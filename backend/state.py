from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import RLock
from typing import Any
import json
import secrets
import uuid

from psycopg import connect
from psycopg.rows import dict_row

from config import settings
from content import build_night_prompt, get_role_night_template, get_script_reference, infer_alignment


UTC = timezone.utc
SNAPSHOT_KEY = 'botc_snapshot'
TEST_PLAYER_PREFIX = 'test-player-'


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    return datetime.fromisoformat(raw)


class GamePhase(str, Enum):
    SETUP = 'setup'
    NIGHT = 'night'
    DAY = 'day'
    FINISHED = 'finished'


class NightStepStatus(str, Enum):
    PENDING = 'pending'
    ACTIVE = 'active'
    AWAITING_RESPONSE = 'awaiting_response'
    AWAITING_APPROVAL = 'awaiting_approval'
    COMPLETE = 'complete'
    SKIPPED = 'skipped'


@dataclass
class WebSession:
    session_id: str
    discord_user_id: str
    username: str
    avatar_hash: str | None
    expires_at: datetime
    storyteller_hint: bool = False


@dataclass
class LobbyPlayer:
    discord_user_id: str
    display_name: str
    joined_at: datetime = field(default_factory=utcnow)


@dataclass
class GamePlayer:
    discord_user_id: str
    display_name: str
    seat: int
    is_alive: bool = True
    role_name: str | None = None
    alignment: str | None = None
    reminders: list[str] = field(default_factory=list)
    private_history: list[str] = field(default_factory=list)
    night_action_prompt: str | None = None
    night_action_response: str | None = None
    night_action_submitted_at: datetime | None = None


@dataclass
class NightStep:
    step_id: str
    order: int
    role_name: str
    player_id: str
    player_name: str
    audience: str
    requires_response: bool = False
    requires_approval: bool = False
    player_prompt: str | None = None
    storyteller_prompt: str | None = None
    approval_prompt: str | None = None
    status: NightStepStatus = NightStepStatus.PENDING
    response_text: str | None = None
    resolution_note: str | None = None
    activated_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class Nomination:
    nominator_id: str
    nominee_id: str
    opened_at: datetime = field(default_factory=utcnow)
    votes: dict[str, bool] = field(default_factory=dict)


@dataclass
class GameRecord:
    game_id: str = 'current'
    name: str = 'Blood on the Clocktower'
    script: str = 'troubles_brewing'
    phase: GamePhase = GamePhase.SETUP
    storyteller_id: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    players: dict[str, GamePlayer] = field(default_factory=dict)
    current_nomination: Nomination | None = None
    log_entries: list[str] = field(default_factory=list)
    night_feed: list[str] = field(default_factory=list)
    night_steps: list[NightStep] = field(default_factory=list)
    active_night_step_id: str | None = None


class GameStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._game = GameRecord()
        self._sessions: dict[str, WebSession] = {}
        self._oauth_states: dict[str, dict[str, Any]] = {}
        self._lobby_players: dict[str, LobbyPlayer] = {}
        self._db_ready = False
        if settings.database_ready:
            self.initialize()

    def initialize(self) -> None:
        if not settings.database_ready:
            return
        with self._lock:
            self._ensure_db_schema()
            self._load_snapshot_from_db()
            self._db_ready = True

    def _connect(self):
        if not settings.database_url:
            raise RuntimeError('DATABASE_URL is not configured.')
        return connect(settings.database_url, row_factory=dict_row)

    def _ensure_db_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    '''
                    CREATE TABLE IF NOT EXISTS app_state (
                        state_key TEXT PRIMARY KEY,
                        payload JSONB NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    '''
                )
            conn.commit()

    def _serialize_session(self, session: WebSession) -> dict[str, Any]:
        return {
            'session_id': session.session_id,
            'discord_user_id': session.discord_user_id,
            'username': session.username,
            'avatar_hash': session.avatar_hash,
            'expires_at': session.expires_at.isoformat(),
            'storyteller_hint': session.storyteller_hint,
        }

    def _serialize_lobby_entry(self, player: LobbyPlayer) -> dict[str, Any]:
        return {
            'discord_user_id': player.discord_user_id,
            'display_name': player.display_name,
            'joined_at': player.joined_at.isoformat(),
        }

    def _serialize_game_player_snapshot(self, player: GamePlayer) -> dict[str, Any]:
        return {
            'discord_user_id': player.discord_user_id,
            'display_name': player.display_name,
            'seat': player.seat,
            'is_alive': player.is_alive,
            'role_name': player.role_name,
            'alignment': player.alignment,
            'reminders': player.reminders,
            'private_history': player.private_history,
            'night_action_prompt': player.night_action_prompt,
            'night_action_response': player.night_action_response,
            'night_action_submitted_at': player.night_action_submitted_at.isoformat() if player.night_action_submitted_at else None,
        }

    def _serialize_night_step_snapshot(self, step: NightStep) -> dict[str, Any]:
        return {
            'step_id': step.step_id,
            'order': step.order,
            'role_name': step.role_name,
            'player_id': step.player_id,
            'player_name': step.player_name,
            'audience': step.audience,
            'requires_response': step.requires_response,
            'requires_approval': step.requires_approval,
            'player_prompt': step.player_prompt,
            'storyteller_prompt': step.storyteller_prompt,
            'approval_prompt': step.approval_prompt,
            'status': step.status.value,
            'response_text': step.response_text,
            'resolution_note': step.resolution_note,
            'activated_at': step.activated_at.isoformat() if step.activated_at else None,
            'completed_at': step.completed_at.isoformat() if step.completed_at else None,
        }

    def _serialize_nomination_snapshot(self, nomination: Nomination | None) -> dict[str, Any] | None:
        if not nomination:
            return None
        return {
            'nominator_id': nomination.nominator_id,
            'nominee_id': nomination.nominee_id,
            'opened_at': nomination.opened_at.isoformat(),
            'votes': nomination.votes,
        }

    def _snapshot_payload_locked(self) -> dict[str, Any]:
        return {
            'game': {
                'game_id': self._game.game_id,
                'name': self._game.name,
                'script': self._game.script,
                'phase': self._game.phase.value,
                'storyteller_id': self._game.storyteller_id,
                'created_at': self._game.created_at.isoformat(),
                'updated_at': self._game.updated_at.isoformat(),
                'players': {player_id: self._serialize_game_player_snapshot(player) for player_id, player in self._game.players.items()},
                'current_nomination': self._serialize_nomination_snapshot(self._game.current_nomination),
                'log_entries': self._game.log_entries,
                'night_feed': self._game.night_feed,
                'night_steps': [self._serialize_night_step_snapshot(step) for step in self._game.night_steps],
                'active_night_step_id': self._game.active_night_step_id,
            },
            'sessions': {session_id: self._serialize_session(session) for session_id, session in self._sessions.items()},
            'oauth_states': self._oauth_states,
            'lobby_players': {player_id: self._serialize_lobby_entry(player) for player_id, player in self._lobby_players.items()},
        }

    def _load_snapshot_from_db(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT payload FROM app_state WHERE state_key = %s', (SNAPSHOT_KEY,))
                row = cur.fetchone()
        if not row:
            return

        payload = row['payload']
        game_payload = payload.get('game', {})
        players_payload = game_payload.get('players', {})
        night_steps_payload = game_payload.get('night_steps', [])
        nomination_payload = game_payload.get('current_nomination')
        current_nomination = None
        if nomination_payload:
            current_nomination = Nomination(
                nominator_id=nomination_payload['nominator_id'],
                nominee_id=nomination_payload['nominee_id'],
                opened_at=parse_dt(nomination_payload.get('opened_at')) or utcnow(),
                votes={str(key): bool(value) for key, value in (nomination_payload.get('votes') or {}).items()},
            )

        self._game = GameRecord(
            game_id=game_payload.get('game_id', 'current'),
            name=game_payload.get('name', 'Blood on the Clocktower'),
            script=game_payload.get('script', 'troubles_brewing'),
            phase=GamePhase(game_payload.get('phase', GamePhase.SETUP.value)),
            storyteller_id=game_payload.get('storyteller_id'),
            created_at=parse_dt(game_payload.get('created_at')) or utcnow(),
            updated_at=parse_dt(game_payload.get('updated_at')) or utcnow(),
            players={
                player_id: GamePlayer(
                    discord_user_id=player_snapshot['discord_user_id'],
                    display_name=player_snapshot['display_name'],
                    seat=int(player_snapshot['seat']),
                    is_alive=bool(player_snapshot.get('is_alive', True)),
                    role_name=player_snapshot.get('role_name'),
                    alignment=player_snapshot.get('alignment'),
                    reminders=list(player_snapshot.get('reminders', [])),
                    private_history=list(player_snapshot.get('private_history', [])),
                    night_action_prompt=player_snapshot.get('night_action_prompt'),
                    night_action_response=player_snapshot.get('night_action_response'),
                    night_action_submitted_at=parse_dt(player_snapshot.get('night_action_submitted_at')),
                )
                for player_id, player_snapshot in players_payload.items()
            },
            current_nomination=current_nomination,
            log_entries=list(game_payload.get('log_entries', [])),
            night_feed=list(game_payload.get('night_feed', [])),
            night_steps=[
                NightStep(
                    step_id=step_snapshot['step_id'],
                    order=int(step_snapshot.get('order', 999)),
                    role_name=step_snapshot.get('role_name', 'Unknown'),
                    player_id=step_snapshot.get('player_id', ''),
                    player_name=step_snapshot.get('player_name', 'Unknown'),
                    audience=step_snapshot.get('audience', 'storyteller'),
                    requires_response=bool(step_snapshot.get('requires_response', False)),
                    requires_approval=bool(step_snapshot.get('requires_approval', False)),
                    player_prompt=step_snapshot.get('player_prompt'),
                    storyteller_prompt=step_snapshot.get('storyteller_prompt'),
                    approval_prompt=step_snapshot.get('approval_prompt'),
                    status=NightStepStatus(step_snapshot.get('status', NightStepStatus.PENDING.value)),
                    response_text=step_snapshot.get('response_text'),
                    resolution_note=step_snapshot.get('resolution_note'),
                    activated_at=parse_dt(step_snapshot.get('activated_at')),
                    completed_at=parse_dt(step_snapshot.get('completed_at')),
                )
                for step_snapshot in night_steps_payload
            ],
            active_night_step_id=game_payload.get('active_night_step_id'),
        )

        self._sessions = {
            session_id: WebSession(
                session_id=session_snapshot['session_id'],
                discord_user_id=session_snapshot['discord_user_id'],
                username=session_snapshot['username'],
                avatar_hash=session_snapshot.get('avatar_hash'),
                expires_at=parse_dt(session_snapshot.get('expires_at')) or utcnow(),
                storyteller_hint=bool(session_snapshot.get('storyteller_hint', False)),
            )
            for session_id, session_snapshot in (payload.get('sessions') or {}).items()
        }
        self._oauth_states = dict(payload.get('oauth_states') or {})
        self._lobby_players = {
            player_id: LobbyPlayer(
                discord_user_id=lobby_snapshot['discord_user_id'],
                display_name=lobby_snapshot['display_name'],
                joined_at=parse_dt(lobby_snapshot.get('joined_at')) or utcnow(),
            )
            for player_id, lobby_snapshot in (payload.get('lobby_players') or {}).items()
        }

    def _persist_locked(self) -> None:
        if not settings.database_ready:
            return
        payload = self._snapshot_payload_locked()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    '''
                    INSERT INTO app_state (state_key, payload, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (state_key)
                    DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
                    ''',
                    (SNAPSHOT_KEY, json.dumps(payload)),
                )
            conn.commit()

    def _touch(self) -> None:
        self._game.updated_at = utcnow()
        self._persist_locked()

    def _clear_night_state_locked(self) -> None:
        self._game.night_steps = []
        self._game.active_night_step_id = None
        for player in self._game.players.values():
            player.night_action_prompt = None
            player.night_action_response = None
            player.night_action_submitted_at = None

    def _get_night_step_locked(self, step_id: str | None) -> NightStep | None:
        if not step_id:
            return None
        for step in self._game.night_steps:
            if step.step_id == step_id:
                return step
        return None

    def _set_player_prompt_for_active_step_locked(self, step: NightStep | None) -> None:
        for player in self._game.players.values():
            player.night_action_prompt = None
        if not step or step.audience != 'player':
            return
        player = self._game.players.get(step.player_id)
        if player:
            player.night_action_prompt = step.player_prompt or build_night_prompt(
                self._game.script,
                player.role_name,
                player.alignment,
                player.reminders,
            )

    def _build_night_steps_locked(self) -> list[NightStep]:
        steps: list[NightStep] = []
        ordered_players = sorted(
            self._game.players.values(),
            key=lambda player: (int(get_role_night_template(player.role_name).get('order', 999)), player.seat),
        )
        for player in ordered_players:
            if not player.is_alive or not player.role_name:
                continue
            template = get_role_night_template(player.role_name)
            steps.append(
                NightStep(
                    step_id=str(uuid.uuid4()),
                    order=int(template.get('order', 999)),
                    role_name=player.role_name,
                    player_id=player.discord_user_id,
                    player_name=player.display_name,
                    audience=str(template.get('audience', 'storyteller')),
                    requires_response=bool(template.get('requires_response', False)),
                    requires_approval=bool(template.get('requires_approval', False)),
                    player_prompt=build_night_prompt(self._game.script, player.role_name, player.alignment, player.reminders),
                    storyteller_prompt=str(template.get('storyteller_prompt') or ''),
                    approval_prompt=str(template.get('approval_prompt') or ''),
                    status=NightStepStatus.PENDING,
                )
            )
        return steps

    def _activate_next_night_step_locked(self) -> NightStep | None:
        next_step = next((step for step in self._game.night_steps if step.status == NightStepStatus.PENDING), None)
        if not next_step:
            self._game.active_night_step_id = None
            self._set_player_prompt_for_active_step_locked(None)
            self._game.night_feed.append('Night order complete.')
            return None

        next_step.status = NightStepStatus.ACTIVE
        next_step.activated_at = utcnow()
        self._game.active_night_step_id = next_step.step_id
        self._set_player_prompt_for_active_step_locked(next_step)
        self._game.night_feed.append(f'Night order: {next_step.player_name} ({next_step.role_name}) is now active.')
        return next_step

    def _complete_current_night_step_locked(self, actor_id: str, resolution_note: str | None = None, approved: bool = False) -> NightStep | None:
        step = self._get_night_step_locked(self._game.active_night_step_id)
        if not step:
            return None
        if step.audience == 'player' and step.requires_response and step.status == NightStepStatus.ACTIVE:
            raise ValueError('The active player must submit a night action before you can advance.')
        if step.status == NightStepStatus.AWAITING_APPROVAL and not approved:
            raise ValueError('This night action is waiting for storyteller approval.')

        step.status = NightStepStatus.COMPLETE
        step.completed_at = utcnow()
        if resolution_note:
            step.resolution_note = resolution_note
        self._game.night_feed.append(
            f'{actor_id} {"approved" if approved else "completed"} {step.player_name} ({step.role_name}) and advanced the night.'
        )
        self._activate_next_night_step_locked()
        return step

    def reset_game(self) -> None:
        with self._lock:
            self._game = GameRecord()
            self._persist_locked()

    def current_game(self) -> GameRecord:
        return self._game

    def get_storyteller_id(self) -> str | None:
        return self._game.storyteller_id

    def set_storyteller_id(self, discord_user_id: str) -> None:
        with self._lock:
            self._game.storyteller_id = discord_user_id
            self._lobby_players.pop(discord_user_id, None)
            self._game.log_entries.append(f'{discord_user_id} claimed storyteller access.')
            self._touch()

    def get_player(self, discord_user_id: str) -> GamePlayer | None:
        with self._lock:
            return self._game.players.get(discord_user_id)

    def list_players(self) -> list[GamePlayer]:
        with self._lock:
            return sorted(self._game.players.values(), key=lambda player: player.seat)

    def register_lobby_player(self, discord_user_id: str, display_name: str) -> None:
        with self._lock:
            if not discord_user_id or discord_user_id == self._game.storyteller_id or discord_user_id in settings.storyteller_ids:
                self._lobby_players.pop(discord_user_id, None)
                self._persist_locked()
                return
            existing = self._lobby_players.get(discord_user_id)
            if existing:
                existing.display_name = display_name
                self._persist_locked()
                return
            self._lobby_players[discord_user_id] = LobbyPlayer(
                discord_user_id=discord_user_id,
                display_name=display_name,
            )
            self._persist_locked()

    def ensure_test_players(self, target_count: int) -> list[LobbyPlayer]:
        with self._lock:
            non_test_players = [
                player for player in self.list_lobby_players()
                if not player.discord_user_id.startswith(TEST_PLAYER_PREFIX)
            ]
            existing_test_players = [
                player for player in self.list_lobby_players()
                if player.discord_user_id.startswith(TEST_PLAYER_PREFIX)
            ]
            total_needed = max(target_count - len(non_test_players), 0)

            if len(existing_test_players) > total_needed:
                keep_ids = {player.discord_user_id for player in existing_test_players[:total_needed]}
                for player_id in list(self._lobby_players.keys()):
                    if player_id.startswith(TEST_PLAYER_PREFIX) and player_id not in keep_ids:
                        self._lobby_players.pop(player_id, None)
            elif len(existing_test_players) < total_needed:
                start_index = len(existing_test_players) + 1
                for index in range(start_index, total_needed + 1):
                    player_id = f'{TEST_PLAYER_PREFIX}{index}'
                    while player_id in self._lobby_players or player_id in self._game.players:
                        index += 1
                        player_id = f'{TEST_PLAYER_PREFIX}{index}'
                    self._lobby_players[player_id] = LobbyPlayer(
                        discord_user_id=player_id,
                        display_name=f'Test Player {index}',
                    )

            self._persist_locked()
            return self.list_lobby_players()

    def clear_test_players(self) -> list[LobbyPlayer]:
        with self._lock:
            for player_id in list(self._lobby_players.keys()):
                if player_id.startswith(TEST_PLAYER_PREFIX):
                    self._lobby_players.pop(player_id, None)
            self._persist_locked()
            return self.list_lobby_players()

    def remove_lobby_player(self, discord_user_id: str) -> None:
        with self._lock:
            self._lobby_players.pop(discord_user_id, None)
            self._persist_locked()

    def list_lobby_players(self) -> list[LobbyPlayer]:
        with self._lock:
            seated_ids = set(self._game.players.keys())
            return [
                player
                for player in sorted(self._lobby_players.values(), key=lambda player: player.joined_at)
                if player.discord_user_id not in seated_ids
            ]

    def issue_oauth_state(self, next_path: str) -> str:
        with self._lock:
            state = secrets.token_urlsafe(24)
            self._oauth_states[state] = {
                'next_path': next_path or '/',
                'created_at': utcnow().isoformat(),
            }
            self._persist_locked()
            return state

    def consume_oauth_state(self, state: str) -> str:
        with self._lock:
            payload = self._oauth_states.pop(state, None)
            if not payload:
                raise KeyError('Invalid OAuth state')
            self._persist_locked()
            return payload['next_path']

    def create_session(self, discord_user_id: str, username: str, avatar_hash: str | None) -> WebSession:
        with self._lock:
            session_id = secrets.token_urlsafe(32)
            storyteller_hint = discord_user_id in settings.storyteller_ids
            session = WebSession(
                session_id=session_id,
                discord_user_id=discord_user_id,
                username=username,
                avatar_hash=avatar_hash,
                expires_at=utcnow() + timedelta(hours=settings.session_duration_hours),
                storyteller_hint=storyteller_hint,
            )
            self._sessions[session_id] = session
            self._persist_locked()
            return session

    def get_session(self, session_id: str | None) -> WebSession | None:
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            if session.expires_at <= utcnow():
                self._sessions.pop(session_id, None)
                self._persist_locked()
                return None
            return session

    def delete_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            self._sessions.pop(session_id, None)
            self._persist_locked()

    def is_storyteller(self, discord_user_id: str) -> bool:
        return bool(
            discord_user_id
            and (
                discord_user_id in settings.storyteller_ids
                or self._game.storyteller_id == discord_user_id
            )
        )

    def create_or_update_game(
        self,
        storyteller_id: str,
        game_name: str,
        script: str,
        players: list[dict[str, Any]],
    ) -> GameRecord:
        with self._lock:
            player_map: dict[str, GamePlayer] = {}
            for raw_player in players:
                discord_user_id = str(raw_player['discord_user_id'])
                role_name = raw_player.get('role_name')
                reminders = list(raw_player.get('reminders', []))
                alignment = raw_player.get('alignment') or infer_alignment(script, role_name)
                player_map[discord_user_id] = GamePlayer(
                    discord_user_id=discord_user_id,
                    display_name=raw_player['display_name'],
                    seat=int(raw_player['seat']),
                    is_alive=bool(raw_player.get('is_alive', True)),
                    role_name=role_name,
                    alignment=alignment,
                    reminders=reminders,
                    private_history=list(raw_player.get('private_history', [])),
                    night_action_prompt=raw_player.get('night_action_prompt') or build_night_prompt(script, role_name, alignment, reminders),
                    night_action_response=raw_player.get('night_action_response'),
                )
                self._lobby_players.pop(discord_user_id, None)

            self._game = GameRecord(
                game_id=str(uuid.uuid4()),
                name=game_name,
                script=script,
                phase=GamePhase.SETUP,
                storyteller_id=storyteller_id,
                players=player_map,
                log_entries=[f'Game created by storyteller {storyteller_id}.'],
            )
            self._clear_night_state_locked()
            self._persist_locked()
            return self._game

    def set_phase(self, actor_id: str, phase: GamePhase) -> GameRecord:
        with self._lock:
            self._game.phase = phase
            if phase == GamePhase.NIGHT:
                self._clear_night_state_locked()
                self._game.night_steps = self._build_night_steps_locked()
                self._activate_next_night_step_locked()
            else:
                self._clear_night_state_locked()
            self._game.log_entries.append(f'{actor_id} moved the game to {phase.value}.')
            self._touch()
            return self._game

    def set_nomination(self, actor_id: str, nominator_id: str, nominee_id: str) -> Nomination:
        with self._lock:
            self._game.current_nomination = Nomination(
                nominator_id=nominator_id,
                nominee_id=nominee_id,
            )
            self._game.log_entries.append(
                f'{actor_id} opened a nomination: {nominator_id} -> {nominee_id}.'
            )
            self._touch()
            return self._game.current_nomination

    def cast_vote(self, voter_id: str, approve: bool) -> Nomination:
        with self._lock:
            if voter_id not in self._game.players:
                raise KeyError('Player is not seated in the current game.')
            if not self._game.current_nomination:
                raise ValueError('There is no active nomination.')
            self._game.current_nomination.votes[voter_id] = approve
            vote_label = 'yes' if approve else 'no'
            self._game.log_entries.append(f'{voter_id} cast a {vote_label} vote.')
            self._touch()
            return self._game.current_nomination

    def set_player_alive(self, actor_id: str, discord_user_id: str, is_alive: bool) -> GamePlayer:
        with self._lock:
            player = self._game.players[discord_user_id]
            player.is_alive = is_alive
            self._game.log_entries.append(
                f'{actor_id} marked {discord_user_id} as {"alive" if is_alive else "dead"}.'
            )
            self._touch()
            return player

    def add_storyteller_note(self, actor_id: str, message: str, night: bool = False) -> None:
        with self._lock:
            target = self._game.night_feed if night else self._game.log_entries
            target.append(f'{actor_id}: {message}')
            self._touch()

    def add_private_history(self, discord_user_id: str, message: str) -> None:
        with self._lock:
            player = self._game.players[discord_user_id]
            player.private_history.append(message)
            self._touch()

    def set_player_reminders(self, actor_id: str, discord_user_id: str, reminders: list[str]) -> GamePlayer:
        with self._lock:
            player = self._game.players[discord_user_id]
            player.reminders = reminders
            player.night_action_prompt = build_night_prompt(self._game.script, player.role_name, player.alignment, reminders)
            self._game.log_entries.append(f'{actor_id} updated reminders for {discord_user_id}.')
            self._touch()
            return player

    def set_night_prompt(self, actor_id: str, discord_user_id: str, prompt: str) -> GamePlayer:
        with self._lock:
            player = self._game.players[discord_user_id]
            player.night_action_prompt = prompt
            active_step = self._get_night_step_locked(self._game.active_night_step_id)
            if active_step and active_step.player_id == discord_user_id:
                active_step.player_prompt = prompt
            player.night_action_response = None
            player.night_action_submitted_at = None
            self._game.night_feed.append(f'{actor_id} set a night prompt for {player.display_name}.')
            self._touch()
            return player

    def submit_night_action(self, discord_user_id: str, response_text: str) -> GamePlayer:
        with self._lock:
            if self._game.phase != GamePhase.NIGHT:
                raise ValueError('Night actions can only be submitted during the night phase.')
            active_step = self._get_night_step_locked(self._game.active_night_step_id)
            if not active_step:
                raise ValueError('There is no active night step right now.')
            if active_step.player_id != discord_user_id or active_step.audience != 'player':
                raise ValueError('It is not your turn in the night order.')

            player = self._game.players[discord_user_id]
            player.night_action_response = response_text
            player.night_action_submitted_at = utcnow()
            player.private_history.append(f'Night action submitted: {response_text}')
            active_step.response_text = response_text
            if active_step.requires_approval:
                active_step.status = NightStepStatus.AWAITING_APPROVAL
                self._game.night_feed.append(f'{player.display_name} submitted a night action and is awaiting storyteller approval.')
            else:
                active_step.status = NightStepStatus.COMPLETE
                active_step.completed_at = utcnow()
                self._game.night_feed.append(f'{player.display_name} submitted a night action.')
                self._activate_next_night_step_locked()
            self._touch()
            return player

    def advance_night_step(self, actor_id: str, resolution_note: str | None = None) -> dict[str, Any]:
        with self._lock:
            if self._game.phase != GamePhase.NIGHT:
                raise ValueError('You can only advance the night during the night phase.')
            self._complete_current_night_step_locked(actor_id, resolution_note=resolution_note)
            self._touch()
            return self.get_storyteller_state()

    def approve_night_step(self, actor_id: str, resolution_note: str | None = None) -> dict[str, Any]:
        with self._lock:
            if self._game.phase != GamePhase.NIGHT:
                raise ValueError('You can only approve night actions during the night phase.')
            step = self._get_night_step_locked(self._game.active_night_step_id)
            if not step:
                raise ValueError('There is no active night step right now.')
            if step.status not in {NightStepStatus.AWAITING_APPROVAL, NightStepStatus.ACTIVE}:
                raise ValueError('This night step does not need storyteller approval.')
            self._complete_current_night_step_locked(actor_id, resolution_note=resolution_note, approved=True)
            self._touch()
            return self.get_storyteller_state()

    def _serialize_lobby_player(self, player: LobbyPlayer) -> dict[str, Any]:
        return {
            'discord_user_id': player.discord_user_id,
            'display_name': player.display_name,
            'joined_at': player.joined_at.isoformat(),
        }

    def _serialize_player_public(self, player: GamePlayer) -> dict[str, Any]:
        return {
            'discord_user_id': player.discord_user_id,
            'display_name': player.display_name,
            'seat': player.seat,
            'is_alive': player.is_alive,
        }

    def _serialize_player_private(self, player: GamePlayer) -> dict[str, Any]:
        payload = self._serialize_player_public(player)
        payload.update(
            {
                'role_name': player.role_name,
                'alignment': player.alignment,
                'reminders': player.reminders,
                'private_history': player.private_history,
                'night_action_prompt': player.night_action_prompt,
                'night_action_response': player.night_action_response,
                'night_action_submitted_at': player.night_action_submitted_at.isoformat() if player.night_action_submitted_at else None,
            }
        )
        return payload

    def _serialize_night_step(self, step: NightStep | None) -> dict[str, Any] | None:
        if not step:
            return None
        return {
            'step_id': step.step_id,
            'order': step.order,
            'role_name': step.role_name,
            'player_id': step.player_id,
            'player_name': step.player_name,
            'audience': step.audience,
            'requires_response': step.requires_response,
            'requires_approval': step.requires_approval,
            'player_prompt': step.player_prompt,
            'storyteller_prompt': step.storyteller_prompt,
            'approval_prompt': step.approval_prompt,
            'status': step.status.value,
            'response_text': step.response_text,
            'resolution_note': step.resolution_note,
            'activated_at': step.activated_at.isoformat() if step.activated_at else None,
            'completed_at': step.completed_at.isoformat() if step.completed_at else None,
        }

    def serialize_nomination(self) -> dict[str, Any] | None:
        nomination = self._game.current_nomination
        if not nomination:
            return None
        return {
            'nominator_id': nomination.nominator_id,
            'nominee_id': nomination.nominee_id,
            'opened_at': nomination.opened_at.isoformat(),
            'votes': nomination.votes,
        }

    def get_public_state(self) -> dict[str, Any]:
        with self._lock:
            players = sorted(self._game.players.values(), key=lambda player: player.seat)
            return {
                'game_id': self._game.game_id,
                'name': self._game.name,
                'script': self._game.script,
                'script_reference': get_script_reference(self._game.script),
                'phase': self._game.phase.value,
                'players': [self._serialize_player_public(player) for player in players],
                'current_nomination': self.serialize_nomination(),
                'log_entries': self._game.log_entries[-20:],
            }

    def get_player_state(self, discord_user_id: str, viewer_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            player = self._game.players[discord_user_id]
            public_state = self.get_public_state()
            public_state['viewer'] = self._serialize_player_private(player)
            public_state['viewer_context'] = {
                'requested_player_id': discord_user_id,
                'viewer_id': viewer_id or discord_user_id,
                'is_preview': bool(viewer_id and viewer_id != discord_user_id),
            }
            public_state['current_night_step'] = self._serialize_night_step(
                self._get_night_step_locked(self._game.active_night_step_id)
            )
            return public_state

    def get_storyteller_state(self) -> dict[str, Any]:
        with self._lock:
            players = sorted(self._game.players.values(), key=lambda player: player.seat)
            lobby_players = self.list_lobby_players()
            return {
                'game_id': self._game.game_id,
                'name': self._game.name,
                'script': self._game.script,
                'script_reference': get_script_reference(self._game.script),
                'phase': self._game.phase.value,
                'storyteller_id': self._game.storyteller_id,
                'players': [self._serialize_player_private(player) for player in players],
                'lobby_players': [self._serialize_lobby_player(player) for player in lobby_players],
                'current_nomination': self.serialize_nomination(),
                'log_entries': self._game.log_entries[-50:],
                'night_feed': self._game.night_feed[-50:],
                'night_steps': [self._serialize_night_step(step) for step in self._game.night_steps],
                'current_night_step': self._serialize_night_step(
                    self._get_night_step_locked(self._game.active_night_step_id)
                ),
            }


store = GameStore()



















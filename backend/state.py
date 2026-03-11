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
from content import build_night_prompt, get_game_status_options, get_role_group, get_role_night_template, get_script_reference, get_script_role_names, infer_alignment, is_demon_role


UTC = timezone.utc
SNAPSHOT_KEY = 'botc_snapshot'
TEST_PLAYER_PREFIX = 'test-player-'
STATUS_POISONED = 'Poisoned'
STATUS_DRUNK = 'Drunk'
STATUS_DIES_AT_DAWN = 'Dies at dawn'


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
    storyteller_message: str | None = None
    status_markers: list[str] = field(default_factory=list)
    is_poisoned: bool = False
    is_drunk: bool = False
    pending_death: bool = False
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
    input_type: str | None = None
    target_count: int | None = None
    allow_self: bool = True
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
    night_count: int = 0
    night_steps: list[NightStep] = field(default_factory=list)
    active_night_step_id: str | None = None
    demon_bluffs: list[str] = field(default_factory=list)


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

    def _normalize_status_markers(self, markers: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for marker in markers or []:
            cleaned = str(marker).strip()
            if not cleaned or cleaned in seen:
                continue
            normalized.append(cleaned)
            seen.add(cleaned)
        return normalized

    def _sync_player_status_flags_locked(self, player: GamePlayer) -> None:
        player.status_markers = self._normalize_status_markers(player.status_markers)
        marker_set = set(player.status_markers)
        player.is_poisoned = STATUS_POISONED in marker_set
        player.is_drunk = STATUS_DRUNK in marker_set
        player.pending_death = STATUS_DIES_AT_DAWN in marker_set

    def _set_status_marker_locked(self, player: GamePlayer, marker: str, enabled: bool) -> None:
        cleaned = marker.strip()
        if not cleaned:
            return
        marker_set = set(player.status_markers)
        if enabled:
            marker_set.add(cleaned)
        else:
            marker_set.discard(cleaned)
        player.status_markers = sorted(marker_set)
        self._sync_player_status_flags_locked(player)

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
            'storyteller_message': player.storyteller_message,
            'status_markers': player.status_markers,
            'is_poisoned': player.is_poisoned,
            'is_drunk': player.is_drunk,
            'pending_death': player.pending_death,
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
            'input_type': step.input_type,
            'target_count': step.target_count,
            'allow_self': step.allow_self,
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
                'night_count': self._game.night_count,
                'night_steps': [self._serialize_night_step_snapshot(step) for step in self._game.night_steps],
                'active_night_step_id': self._game.active_night_step_id,
                'demon_bluffs': self._game.demon_bluffs,
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
                    storyteller_message=player_snapshot.get('storyteller_message'),
                    status_markers=self._normalize_status_markers([
                        *(player_snapshot.get('status_markers') or []),
                        *([STATUS_POISONED] if player_snapshot.get('is_poisoned') else []),
                        *([STATUS_DRUNK] if player_snapshot.get('is_drunk') else []),
                        *([STATUS_DIES_AT_DAWN] if player_snapshot.get('pending_death') else []),
                    ]),
                    night_action_response=player_snapshot.get('night_action_response'),
                    night_action_submitted_at=parse_dt(player_snapshot.get('night_action_submitted_at')),
                )
                for player_id, player_snapshot in players_payload.items()
            },
            current_nomination=current_nomination,
            log_entries=list(game_payload.get('log_entries', [])),
            night_feed=list(game_payload.get('night_feed', [])),
            night_count=int(game_payload.get('night_count', 0)),
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
                    input_type=step_snapshot.get('input_type'),
                    target_count=step_snapshot.get('target_count'),
                    allow_self=bool(step_snapshot.get('allow_self', True)),
                    status=NightStepStatus(step_snapshot.get('status', NightStepStatus.PENDING.value)),
                    response_text=step_snapshot.get('response_text'),
                    resolution_note=step_snapshot.get('resolution_note'),
                    activated_at=parse_dt(step_snapshot.get('activated_at')),
                    completed_at=parse_dt(step_snapshot.get('completed_at')),
                )
                for step_snapshot in night_steps_payload
            ],
            active_night_step_id=game_payload.get('active_night_step_id'),
            demon_bluffs=list(game_payload.get('demon_bluffs', [])),
        )

        for player in self._game.players.values():
            self._sync_player_status_flags_locked(player)

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

    def _clear_night_state_locked(self, clear_storyteller_message: bool = False) -> None:
        self._game.night_steps = []
        self._game.active_night_step_id = None
        for player in self._game.players.values():
            player.night_action_prompt = None
            if clear_storyteller_message:
                player.storyteller_message = None
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

    def _skip_future_steps_for_player_locked(self, discord_user_id: str, reason: str) -> None:
        for step in self._game.night_steps:
            if step.player_id == discord_user_id and step.status == NightStepStatus.PENDING:
                step.status = NightStepStatus.SKIPPED
                step.completed_at = utcnow()
                step.resolution_note = reason

    def _restore_future_steps_for_player_locked(self, discord_user_id: str, reason: str) -> None:
        for step in self._game.night_steps:
            if step.player_id == discord_user_id and step.status == NightStepStatus.SKIPPED and step.resolution_note == reason:
                step.status = NightStepStatus.PENDING
                step.completed_at = None
                step.resolution_note = None

    def _apply_pending_deaths_locked(self, actor_id: str) -> list[str]:
        resolved: list[str] = []
        for player in self._game.players.values():
            if not player.pending_death:
                continue
            self._set_status_marker_locked(player, STATUS_DIES_AT_DAWN, False)
            if player.is_alive:
                player.is_alive = False
                player.storyteller_message = 'You died in the night.'
                player.private_history.append('Storyteller: You died in the night.')
                resolved.append(player.display_name)
        if resolved:
            self._game.log_entries.append(f'{actor_id} revealed dawn deaths: {", ".join(resolved)}.')
        return resolved

    def _apply_night_resolution_locked(
        self,
        actor_id: str,
        step: NightStep,
        resolution_note: str | None,
        death_target_ids: list[str],
        poison_target_ids: list[str],
        drunk_target_ids: list[str],
        sober_target_ids: list[str],
        healthy_target_ids: list[str],
    ) -> list[str]:
        summary: list[str] = []
        if resolution_note:
            player = self._game.players.get(step.player_id)
            if player:
                player.storyteller_message = resolution_note
                player.private_history.append(f'Storyteller: {resolution_note}')
            summary.append(f'info given: {resolution_note}')

        for player_id in death_target_ids:
            target = self._game.players.get(player_id)
            if not target:
                continue
            self._set_status_marker_locked(target, STATUS_DIES_AT_DAWN, True)
            self._skip_future_steps_for_player_locked(player_id, 'Skipped because this player will die at dawn.')
            summary.append(f'dies at dawn: {target.display_name}')

        for player_id in poison_target_ids:
            target = self._game.players.get(player_id)
            if not target:
                continue
            self._set_status_marker_locked(target, STATUS_POISONED, True)
            summary.append(f'poisoned: {target.display_name}')

        for player_id in drunk_target_ids:
            target = self._game.players.get(player_id)
            if not target:
                continue
            self._set_status_marker_locked(target, STATUS_DRUNK, True)
            summary.append(f'drunk: {target.display_name}')

        for player_id in sober_target_ids:
            target = self._game.players.get(player_id)
            if not target:
                continue
            self._set_status_marker_locked(target, STATUS_DRUNK, False)
            summary.append(f'sober: {target.display_name}')

        for player_id in healthy_target_ids:
            target = self._game.players.get(player_id)
            if not target:
                continue
            self._set_status_marker_locked(target, STATUS_POISONED, False)
            summary.append(f'healthy: {target.display_name}')

        if not summary:
            summary.append('no storyteller updates recorded')
        return summary

    def _build_night_steps_locked(self) -> list[NightStep]:
        steps: list[NightStep] = []
        night_number = max(self._game.night_count, 1)
        active_players = [
            player for player in self._game.players.values()
            if player.is_alive and not player.pending_death and player.role_name
        ]
        ordered_players = sorted(
            active_players,
            key=lambda player: (int(get_role_night_template(player.role_name, night_number).get('order', 999)), player.seat),
        )
        for player in ordered_players:
            template = get_role_night_template(player.role_name, night_number)
            if not bool(template.get('appears_tonight', True)):
                continue
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
                    input_type=str(template.get('input_type')) if template.get('input_type') else None,
                    target_count=int(template.get('target_count')) if template.get('target_count') else None,
                    allow_self=bool(template.get('allow_self', True)),
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

    def _complete_current_night_step_locked(
        self,
        actor_id: str,
        resolution_note: str | None = None,
        approved: bool = False,
        death_target_ids: list[str] | None = None,
        poison_target_ids: list[str] | None = None,
        drunk_target_ids: list[str] | None = None,
        sober_target_ids: list[str] | None = None,
        healthy_target_ids: list[str] | None = None,
    ) -> NightStep | None:
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
        summary = self._apply_night_resolution_locked(
            actor_id,
            step,
            resolution_note,
            death_target_ids or [],
            poison_target_ids or [],
            drunk_target_ids or [],
            sober_target_ids or [],
            healthy_target_ids or [],
        )
        self._game.night_feed.append(
            f'{actor_id} {"approved" if approved else "completed"} {step.player_name} ({step.role_name}): ' + '; '.join(summary)
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

    def list_available_demon_bluffs(self) -> list[str]:
        with self._lock:
            in_play_roles = {player.role_name for player in self._game.players.values() if player.role_name}
            return [role_name for role_name in get_script_role_names(self._game.script) if role_name not in in_play_roles]

    def seat_lobby_player(self, actor_id: str, lobby_player_id: str, seat: int) -> GamePlayer:
        with self._lock:
            lobby_player = self._lobby_players.get(lobby_player_id)
            if not lobby_player:
                raise KeyError('Lobby player not found.')
            if lobby_player_id in self._game.players:
                raise ValueError('That player is already seated in the current game.')
            if any(player.seat == seat for player in self._game.players.values()):
                raise ValueError('That seat is already occupied.')

            player = GamePlayer(
                discord_user_id=lobby_player.discord_user_id,
                display_name=lobby_player.display_name,
                seat=seat,
            )
            self._game.players[player.discord_user_id] = player
            self._lobby_players.pop(player.discord_user_id, None)
            self._game.log_entries.append(f'{actor_id} seated {player.display_name} in seat {seat + 1}.')
            self._touch()
            return player

    def set_demon_bluffs(self, actor_id: str, bluffs: list[str]) -> list[str]:
        with self._lock:
            available = set(self.list_available_demon_bluffs())
            cleaned: list[str] = []
            seen: set[str] = set()
            for bluff in bluffs:
                name = str(bluff).strip()
                if not name or name in seen:
                    continue
                if name not in available:
                    raise ValueError(f'{name} is not an out-of-play role for this script.')
                cleaned.append(name)
                seen.add(name)
            if len(cleaned) > 3:
                raise ValueError('You can set at most 3 demon bluffs.')
            self._game.demon_bluffs = cleaned
            self._game.log_entries.append(f'{actor_id} updated demon bluffs.')
            self._touch()
            return list(self._game.demon_bluffs)

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
        demon_bluffs: list[str] | None = None,
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
                    storyteller_message=raw_player.get('storyteller_message'),
                    status_markers=self._normalize_status_markers([
                        *(raw_player.get('status_markers') or []),
                        *([STATUS_POISONED] if raw_player.get('is_poisoned') else []),
                        *([STATUS_DRUNK] if raw_player.get('is_drunk') else []),
                        *([STATUS_DIES_AT_DAWN] if raw_player.get('pending_death') else []),
                    ]),
                    night_action_response=raw_player.get('night_action_response'),
                )
                self._sync_player_status_flags_locked(player_map[discord_user_id])
                self._lobby_players.pop(discord_user_id, None)

            in_play_roles = {player.role_name for player in player_map.values() if player.role_name}
            allowed_bluffs = [role_name for role_name in get_script_role_names(script) if role_name not in in_play_roles]
            cleaned_bluffs: list[str] = []
            seen_bluffs: set[str] = set()
            for bluff in demon_bluffs or []:
                name = str(bluff).strip()
                if not name or name in seen_bluffs or name not in allowed_bluffs:
                    continue
                cleaned_bluffs.append(name)
                seen_bluffs.add(name)
                if len(cleaned_bluffs) == 3:
                    break

            self._game = GameRecord(
                game_id=str(uuid.uuid4()),
                name=game_name,
                script=script,
                phase=GamePhase.SETUP,
                storyteller_id=storyteller_id,
                players=player_map,
                log_entries=[f'Game created by storyteller {storyteller_id}.'],
                demon_bluffs=cleaned_bluffs,
            )
            self._clear_night_state_locked(clear_storyteller_message=True)
            self._persist_locked()
            return self._game

    def set_phase(self, actor_id: str, phase: GamePhase) -> GameRecord:
        with self._lock:
            self._game.phase = phase
            if phase == GamePhase.NIGHT:
                self._game.night_count += 1
                self._clear_night_state_locked(clear_storyteller_message=True)
                self._game.night_steps = self._build_night_steps_locked()
                self._activate_next_night_step_locked()
            else:
                if phase == GamePhase.DAY:
                    dawn_deaths = self._apply_pending_deaths_locked(actor_id)
                    if dawn_deaths:
                        self._game.night_feed.append('Dawn deaths: ' + ', '.join(dawn_deaths))
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
            if is_alive:
                self._set_status_marker_locked(player, STATUS_DIES_AT_DAWN, False)
                self._restore_future_steps_for_player_locked(discord_user_id, 'Skipped because this player is dead.')
                self._restore_future_steps_for_player_locked(discord_user_id, 'Skipped because this player will die at dawn.')
            else:
                self._skip_future_steps_for_player_locked(discord_user_id, 'Skipped because this player is dead.')
            self._game.log_entries.append(
                f'{actor_id} marked {discord_user_id} as {"alive" if is_alive else "dead"}.'
            )
            self._touch()
            return player

    def update_player_status(
        self,
        actor_id: str,
        discord_user_id: str,
        *,
        is_poisoned: bool | None = None,
        is_drunk: bool | None = None,
        pending_death: bool | None = None,
        add_statuses: list[str] | None = None,
        remove_statuses: list[str] | None = None,
    ) -> GamePlayer:
        with self._lock:
            player = self._game.players[discord_user_id]
            changes: list[str] = []
            if is_poisoned is not None:
                self._set_status_marker_locked(player, STATUS_POISONED, is_poisoned)
                changes.append(f'poisoned={is_poisoned}')
            if is_drunk is not None:
                self._set_status_marker_locked(player, STATUS_DRUNK, is_drunk)
                changes.append(f'drunk={is_drunk}')
            if pending_death is not None:
                self._set_status_marker_locked(player, STATUS_DIES_AT_DAWN, pending_death)
                changes.append(f'pending_death={pending_death}')
                if pending_death:
                    self._skip_future_steps_for_player_locked(discord_user_id, 'Skipped because this player will die at dawn.')
                else:
                    self._restore_future_steps_for_player_locked(discord_user_id, 'Skipped because this player will die at dawn.')
            for status in self._normalize_status_markers(add_statuses):
                self._set_status_marker_locked(player, status, True)
                changes.append(f'added={status}')
            for status in self._normalize_status_markers(remove_statuses):
                self._set_status_marker_locked(player, status, False)
                changes.append(f'removed={status}')
            if changes:
                self._game.night_feed.append(f'{actor_id} updated {player.display_name}: ' + ', '.join(changes))
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

    def _resolve_history_targets_locked(self, response_text: str) -> list[str]:
        targets: list[str] = []
        for raw_target in response_text.split(','):
            token = raw_target.strip()
            if not token:
                continue
            player = self._game.players.get(token)
            targets.append(player.display_name if player else token)
        return targets

    def _format_private_history_entry_locked(self, player: GamePlayer, response_text: str) -> str:
        role_name = player.role_name or 'Night action'
        cleaned = response_text.strip()
        targets = self._resolve_history_targets_locked(cleaned)
        if role_name == 'Imp' and targets:
            return f'Imp marked {targets[0]} to die at dawn.'
        if role_name == 'Fortune Teller' and len(targets) >= 2:
            return f'Fortune Teller checked {targets[0]} and {targets[1]}.'
        if role_name == 'Monk' and targets:
            return f'Monk protected {targets[0]} for the night.'
        if role_name == 'Poisoner' and targets:
            return f'Poisoner chose to poison {targets[0]}.'
        if role_name == 'Butler' and targets:
            return f'Butler chose to follow {targets[0]} tomorrow.'
        if role_name == 'Dreamer' and targets:
            return f'Dreamer selected {targets[0]} for a reading.'
        if role_name == 'Snake Charmer' and targets:
            return f'Snake Charmer targeted {targets[0]}.'
        if role_name == 'Seamstress' and len(targets) >= 2:
            return f'Seamstress compared {targets[0]} and {targets[1]}.'
        if role_name == 'Witch' and targets:
            return f'Witch hexed {targets[0]}.'
        if role_name in {'Fang Gu', 'Vigormortis', 'No Dashii', 'Vortox', 'Zombuul'} and targets:
            return f'{role_name} chose {targets[0]} as the target.'
        if role_name == 'Sailor' and targets:
            return f'Sailor drank with {targets[0]}.'
        if role_name == 'Chambermaid' and len(targets) >= 2:
            return f'Chambermaid checked whether {targets[0]} and {targets[1]} woke tonight.'
        if role_name == 'Exorcist' and targets:
            return f'Exorcist attempted to block {targets[0]}.'
        if role_name == 'Innkeeper' and len(targets) >= 2:
            return f'Innkeeper protected {targets[0]} and {targets[1]}.'
        if role_name == 'Pukka' and targets:
            return f'Pukka poisoned {targets[0]}.'
        if role_name == 'Shabaloth' and len(targets) >= 2:
            return f'Shabaloth targeted {targets[0]} and {targets[1]}.'
        if targets:
            if len(targets) == 1:
                return f'{role_name} targeted {targets[0]}.'
            return f"{role_name} targeted {', '.join(targets[:-1])} and {targets[-1]}."
        if cleaned:
            return f'{role_name} submitted: {cleaned}'
        return f'{role_name} submitted a night action.'
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
            player.private_history.append(self._format_private_history_entry_locked(player, response_text))
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

    def signal_night_step_ready(self, discord_user_id: str) -> GamePlayer:
        with self._lock:
            if self._game.phase != GamePhase.NIGHT:
                raise ValueError('Night readiness can only be signaled during the night phase.')
            active_step = self._get_night_step_locked(self._game.active_night_step_id)
            if not active_step:
                raise ValueError('There is no active night step right now.')
            if active_step.player_id != discord_user_id:
                raise ValueError('It is not your turn in the night order.')

            player = self._game.players[discord_user_id]
            if not self._viewer_can_see_grimoire_locked(player, active_step):
                raise ValueError('This player does not currently have a reviewable grimoire window.')

            player.private_history.append('Marked grimoire review as complete.')
            active_step.response_text = 'Spy has finished reviewing the grimoire.'
            self._game.night_feed.append(f'{player.display_name} signaled that they are done reviewing the grimoire.')
            self._touch()
            return player

    def advance_night_step(
        self,
        actor_id: str,
        resolution_note: str | None = None,
        *,
        death_target_ids: list[str] | None = None,
        poison_target_ids: list[str] | None = None,
        drunk_target_ids: list[str] | None = None,
        sober_target_ids: list[str] | None = None,
        healthy_target_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self._game.phase != GamePhase.NIGHT:
                raise ValueError('You can only advance the night during the night phase.')
            self._complete_current_night_step_locked(
                actor_id,
                resolution_note=resolution_note,
                death_target_ids=death_target_ids,
                poison_target_ids=poison_target_ids,
                drunk_target_ids=drunk_target_ids,
                sober_target_ids=sober_target_ids,
                healthy_target_ids=healthy_target_ids,
            )
            self._touch()
            return self.get_storyteller_state()

    def approve_night_step(
        self,
        actor_id: str,
        resolution_note: str | None = None,
        *,
        death_target_ids: list[str] | None = None,
        poison_target_ids: list[str] | None = None,
        drunk_target_ids: list[str] | None = None,
        sober_target_ids: list[str] | None = None,
        healthy_target_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            if self._game.phase != GamePhase.NIGHT:
                raise ValueError('You can only approve night actions during the night phase.')
            step = self._get_night_step_locked(self._game.active_night_step_id)
            if not step:
                raise ValueError('There is no active night step right now.')
            if step.status not in {NightStepStatus.AWAITING_APPROVAL, NightStepStatus.ACTIVE}:
                raise ValueError('This night step does not need storyteller approval.')
            self._complete_current_night_step_locked(
                actor_id,
                resolution_note=resolution_note,
                approved=True,
                death_target_ids=death_target_ids,
                poison_target_ids=poison_target_ids,
                drunk_target_ids=drunk_target_ids,
                sober_target_ids=sober_target_ids,
                healthy_target_ids=healthy_target_ids,
            )
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

    def _serialize_grimoire_entry_for_player(self, player: GamePlayer) -> dict[str, Any]:
        return {
            'discord_user_id': player.discord_user_id,
            'display_name': player.display_name,
            'seat': player.seat,
            'is_alive': player.is_alive,
            'role_name': player.role_name,
            'alignment': player.alignment,
            'status_markers': player.status_markers,
            'reminders': player.reminders,
        }

    def _viewer_can_see_grimoire_locked(self, player: GamePlayer, step: NightStep | None) -> bool:
        if 'Show Grimoire' not in player.status_markers:
            return False
        if not step:
            return False
        return step.player_id == player.discord_user_id and step.role_name == player.role_name

    def _serialize_player_storyteller(self, player: GamePlayer) -> dict[str, Any]:
        payload = self._serialize_player_private(player)
        payload.update(
            {
                'is_poisoned': player.is_poisoned,
                'is_drunk': player.is_drunk,
                'pending_death': player.pending_death,
            }
        )
        return payload

    def _serialize_player_private(self, player: GamePlayer) -> dict[str, Any]:
        payload = self._serialize_player_public(player)
        payload.update(
            {
                'role_name': player.role_name,
                'alignment': player.alignment,
                'reminders': player.reminders,
                'private_history': player.private_history,
                'night_action_prompt': player.night_action_prompt,
                'storyteller_message': player.storyteller_message,
                'status_markers': player.status_markers,
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
            'input_type': step.input_type,
            'target_count': step.target_count,
            'allow_self': step.allow_self,
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

    def _serialize_evil_team_locked(self, viewer: GamePlayer) -> list[dict[str, str]]:
        if self._game.phase != GamePhase.NIGHT or len(self._game.players) < 8:
            return []
        viewer_group = get_role_group(self._game.script, viewer.role_name)
        if viewer.alignment != 'Evil' or viewer_group not in {'minions', 'demons'}:
            return []

        entries: list[dict[str, str]] = []
        for player in sorted(self._game.players.values(), key=lambda item: item.seat):
            if player.discord_user_id == viewer.discord_user_id or player.alignment != 'Evil':
                continue
            group = get_role_group(self._game.script, player.role_name)
            if group not in {'minions', 'demons'}:
                continue
            entries.append(
                {
                    'discord_user_id': player.discord_user_id,
                    'display_name': player.display_name,
                    'seat_label': f'Seat {player.seat + 1}',
                    'team_role': 'Demon' if group == 'demons' else 'Minion',
                }
            )
        return entries

    def get_player_state(self, discord_user_id: str, viewer_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            player = self._game.players[discord_user_id]
            public_state = self.get_public_state()
            current_step = self._get_night_step_locked(self._game.active_night_step_id)
            public_state['viewer'] = self._serialize_player_private(player)
            public_state['viewer_evil_team'] = self._serialize_evil_team_locked(player)
            public_state['viewer_context'] = {
                'requested_player_id': discord_user_id,
                'viewer_id': viewer_id or discord_user_id,
                'is_preview': bool(viewer_id and viewer_id != discord_user_id),
            }
            public_state['current_night_step'] = self._serialize_night_step(current_step)
            public_state['viewer_demon_bluffs'] = list(self._game.demon_bluffs) if is_demon_role(self._game.script, player.role_name) else []
            public_state['viewer_grimoire'] = [
                self._serialize_grimoire_entry_for_player(seated_player)
                for seated_player in sorted(self._game.players.values(), key=lambda seated: seated.seat)
            ] if self._viewer_can_see_grimoire_locked(player, current_step) else None
            return public_state

    def get_storyteller_state(self) -> dict[str, Any]:
        with self._lock:
            players = sorted(self._game.players.values(), key=lambda player: player.seat)
            lobby_players = self.list_lobby_players()
            available_statuses = get_game_status_options([player.role_name for player in players])
            return {
                'game_id': self._game.game_id,
                'name': self._game.name,
                'script': self._game.script,
                'script_reference': get_script_reference(self._game.script),
                'phase': self._game.phase.value,
                'storyteller_id': self._game.storyteller_id,
                'available_statuses': available_statuses,
                'available_demon_bluffs': self.list_available_demon_bluffs(),
                'demon_bluffs': list(self._game.demon_bluffs),
                'players': [self._serialize_player_storyteller(player) for player in players],
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









































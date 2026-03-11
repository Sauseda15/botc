from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import RLock
from typing import Any
import secrets
import uuid

from config import settings
from content import build_night_prompt, get_script_reference, infer_alignment


UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


class GamePhase(str, Enum):
    SETUP = 'setup'
    NIGHT = 'night'
    DAY = 'day'
    FINISHED = 'finished'


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


class GameStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._game = GameRecord()
        self._sessions: dict[str, WebSession] = {}
        self._oauth_states: dict[str, dict[str, Any]] = {}
        self._lobby_players: dict[str, LobbyPlayer] = {}

    def _touch(self) -> None:
        self._game.updated_at = utcnow()

    def reset_game(self) -> None:
        with self._lock:
            self._game = GameRecord()

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
                return
            existing = self._lobby_players.get(discord_user_id)
            if existing:
                existing.display_name = display_name
                return
            self._lobby_players[discord_user_id] = LobbyPlayer(
                discord_user_id=discord_user_id,
                display_name=display_name,
            )

    def remove_lobby_player(self, discord_user_id: str) -> None:
        with self._lock:
            self._lobby_players.pop(discord_user_id, None)

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
                'created_at': utcnow(),
            }
            return state

    def consume_oauth_state(self, state: str) -> str:
        with self._lock:
            payload = self._oauth_states.pop(state, None)
            if not payload:
                raise KeyError('Invalid OAuth state')
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
                return None
            return session

    def delete_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            self._sessions.pop(session_id, None)

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
            return self._game

    def set_phase(self, actor_id: str, phase: GamePhase) -> GameRecord:
        with self._lock:
            self._game.phase = phase
            if phase == GamePhase.NIGHT:
                for player in self._game.players.values():
                    player.night_action_response = None
                    player.night_action_submitted_at = None
                    player.night_action_prompt = build_night_prompt(self._game.script, player.role_name, player.alignment, player.reminders)
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
            player.night_action_response = None
            player.night_action_submitted_at = None
            self._game.night_feed.append(f'{actor_id} set a night prompt for {player.display_name}.')
            self._touch()
            return player

    def submit_night_action(self, discord_user_id: str, response_text: str) -> GamePlayer:
        with self._lock:
            if self._game.phase != GamePhase.NIGHT:
                raise ValueError('Night actions can only be submitted during the night phase.')
            player = self._game.players[discord_user_id]
            player.night_action_response = response_text
            player.night_action_submitted_at = utcnow()
            player.private_history.append(f'Night action submitted: {response_text}')
            self._game.night_feed.append(f'{player.display_name} submitted a night action.')
            self._touch()
            return player

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
            }


store = GameStore()
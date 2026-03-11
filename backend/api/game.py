from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_optional_session, require_session, require_storyteller
from content import get_script_options
from state import GamePhase, WebSession, store

router = APIRouter(prefix='/api/game', tags=['game'])


class PlayerInput(BaseModel):
    discord_user_id: str
    display_name: str
    seat: int = Field(ge=0)
    is_alive: bool = True
    role_name: str | None = None
    alignment: str | None = None
    reminders: list[str] = Field(default_factory=list)
    private_history: list[str] = Field(default_factory=list)
    night_action_prompt: str | None = None
    night_action_response: str | None = None


class CreateGameRequest(BaseModel):
    name: str = 'Blood on the Clocktower'
    script: str = 'troubles_brewing'
    players: list[PlayerInput] = Field(default_factory=list)


class PhaseUpdateRequest(BaseModel):
    phase: GamePhase


class NominationRequest(BaseModel):
    nominator_id: str
    nominee_id: str


class VoteRequest(BaseModel):
    approve: bool


class AliveUpdateRequest(BaseModel):
    discord_user_id: str
    is_alive: bool


class StorytellerNoteRequest(BaseModel):
    message: str
    night: bool = False


class NightPromptRequest(BaseModel):
    discord_user_id: str
    prompt: str


class NightActionRequest(BaseModel):
    response: str


@router.get('/setup-options')
async def setup_options():
    return {'scripts': get_script_options()}


@router.get('/public')
async def public_state(session: WebSession | None = Depends(get_optional_session)):
    state = store.get_public_state()
    if session:
        state['session'] = {
            'discord_user_id': session.discord_user_id,
            'username': session.username,
            'is_storyteller': store.is_storyteller(session.discord_user_id) or (store.get_storyteller_id() is None),
            'is_player': session.discord_user_id in store.current_game().players,
        }
    return state


@router.get('/player')
async def player_state(
    as_player: str | None = Query(default=None),
    session: WebSession = Depends(require_session),
):
    requested_player_id = session.discord_user_id
    if as_player and as_player != session.discord_user_id:
        if not store.is_storyteller(session.discord_user_id):
            raise HTTPException(status_code=403, detail='Only storytellers can preview another player view.')
        requested_player_id = as_player

    if requested_player_id not in store.current_game().players:
        raise HTTPException(status_code=403, detail='You are not seated in the current game.')
    return store.get_player_state(requested_player_id, viewer_id=session.discord_user_id)


@router.get('/storyteller')
async def storyteller_state(session: WebSession = Depends(require_storyteller)):
    return store.get_storyteller_state()


@router.post('/storyteller/game')
async def create_game(payload: CreateGameRequest, session: WebSession = Depends(require_storyteller)):
    game = store.create_or_update_game(
        storyteller_id=session.discord_user_id,
        game_name=payload.name,
        script=payload.script,
        players=[player.model_dump() for player in payload.players],
    )
    return {
        'status': 'ok',
        'game_id': game.game_id,
        'public_state': store.get_public_state(),
        'storyteller_state': store.get_storyteller_state(),
    }


@router.post('/storyteller/phase')
async def update_phase(payload: PhaseUpdateRequest, session: WebSession = Depends(require_storyteller)):
    store.set_phase(session.discord_user_id, payload.phase)
    return store.get_storyteller_state()


@router.post('/storyteller/nomination')
async def start_nomination(payload: NominationRequest, session: WebSession = Depends(require_storyteller)):
    store.set_nomination(session.discord_user_id, payload.nominator_id, payload.nominee_id)
    return store.get_storyteller_state()


@router.post('/storyteller/alive')
async def update_alive(payload: AliveUpdateRequest, session: WebSession = Depends(require_storyteller)):
    store.set_player_alive(session.discord_user_id, payload.discord_user_id, payload.is_alive)
    return store.get_storyteller_state()


@router.post('/storyteller/note')
async def add_note(payload: StorytellerNoteRequest, session: WebSession = Depends(require_storyteller)):
    store.add_storyteller_note(session.discord_user_id, payload.message, night=payload.night)
    return store.get_storyteller_state()


@router.post('/storyteller/night-prompt')
async def set_night_prompt(payload: NightPromptRequest, session: WebSession = Depends(require_storyteller)):
    store.set_night_prompt(session.discord_user_id, payload.discord_user_id, payload.prompt)
    return store.get_storyteller_state()


@router.post('/player/vote')
async def cast_vote(payload: VoteRequest, session: WebSession = Depends(require_session)):
    store.cast_vote(session.discord_user_id, payload.approve)
    return store.get_player_state(session.discord_user_id, viewer_id=session.discord_user_id)


@router.post('/player/night-action')
async def submit_night_action(payload: NightActionRequest, session: WebSession = Depends(require_session)):
    if session.discord_user_id not in store.current_game().players:
        raise HTTPException(status_code=403, detail='You are not seated in the current game.')
    try:
        store.submit_night_action(session.discord_user_id, payload.response)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return store.get_player_state(session.discord_user_id, viewer_id=session.discord_user_id)
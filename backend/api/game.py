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


class StatusUpdateRequest(BaseModel):
    discord_user_id: str
    is_poisoned: bool | None = None
    is_drunk: bool | None = None
    pending_death: bool | None = None
    add_statuses: list[str] = Field(default_factory=list)
    remove_statuses: list[str] = Field(default_factory=list)


class StorytellerNoteRequest(BaseModel):
    message: str
    night: bool = False


class NightPromptRequest(BaseModel):
    discord_user_id: str
    prompt: str


class NightActionRequest(BaseModel):
    response: str
    target_player_id: str | None = None


class NightReadyRequest(BaseModel):
    target_player_id: str | None = None


class TestPlayersRequest(BaseModel):
    target_count: int = Field(ge=0, le=20)


class SeatLobbyPlayerRequest(BaseModel):
    discord_user_id: str
    seat: int = Field(ge=0)


class DemonBluffsRequest(BaseModel):
    bluffs: list[str] = Field(default_factory=list)


class NightAdvanceRequest(BaseModel):
    resolution_note: str | None = None
    death_target_ids: list[str] = Field(default_factory=list)
    poison_target_ids: list[str] = Field(default_factory=list)
    drunk_target_ids: list[str] = Field(default_factory=list)
    sober_target_ids: list[str] = Field(default_factory=list)
    healthy_target_ids: list[str] = Field(default_factory=list)


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


@router.post('/storyteller/test-players')
async def ensure_test_players(payload: TestPlayersRequest, session: WebSession = Depends(require_storyteller)):
    store.ensure_test_players(payload.target_count)
    return store.get_storyteller_state()


@router.post('/storyteller/test-players/clear')
async def clear_test_players(session: WebSession = Depends(require_storyteller)):
    store.clear_test_players()
    return store.get_storyteller_state()


@router.post('/storyteller/seat-lobby-player')
async def seat_lobby_player(payload: SeatLobbyPlayerRequest, session: WebSession = Depends(require_storyteller)):
    try:
        store.seat_lobby_player(session.discord_user_id, payload.discord_user_id, payload.seat)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return store.get_storyteller_state()


@router.post('/storyteller/demon-bluffs')
async def set_demon_bluffs(payload: DemonBluffsRequest, session: WebSession = Depends(require_storyteller)):
    try:
        store.set_demon_bluffs(session.discord_user_id, payload.bluffs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return store.get_storyteller_state()

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


@router.post('/storyteller/status')
async def update_status(payload: StatusUpdateRequest, session: WebSession = Depends(require_storyteller)):
    try:
        store.update_player_status(
            session.discord_user_id,
            payload.discord_user_id,
            is_poisoned=payload.is_poisoned,
            is_drunk=payload.is_drunk,
            pending_death=payload.pending_death,
            add_statuses=payload.add_statuses,
            remove_statuses=payload.remove_statuses,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return store.get_storyteller_state()


@router.post('/storyteller/note')
async def add_note(payload: StorytellerNoteRequest, session: WebSession = Depends(require_storyteller)):
    store.add_storyteller_note(session.discord_user_id, payload.message, night=payload.night)
    return store.get_storyteller_state()


@router.post('/storyteller/night-prompt')
async def set_night_prompt(payload: NightPromptRequest, session: WebSession = Depends(require_storyteller)):
    store.set_night_prompt(session.discord_user_id, payload.discord_user_id, payload.prompt)
    return store.get_storyteller_state()


@router.post('/storyteller/night/advance')
async def advance_night(payload: NightAdvanceRequest, session: WebSession = Depends(require_storyteller)):
    try:
        return store.advance_night_step(
            session.discord_user_id,
            payload.resolution_note,
            death_target_ids=payload.death_target_ids,
            poison_target_ids=payload.poison_target_ids,
            drunk_target_ids=payload.drunk_target_ids,
            sober_target_ids=payload.sober_target_ids,
            healthy_target_ids=payload.healthy_target_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/storyteller/night/approve')
async def approve_night(payload: NightAdvanceRequest, session: WebSession = Depends(require_storyteller)):
    try:
        return store.approve_night_step(
            session.discord_user_id,
            payload.resolution_note,
            death_target_ids=payload.death_target_ids,
            poison_target_ids=payload.poison_target_ids,
            drunk_target_ids=payload.drunk_target_ids,
            sober_target_ids=payload.sober_target_ids,
            healthy_target_ids=payload.healthy_target_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/player/vote')
async def cast_vote(payload: VoteRequest, session: WebSession = Depends(require_session)):
    store.cast_vote(session.discord_user_id, payload.approve)
    return store.get_player_state(session.discord_user_id, viewer_id=session.discord_user_id)


@router.post('/player/night-action')
async def submit_night_action(payload: NightActionRequest, session: WebSession = Depends(require_session)):
    target_player_id = session.discord_user_id
    if payload.target_player_id and payload.target_player_id != session.discord_user_id:
        if not store.is_storyteller(session.discord_user_id):
            raise HTTPException(status_code=403, detail='Only storytellers can submit a test action for another player.')
        target_player_id = payload.target_player_id

    if target_player_id not in store.current_game().players:
        raise HTTPException(status_code=403, detail='That player is not seated in the current game.')

    try:
        store.submit_night_action(target_player_id, payload.response)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return store.get_player_state(target_player_id, viewer_id=session.discord_user_id)


@router.post('/player/night-ready')
async def signal_night_ready(payload: NightReadyRequest, session: WebSession = Depends(require_session)):
    target_player_id = session.discord_user_id
    if payload.target_player_id and payload.target_player_id != session.discord_user_id:
        if not store.is_storyteller(session.discord_user_id):
            raise HTTPException(status_code=403, detail='Only storytellers can mark another player ready in preview mode.')
        target_player_id = payload.target_player_id

    if target_player_id not in store.current_game().players:
        raise HTTPException(status_code=403, detail='That player is not seated in the current game.')

    try:
        store.signal_night_step_ready(target_player_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return store.get_player_state(target_player_id, viewer_id=session.discord_user_id)









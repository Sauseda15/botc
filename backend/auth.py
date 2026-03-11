from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from config import settings
from state import WebSession, store

router = APIRouter(prefix='/api/auth', tags=['auth'])

DISCORD_AUTHORIZE_URL = 'https://discord.com/oauth2/authorize'
DISCORD_TOKEN_URL = 'https://discord.com/api/oauth2/token'
DISCORD_ME_URL = 'https://discord.com/api/users/@me'
DEFAULT_HEADERS = {
    'Accept': 'application/json',
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/133.0.0.0 Safari/537.36'
    ),
}


def _has_storyteller_access(discord_user_id: str) -> bool:
    if store.is_storyteller(discord_user_id):
        return True
    return store.get_storyteller_id() is None and not settings.storyteller_ids


def _parse_error_body(exc: HTTPError) -> str:
    try:
        body = exc.read().decode('utf-8')
    except Exception:
        return exc.reason if hasattr(exc, 'reason') else str(exc)
    return body or (exc.reason if hasattr(exc, 'reason') else str(exc))


def _frontend_cookie_settings() -> tuple[bool, str]:
    parsed = urlparse(settings.frontend_base_url)
    is_local = parsed.hostname in {'localhost', '127.0.0.1'}
    return (not is_local, 'none' if not is_local else 'lax')


def _discord_post_form(url: str, form_data: dict[str, str]) -> dict:
    request = UrlRequest(
        url,
        data=urlencode(form_data).encode('utf-8'),
        headers={
            **DEFAULT_HEADERS,
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        raise HTTPException(
            status_code=400,
            detail=f'Discord token exchange failed ({exc.code}): {_parse_error_body(exc)}',
        ) from exc


def _discord_get_json(url: str, access_token: str) -> dict:
    request = UrlRequest(
        url,
        headers={
            **DEFAULT_HEADERS,
            'Authorization': f'Bearer {access_token}',
        },
        method='GET',
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        raise HTTPException(
            status_code=400,
            detail=f'Discord user lookup failed ({exc.code}): {_parse_error_body(exc)}',
        ) from exc


async def get_optional_session(request: Request) -> WebSession | None:
    session_id = request.cookies.get(settings.session_cookie_name)
    return store.get_session(session_id)


async def require_session(session: WebSession | None = Depends(get_optional_session)) -> WebSession:
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Login required.')
    return session


async def require_storyteller(session: WebSession = Depends(require_session)) -> WebSession:
    if not _has_storyteller_access(session.discord_user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Storyteller access required.')
    return session


@router.get('/login')
async def login(next: str = '/'):
    if not settings.discord_oauth_ready:
        raise HTTPException(status_code=503, detail='Discord OAuth is not configured.')

    state = store.issue_oauth_state(next)
    query = urlencode(
        {
            'client_id': settings.discord_client_id,
            'redirect_uri': settings.discord_redirect_uri,
            'response_type': 'code',
            'scope': 'identify',
            'state': state,
            'prompt': 'consent',
        }
    )
    return RedirectResponse(url=f'{DISCORD_AUTHORIZE_URL}?{query}', status_code=302)


@router.get('/callback')
async def callback(code: str, state: str):
    if not settings.discord_oauth_ready:
        raise HTTPException(status_code=503, detail='Discord OAuth is not configured.')

    try:
        next_path = store.consume_oauth_state(state)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail='Invalid OAuth state.') from exc

    token_payload = _discord_post_form(
        DISCORD_TOKEN_URL,
        {
            'client_id': settings.discord_client_id or '',
            'client_secret': settings.discord_client_secret or '',
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': settings.discord_redirect_uri,
        },
    )
    access_token = token_payload.get('access_token')
    if not access_token:
        raise HTTPException(status_code=400, detail='Discord did not return an access token.')

    user_payload = _discord_get_json(DISCORD_ME_URL, access_token)
    session = store.create_session(
        discord_user_id=str(user_payload['id']),
        username=user_payload['username'],
        avatar_hash=user_payload.get('avatar'),
    )

    secure_cookie, same_site = _frontend_cookie_settings()
    redirect = RedirectResponse(url=f"{settings.frontend_base_url}{next_path}", status_code=302)
    redirect.set_cookie(
        key=settings.session_cookie_name,
        value=session.session_id,
        httponly=True,
        secure=secure_cookie,
        samesite=same_site,
        max_age=settings.session_duration_hours * 60 * 60,
    )
    return redirect


@router.get('/me')
async def me(session: WebSession | None = Depends(get_optional_session)):
    if not session:
        return {'authenticated': False}

    is_storyteller = _has_storyteller_access(session.discord_user_id)
    if not is_storyteller:
        store.register_lobby_player(session.discord_user_id, session.username)

    player = store.current_game().players.get(session.discord_user_id)
    return {
        'authenticated': True,
        'user': {
            'discord_user_id': session.discord_user_id,
            'username': session.username,
            'avatar_hash': session.avatar_hash,
            'is_storyteller': is_storyteller,
            'is_player': bool(player),
        },
    }


@router.post('/logout')
async def logout(request: Request):
    session_id = request.cookies.get(settings.session_cookie_name)
    store.delete_session(session_id)
    secure_cookie, same_site = _frontend_cookie_settings()
    response = Response(status_code=204)
    response.delete_cookie(settings.session_cookie_name, secure=secure_cookie, samesite=same_site)
    return response
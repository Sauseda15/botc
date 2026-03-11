from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import game as game_router
from auth import router as auth_router
from config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title='BOTC Control Layer')

allowed_origins = [
    settings.frontend_base_url,
    'http://localhost:3000',
    'http://localhost:5173',
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(allowed_origins)),
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router)
app.include_router(game_router.router)

FRONTEND_DIST = Path(__file__).resolve().parent.parent / 'frontend' / 'dist'
FRONTEND_INDEX = FRONTEND_DIST / 'index.html'
ASSETS_DIR = FRONTEND_DIST / 'assets'

if ASSETS_DIR.exists():
    app.mount('/assets', StaticFiles(directory=ASSETS_DIR), name='frontend-assets')

bot_task: asyncio.Task | None = None
bot_instance = None


async def run_discord_bot() -> None:
    global bot_instance
    try:
        from discord_bot.bot import bot, setup_bot

        bot_instance = bot
        await setup_bot()
        await bot.start(settings.discord_token)
    except Exception:
        logger.exception('Discord bot failed to start.')


@app.on_event('startup')
async def startup_event() -> None:
    global bot_task
    if settings.bot_ready and bot_task is None:
        bot_task = asyncio.create_task(run_discord_bot())
    else:
        logger.info('Discord bot startup skipped. Configure ENABLE_DISCORD_BOT=true and a valid DISCORD_TOKEN to enable it.')


@app.on_event('shutdown')
async def shutdown_event() -> None:
    if bot_instance is not None and bot_instance.is_ready():
        await bot_instance.close()


@app.get('/')
async def root():
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    return {'message': 'BOTC backend is running'}


@app.get('/{full_path:path}')
async def spa_fallback(full_path: str):
    if full_path.startswith('api'):
        return {'detail': 'Not found'}
    candidate = FRONTEND_DIST / full_path
    if candidate.exists() and candidate.is_file():
        return FileResponse(candidate)
    if FRONTEND_INDEX.exists():
        return FileResponse(FRONTEND_INDEX)
    return {'message': 'BOTC backend is running'}


if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=8000, reload=True)
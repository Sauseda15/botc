import logging
import discord
import asyncio

logger = logging.getLogger(__name__)

async def handle_interaction_error(exception):
    if isinstance(exception, discord.HTTPException):
        if exception.status == 400:
            retry_after = exception.retry_after
            logger.warning(f'HTTPException occurred. Retrying after {retry_after} seconds')
            await asyncio.sleep(retry_after)
        else:
            logger.error('HTTPException occurred')

def setup_logging():
    logging.basicConfig(level=logging.INFO)
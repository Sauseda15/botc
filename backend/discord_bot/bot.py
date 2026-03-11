import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.dm_messages = True

bot = commands.Bot(command_prefix='/', intents=intents)

synced = False


@bot.event
async def on_ready():
    global synced
    if not synced:
        await bot.tree.sync()
        synced = True


async def setup_bot():
    from .cogs.control_cog import setup

    await setup(bot)

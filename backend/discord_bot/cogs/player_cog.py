import discord
from discord.ext import commands
from .game_cog import active_game_cog

class PlayerCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def get_game(self):
        if active_game_cog and active_game_cog.games:
            return list(active_game_cog.games.values())[0]
        return None

    @commands.hybrid_command(name='status', aliases=['s'], brief='Check whether a game is active')
    async def player_status(self, ctx: commands.Context) -> None:
        game = self.get_game()
        if not game:
            await ctx.send("❌ There is no active game.")
            return

        await ctx.send(
            f"✅ A game is active.\n"
            f"Started: {game.is_started}\n"
            f"Players: {len(game.players)}\n"
            f"State: {game.game_state.name}"
        )

def setup(bot: commands.Bot):
    bot.add_cog(PlayerCog(bot))
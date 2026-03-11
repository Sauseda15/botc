from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from state import GamePhase, store


def _is_bootstrap_storyteller(discord_user_id: str) -> bool:
    return store.get_storyteller_id() is None and not store.current_game().players


class ControlCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _has_storyteller_access(self, discord_user_id: int) -> bool:
        user_id = str(discord_user_id)
        return store.is_storyteller(user_id) or _is_bootstrap_storyteller(user_id)

    async def _require_storyteller(self, interaction: discord.Interaction) -> bool:
        if self._has_storyteller_access(interaction.user.id):
            return True
        await interaction.response.send_message('Storyteller access is required for this command.', ephemeral=True)
        return False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f'Logged in as {self.bot.user} (ID: {self.bot.user.id})')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return

        player = store.get_player(str(message.author.id))
        if not player:
            return
        if store.current_game().phase != GamePhase.NIGHT:
            return

        transcript = message.content.strip()
        if not transcript:
            return

        store.add_private_history(player.discord_user_id, f'Night response: {transcript}')
        store.add_storyteller_note(player.discord_user_id, f'{player.display_name}: {transcript}', night=True)
        await message.add_reaction('🌙')

    @app_commands.command(name='claim_storyteller', description='Claim storyteller access for the current BOTC game.')
    async def claim_storyteller(self, interaction: discord.Interaction) -> None:
        if store.get_storyteller_id() and not store.is_storyteller(str(interaction.user.id)):
            await interaction.response.send_message('A storyteller has already been assigned in the backend.', ephemeral=True)
            return

        store.set_storyteller_id(str(interaction.user.id))
        await interaction.response.send_message('You now have storyteller access in Discord and on the website.', ephemeral=True)

    @app_commands.command(name='game_status', description='Show the current BOTC backend status.')
    async def game_status(self, interaction: discord.Interaction) -> None:
        game = store.current_game()
        players = store.list_players()
        lines = [
            f'Game: {game.name}',
            f'Script: {game.script}',
            f'Phase: {game.phase.value}',
            f'Storyteller: {game.storyteller_id or "unclaimed"}',
            f'Seated players: {len(players)}',
        ]
        if players:
            lines.append('Seats: ' + ', '.join(f'{player.seat}:{player.display_name}' for player in players))
        await interaction.response.send_message('\n'.join(lines), ephemeral=True)

    @app_commands.command(name='send_roles', description='DM each seated player their role from the shared backend state.')
    async def send_roles(self, interaction: discord.Interaction) -> None:
        if not await self._require_storyteller(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        delivered = 0
        failed: list[str] = []
        game = store.current_game()

        for player in store.list_players():
            user = self.bot.get_user(int(player.discord_user_id)) or await self.bot.fetch_user(int(player.discord_user_id))
            if not user:
                failed.append(player.display_name)
                continue
            try:
                role_line = player.role_name or 'Role not assigned yet'
                alignment_line = player.alignment or 'Alignment not assigned yet'
                reminders = '\n'.join(f'- {item}' for item in player.reminders) if player.reminders else '- None'
                await user.send(
                    f'Game: {game.name}\n'
                    f'Script: {game.script}\n'
                    f'Your role: {role_line}\n'
                    f'Alignment: {alignment_line}\n'
                    f'Reminders:\n{reminders}'
                )
                delivered += 1
                store.add_private_history(player.discord_user_id, 'Role DM delivered in Discord.')
            except discord.Forbidden:
                failed.append(player.display_name)

        summary = f'Role DMs sent to {delivered} player(s).'
        if failed:
            summary += ' Failed: ' + ', '.join(failed)
        await interaction.followup.send(summary, ephemeral=True)

    @app_commands.command(name='begin_night', description='Move the game to night and DM alive players to check Discord.')
    async def begin_night(self, interaction: discord.Interaction) -> None:
        if not await self._require_storyteller(interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        store.set_phase(str(interaction.user.id), GamePhase.NIGHT)
        prompted = 0
        failed: list[str] = []

        for player in store.list_players():
            if not player.is_alive:
                continue
            user = self.bot.get_user(int(player.discord_user_id)) or await self.bot.fetch_user(int(player.discord_user_id))
            if not user:
                failed.append(player.display_name)
                continue
            try:
                reminders = '\n'.join(f'- {item}' for item in player.reminders) if player.reminders else '- None'
                await user.send(
                    'Night has begun. Reply in this DM with your action or question for the storyteller.\n'
                    f'Role: {player.role_name or "Unassigned"}\n'
                    f'Reminders:\n{reminders}'
                )
                prompted += 1
                store.add_private_history(player.discord_user_id, 'Night prompt delivered in Discord.')
            except discord.Forbidden:
                failed.append(player.display_name)

        summary = f'Night started. Prompted {prompted} alive player(s).'
        if failed:
            summary += ' Failed: ' + ', '.join(failed)
        await interaction.followup.send(summary, ephemeral=True)

    @app_commands.command(name='begin_day', description='Move the game to day in the shared backend state.')
    async def begin_day(self, interaction: discord.Interaction) -> None:
        if not await self._require_storyteller(interaction):
            return
        store.set_phase(str(interaction.user.id), GamePhase.DAY)
        await interaction.response.send_message('Game phase set to day.', ephemeral=True)

    @app_commands.command(name='night_prompt', description='Send a private custom prompt to one seated player.')
    @app_commands.describe(player='The seated player to message', prompt='The message to send privately')
    async def night_prompt(self, interaction: discord.Interaction, player: discord.User, prompt: str) -> None:
        if not await self._require_storyteller(interaction):
            return

        game_player = store.get_player(str(player.id))
        if not game_player:
            await interaction.response.send_message('That Discord user is not seated in the current game.', ephemeral=True)
            return

        try:
            await player.send(f'Storyteller prompt: {prompt}')
            store.add_private_history(game_player.discord_user_id, f'Storyteller prompt: {prompt}')
            store.add_storyteller_note(str(interaction.user.id), f'Prompted {game_player.display_name}: {prompt}', night=True)
            await interaction.response.send_message(f'Prompt sent to {game_player.display_name}.', ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(f'Could not DM {game_player.display_name}.', ephemeral=True)

    @app_commands.command(name='set_reminders', description='Update reminder tokens/notes for one seated player.')
    @app_commands.describe(player='The seated player to update', reminders='Comma-separated reminders')
    async def set_reminders(self, interaction: discord.Interaction, player: discord.User, reminders: str) -> None:
        if not await self._require_storyteller(interaction):
            return

        game_player = store.get_player(str(player.id))
        if not game_player:
            await interaction.response.send_message('That Discord user is not seated in the current game.', ephemeral=True)
            return

        parsed = [item.strip() for item in reminders.split(',') if item.strip()]
        store.set_player_reminders(str(interaction.user.id), game_player.discord_user_id, parsed)
        await interaction.response.send_message(
            f'Reminders updated for {game_player.display_name}: ' + (', '.join(parsed) if parsed else 'none'),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    if not bot.get_cog('ControlCog'):
        await bot.add_cog(ControlCog(bot))

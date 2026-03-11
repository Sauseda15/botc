import discord
from discord.ext import commands
from views import BaseView

class PlayerSelectionView(BaseView):
    def __init__(self, game, player, placeholder, max_values=1):
        super().__init__(timeout=None)
        self.game = game
        self.player = player
        self.max_values = max_values

        options = [
            discord.SelectOption(label=p.user.name, value=str(p.user.id))
            for p in game.players if p != player and p.is_alive()
        ]
        self.add_item(
            discord.ui.Select(
                placeholder=placeholder,
                options=options,
                max_values=max_values,
                custom_id="select_player"
            )
        )

    async def get_selected_players(self):
        selected_ids = await self.get_selected_value(multi=True)
        return [p for p in self.game.players if str(p.user.id) in selected_ids]


class RoleSelectionView(BaseView):
    def __init__(self, game, player, placeholder):
        super().__init__(timeout=None)
        self.game = game
        self.player = player

        options = [
            discord.SelectOption(label=role.name, value=role.name) for role in game.roles_in_play
        ]

        self.add_item(
            discord.ui.Select(
                placeholder=placeholder,
                options=options,
                custom_id="select_role"
            )
        )

    async def get_selected_role(self):
        return await self.get_selected_value()


class PlayerActionView(discord.ui.View):
    def __init__(self, game, player):
        super().__init__(timeout=None)
        self.game = game
        self.player = player

    @discord.ui.button(label="Perform Action", style=discord.ButtonStyle.blurple, custom_id='perform_action')
    async def perform_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Action performed!", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancel Action", style=discord.ButtonStyle.red, custom_id='cancel_action')
    async def cancel_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Action cancelled.", ephemeral=True)
        self.stop()
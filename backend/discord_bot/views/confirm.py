import discord
from .base import BaseView

class ConfirmView(BaseView):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player
        self.confirmed = None

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green, custom_id='confirm')
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.player.ability_used = True
        await interaction.response.send_message("Confirmed", ephemeral=True)
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red, custom_id='cancel')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        await interaction.response.send_message("Cancelled", ephemeral=True)
        self.stop()


class AllowView(BaseView):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player
        self.allowed = None

    @discord.ui.button(label="Allow", style=discord.ButtonStyle.green, custom_id='allow')
    async def allow(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.allowed = True
        await interaction.response.send_message("Allowed", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, custom_id='deny')
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.allowed = False
        await interaction.response.send_message("Denied", ephemeral=True)
        self.stop()

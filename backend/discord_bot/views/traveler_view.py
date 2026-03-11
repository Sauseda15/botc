from .base import BaseView
import discord
import random

class TravlerView(BaseView):
    def __init__(self, game, travler_player):
        super().__init__(timeout=None)
        self.game = game
        self.travler_player = travler_player
        self.numbers = [1, 2, 3]

        travler_options = [
            discord.SelectOption(label=number, value=number.id) for number in self.numbers
        ]

        self.add_item(
            discord.ui.Select(
                placeholder="Select a number",
                options=travler_options,
                custom_id="select_player"
            )
        )

    @discord.ui.button(label="Submit Player", style=discord.ButtonStyle.green, custom_id='submit_player')
    async def submit_player(self, button: discord.ui.Button, interaction: discord.Interaction):
        selected_number = self.children[0].values[0]
        random_number = random.choice(self.numbers)
        if selected_number == random_number:
            self.travler_player.alignment = "Evil"
            await self.traveler_player.send("You alignment is Evil")
        else:
            self.travler_player.alignment = "Good"
            await self.traveler_player.send("You alignment is Good")
        await interaction.response.send_message("Submitted", ephemeral=True)

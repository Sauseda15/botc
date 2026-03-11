import discord
from discord.ext import commands
from views import BaseView
from .player_selection import PlayerSelectionView

class DemonView(BaseView):
    def __init__(self, game, demon_player, lunatic=False, previous_target=None):
        super().__init__(timeout=None)
        self.game = game
        self.demon_player = demon_player
        self.previous_target = previous_target
        self.lunatic = lunatic
        self.true_demon = next((p for p in game.players if p.is_demon), None) if lunatic else None
        self.is_fang_gu = demon_player.role_instance.role == "Fang Gu"

        if previous_target:
            previous_target.is_dead = True
            previous_target.demon_killed = True
            previous_target.is_poisoned = False

        options = [
            discord.SelectOption(label=p.user.name, value=str(p.user.id)) for p in game.players
        ]

        self.add_item(
            discord.ui.Select(
                placeholder="Select a player to poison" if previous_target else "Select a player to kill",
                options=options,
                max_values=1,
                custom_id="select_player"
            )
        )

    @discord.ui.button(label="Submit Player", style=discord.ButtonStyle.green, custom_id='submit_player')
    async def submit_player(self, interaction: discord.Interaction, button: discord.ui.Button):
        selected_ids = await self.get_selected_value(multi=True)
        if not selected_ids:
            await interaction.response.send_message("You must select a player.", ephemeral=True)
            return

        selected_player = next((p for p in self.game.players if str(p.user.id) in selected_ids), None)
        if not selected_player:
            await interaction.response.send_message("Invalid selection.", ephemeral=True)
            return

        if selected_player.is_dead:
            await self.demon_player.send(f"{selected_player.user.name} is already dead.")
            return

        if self.previous_target is None:
            if self.is_fang_gu and selected_player.role in self.game.outsider_roles_in_play:
                selected_player.role_instance = self.demon_player.role_instance
                self.demon_player.is_dead = True
                await self.demon_player.send("You have killed yourself!")
                await selected_player.send("You are now the Fang Gu!")
            elif not selected_player.is_protected:
                selected_player.is_dead = True
                selected_player.demon_killed = True
                await self.demon_player.send(f"You have killed {selected_player.user.name}")
            if self.lunatic and self.true_demon:
                await self.true_demon.send(f"The lunatic has chosen to kill {selected_player.user.name}")
        else:
            selected_player.is_poisoned = True
            await self.demon_player.send(f"You have poisoned {selected_player.user.name}")

        await interaction.response.send_message("Submitted", ephemeral=True)


class MultiKillDemonView(BaseView):
    def __init__(self, game, demon_player, lunatic=False):
        super().__init__(timeout=None)
        self.game = game
        self.demon_player = demon_player
        self.lunatic = lunatic
        self.players_killed = []
        self.true_demon = next((p for p in game.players if p.is_demon), None) if lunatic else None

        demon_type = demon_player.role_instance.role
        max_kills = 3 if demon_type == "Po" else 2

        if demon_type == "Shabaloth":
            for p in game.players:
                if hasattr(p, "can_regurgitate"):
                    p.can_regurgitate = False

        options = [
            discord.SelectOption(label=p.user.name, value=str(p.user.id)) for p in game.players
        ]

        self.add_item(
            discord.ui.Select(
                placeholder="Select players to kill",
                options=options,
                max_values=max_kills,
                custom_id="select_player"
            )
        )

    @discord.ui.button(label="Submit Players", style=discord.ButtonStyle.green, custom_id='submit_players')
    async def submit_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        selected_ids = await self.get_selected_value(multi=True)
        if not selected_ids:
            await interaction.response.send_message("You must select players.", ephemeral=True)
            return

        selected_players = [p for p in self.game.players if str(p.user.id) in selected_ids]
        for p in selected_players:
            if not p.is_dead and not p.is_protected:
                p.is_dead = True
                p.demon_killed = True
                self.players_killed.append(p)
                if self.demon_player.role_instance.role == "Shabaloth" and hasattr(p, "can_regurgitate"):
                    p.can_regurgitate = True

        kill_list = ", ".join(p.user.name for p in self.players_killed)
        await self.demon_player.send(f"You have killed {kill_list}")

        if self.lunatic and self.true_demon:
            await self.true_demon.send(f"The lunatic has chosen to kill {kill_list}")

        await interaction.response.send_message("Submitted", ephemeral=True)

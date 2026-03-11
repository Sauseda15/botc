from roles import Minion
from ..views.player_selection import PlayerSelectionView
from ..views.confirm import ConfirmView
from ..views.demon_views import Devil_s_AdvocateView, WitchView, CerenovusView, PitHagView
import asyncio
import random

class Poisoner(Minion):
    async def perform_night_action(self, game):
        view = PlayerSelectionView(game, self.player, "Select a player to poison")
        await self.player.send("Select a player to poison:", view=view)
        await view.wait()
        selected_player = view.get_selected_player()
        if selected_player:
            selected_player.is_poisoned = True
            await self.player.send(f"{selected_player.user.name} has been poisoned.")


class Spy(Minion):
    async def perform_night_action(self, game):
        grimoire = {}
        for player in game.players:
            role_info = player.role_instance.role
            if player.is_drunk:
                role_info = "Drunk"
            elif player.is_poisoned:
                role_info = "Poisoned"
            elif player.is_protected:
                role_info = "Protected"
            grimoire[player.user.name] = role_info

        grimoire_message = await self.player.send(f"📜 Grimoire:\n" + '\n'.join(f"{k}: {v}" for k, v in grimoire.items()))
        await asyncio.sleep(20)
        await grimoire_message.delete()


class Mastermind(Minion):
    async def perform_night_action(self, game):
        pass  # Reserved for future logic


class Assassin(Minion):
    def __init__(self, player):
        super().__init__(player)
        self.ability_used = False

    async def perform_night_action(self, game):
        if not self.ability_used:
            confirm_view = ConfirmView(self.player)
            await self.player.send("Would you like to use your ability?", view=confirm_view)
            await confirm_view.wait()
            if confirm_view.confirmed:
                view = PlayerSelectionView(game, self.player, "Select a player to kill")
                await self.player.send("Select a player to kill:", view=view)
                await view.wait()
                selected_player = view.get_selected_player()
                if selected_player:
                    selected_player.is_dead = True
                    self.ability_used = True
                    await self.player.send(f"{selected_player.user.name} has been assassinated.")


class Devil_s_Advocate(Minion):
    def __init__(self, player):
        super().__init__(player)
        self.previous_player = None

    async def perform_night_action(self, game):
        view = Devil_s_AdvocateView(game, self.player, self.previous_player)
        await self.player.send("Select a player to protect from execution:", view=view)
        await view.wait()
        self.previous_player = view.get_selected_player()


class Godfather(Minion):
    async def perform_night_action(self, game):
        if game.night_number == 1:
            await self.player.send(f"🎭 Outsiders in play: {', '.join(game.outsiders_in_play)}")


class Evil_Twin(Minion):
    async def perform_night_action(self, game):
        if game.night_number == 1:
            random_townsfolk = random.choice(game.townsfolk_in_play)
            twin = next((p for p in game.players if p.role_instance == random_townsfolk), None)

            if twin:
                await self.player.send(
                    f"🔍 {random_townsfolk} is your twin ({twin.user.name}). "
                    "Your team wins only if they are executed."
                )
                await twin.send(
                    f"🧍 You are the Evil Twin of {self.player.user.name}. "
                    "Your team cannot win if both of you survive."
                )


class Witch(Minion):
    def __init__(self, player):
        super().__init__(player)
        self.previous_target = None

    async def perform_night_action(self, game):
        if len(game.players) > 3:
            view = WitchView(game, self.player, self.previous_target)
            await self.player.send("Select a player to Hex:", view=view)
            await view.wait()
            self.previous_target = view.get_selected_player()


class Cerenovous(Minion):
    def __init__(self, player):
        super().__init__(player)
        self.previous_target = None

    async def perform_night_action(self, game):
        view = CerenovusView(game, self.player, self.previous_target)
        await self.player.send("Select a player and a character to force them into:", view=view)
        await view.wait()
        self.previous_target = view.get_selected_player()


class Pit_Hag(Minion):
    async def perform_night_action(self, game):
        if game.night_number != 1:
            view = PitHagView(game, self.player)
            await self.player.send("Select a player and a role to transform into a Demon:", view=view)
            await view.wait()
            selected_player, selected_role = view.get_selected_player()
            selected_player.role_instance = selected_role
            await self.player.send(f"{selected_player.user.name} has been transformed into a Demon.")
            selected_player.is_transformed = True
            
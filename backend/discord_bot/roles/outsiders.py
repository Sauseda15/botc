from roles import Outsider
from ..views.player_selection import PlayerSelectionView
from ..views.confirm import ConfirmView
from views.views import BarberView
import random


class Butler(Outsider):
    def __init__(self, player):
        super().__init__(player)
        self.vote_tied_to = None

    async def perform_day_action(self, game):
        if self.vote_tied_to and hasattr(self.vote_tied_to, "has_voted"):
            self.player.live_vote = 1 if self.vote_tied_to.has_voted else 0

    async def perform_night_action(self, game):
        view = PlayerSelectionView(game, self.player, "Select a player to tie your vote to")
        await self.player.send("Select a player to tie your vote to:", view=view)
        await view.wait()
        selected_player = view.get_selected_player()
        if selected_player:
            self.vote_tied_to = selected_player


class Recluse(Outsider):
    async def perform_night_action(self, game):
        pass  # Does nothing


class Saint(Outsider):
    async def perform_day_action(self, game):
        if self.is_dead and game.player_executed_today == self.player:
            await game.end_game("evil")

    async def perform_night_action(self, game):
        pass  # Does nothing


class Tinker(Outsider):
    randomly_dies = True

    async def perform_night_action(self, game):
        pass  # Does nothing


class Moonchild(Outsider):
    async def perform_night_action(self, game):
        pass  # Reserved for future logic


class Goon(Outsider):
    visited = False

    async def perform_night_action(self, game):
        pass  # Reserved for future logic


class Sweetheart(Outsider):
    async def perform_night_action(self, game):
        if self.is_dead:
            alive_players = [p for p in game.players if not p.is_dead]
            if alive_players:
                chosen = random.choice(alive_players)
                chosen.is_drunk = True
                await self.player.send(f"{chosen.user.name} has been made drunk due to your death.")


class Mutant(Outsider):
    async def perform_night_action(self, game):
        pass  # Does nothing


class Barber(Outsider):
    def __init__(self, player):
        super().__init__(player)
        self.ability_used = False

    async def perform_night_action(self, game):
        if not self.ability_used:
            demon = next((p for p in game.players if p.is_demon), None)
            if demon:
                confirm_view = ConfirmView(demon)
                await demon.send("Would you like to swap roles tonight?", view=confirm_view)
                await confirm_view.wait()
                if confirm_view.confirmed:
                    view = BarberView(game, demon)
                    await demon.send("Select two players to swap roles:", view=view)
                    await view.wait()
                    # Role swap logic should be triggered here
                    self.ability_used = True


class Klutz(Outsider):
    async def perform_night_action(self, game):
        pass  # Reserved for future logic

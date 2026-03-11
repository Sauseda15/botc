from roles import Demon
from ..views.demon_views import DemonView, MultiKillDemonView
from ..views.confirm import ConfirmView

# === Base Demon Roles ===

class Imp(Demon):
    async def perform_night_action(self, game):
        view = DemonView(game, self.player)
        await self.player.send("Select a player to kill:", view=view)


class Shabaloth(Demon):
    async def perform_night_action(self, game):
        if game.night_number != 1:
            view = MultiKillDemonView(game, self.player)
            await self.player.send("Select two players to kill:", view=view)


class Po(Demon):
    def __init__(self, player):
        super().__init__(player)
        self.killed_last_night = False

    async def perform_night_action(self, game):
        if game.night_number == 1:
            return

        if self.killed_last_night:
            confirm_view = ConfirmView(self.player)
            await self.player.send("Would you like to use your ability?", view=confirm_view)
            await confirm_view.wait()
            if confirm_view.confirmed:
                view = DemonView(game, self.player, self.is_lunatic)
                await self.player.send("Select a player to kill:", view=view)
        else:
            view = MultiKillDemonView(game, self.player, self.is_lunatic)
            await self.player.send("Select three players to kill:", view=view)
            self.killed_last_night = True


class Zombuul(Demon):
    def __init__(self, player):
        super().__init__(player)
        self.ability_used = False
        self.is_dead = False

    async def perform_night_action(self, game):
        if game.night_number == 1:
            return

        if not self.ability_used and self.is_dead:
            self.is_dead = False
            self.ability_used = True

        if game.executed_player:
            view = DemonView(game, self.player, self.is_lunatic)
            await self.player.send("Select a player to kill:", view=view)


class Pukka(Demon):
    def __init__(self, player):
        super().__init__(player)
        self.previous_player = None

    async def perform_night_action(self, game):
        if game.night_number == 1:
            return

        view = DemonView(game, self.player, self.is_lunatic, self.previous_player)
        await self.player.send("Select a player to poison:", view=view)
        # You might want to store the selected player into `self.previous_player` if necessary
        # self.previous_player = selected_player


class Vortox(Demon):
    async def perform_night_action(self, game):
        if game.night_number != 1:
            for player in game.players:
                player.demon_vortox = True

            view = DemonView(game, self.player)
            await self.player.send("Select a player to kill:", view=view)


class FangGu(Demon):
    async def perform_night_action(self, game):
        if game.night_number != 1:
            view = DemonView(game, self.player)
            await self.player.send("Select a player to kill:", view=view)


class NoDashii(Demon):
    async def perform_night_action(self, game):
        if game.night_number != 1:
            view = DemonView(game, self.player)
            await self.player.send("Select a player to kill:", view=view)


class Vigormortis(Demon):
    async def perform_night_action(self, game):
        if game.night_number != 1:
            view = DemonView(game, self.player)
            await self.player.send("Select a player to kill:", view=view)

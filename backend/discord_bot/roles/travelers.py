# === Refactored Townsfolk & Traveler Roles ===
import random
from roles import Townsfolk, Traveler
from ..views.player_selection import PlayerSelectionView
from ..views.role_selection import RoleSelectionView
from ..views.confirm import ConfirmView
from ..views.barber_view import BarberView
from ..views.exorcist_view import ExorcistView
from ..views.gossip_view import GossipView
from ..views.professor_view import ProfessorView
from ..views.dreamer_view import DreamerView
from ..views.philosopher_view import PhilosopherView
from ..views.seamstress_view import SeamstressView
from ..views.bone_collector_view import BoneCollectorView
from ..views.beauracrat_view import BeauracratView
from ..views.harlot_view import HarlotView
from ..views.theif_view import TheifView

# ... [Townsfolk classes remain unchanged] ...

class Bone_Collector(Traveler):
    def __init__(self, player):
        super().__init__(player)
        self.ability_used = False

    async def perform_night_action(self, game):
        if game.night_number != 1 and game.dead_players and not self.ability_used:
            confirm_view = ConfirmView(self.player)
            await self.player.send("Use your Bone Collector ability?", view=confirm_view)
            await confirm_view.wait()
            if confirm_view.confirmed:
                self.ability_used = True
                view = BoneCollectorView(game, self.player)
                await self.player.send("Select a player to learn their role:", view=view)
                await view.wait()

class Bureaucrat(Traveler):
    def __init__(self, player):
        super().__init__(player)
        self.previous_target = None

    async def perform_night_action(self, game):
        view = BeauracratView(game, self.player, self.previous_target)
        await self.player.send("Choose a player to triple their vote tomorrow:", view=view)
        await view.wait()
        self.previous_target = view.get_selected_player()

class Harlot(Traveler):
    async def perform_night_action(self, game):
        if game.night_number != 1:
            view = HarlotView(game, self.player)
            await self.player.send("Choose a player to visit:", view=view)
            await view.wait()
            selected = view.get_selected_player()
            if selected:
                await self.player.send(f"{selected.user.name} is a {selected.role_instance.role}")

class Thief(Traveler):
    def __init__(self, player):
        super().__init__(player)
        self.previous_target = None

    async def perform_night_action(self, game):
        view = TheifView(game, self.player, self.previous_target)
        await self.player.send("Choose a player to make their vote negative:", view=view)
        await view.wait()
        self.previous_target = view.get_selected_player()

# Placeholder travelers to be implemented later
class Apprentice(Traveler):
    async def perform_night_action(self, game):
        pass

class Barista(Traveler):
    async def perform_night_action(self, game):
        pass

class Beggar(Traveler):
    async def perform_night_action(self, game):
        pass

class Bishop(Traveler):
    async def perform_night_action(self, game):
        pass

class Butcher(Traveler):
    async def perform_night_action(self, game):
        pass

class Deviant(Traveler):
    async def perform_night_action(self, game):
        pass

class Gunslinger(Traveler):
    async def perform_night_action(self, game):
        pass

class Judge(Traveler):
    async def perform_night_action(self, game):
        pass

class Matron(Traveler):
    async def perform_night_action(self, game):
        pass

class Scapegoat(Traveler):
    async def perform_night_action(self, game):
        pass

class Voudon(Traveler):
    async def perform_night_action(self, game):
        pass


from abc import ABC, abstractmethod


class BaseRole(ABC): # Abstract Base Class 
    def __init__(self, player):
        self.player = player
        self.init_flags()

    def init_flags(self):
        self.is_drunk = False
        self.drunk_count = 0
        self.is_poisoned = False
        self.is_protected = False
        self.is_dead = False
        self.dead_vote = 0
        self.live_vote = 1 
        self.is_exorcised = False
        self.wakes = False
        self.wake_order = 0
        self.can_regurgitate = False
        self.is_grandmothered = False
        self.demon_killed = False
        self.is_cerenovus = False
        self.is_pit_hagged = False
        self.demon_vortox = False
        self.bones_collected = False

    async def do_nothing(self, *args, **kwargs):
        pass

    async def perform_day_action(self, game):
        await self.do_nothing()

    async def perform_night_action(self, game):
        await self.do_nothing()

    @property
    def alignment(self):
        if isinstance(self, (Townsfolk, Outsider)):
            return "Good"
        elif isinstance(self, (Minion, Demon)):
            return "Evil"
        elif isinstance(self, Traveler):
            return getattr(self, "_alignment", None)
        return "Neutral"

class Townsfolk(BaseRole):
    def __init__(self, player):
        super().__init__(player)
        self.is_townsfolk = True

class Outsider(BaseRole):
    def __init__(self, player):
        super().__init__(player)
        self.is_outsider = True

class Minion(BaseRole):
    def __init__(self, player):
        super().__init__(player)
        self.is_minion = True

class Demon(BaseRole):
    def __init__(self, player):
        super().__init__(player)
        self.is_demon = True

class Traveler(BaseRole):
    def __init__(self, player):
        super().__init__(player)
        self.alignment = None 
        self.is_traveler = True
        self.is_exiled = False
    
    async def get_alignment(self, game):
        from views.traveler_view import TravelerView
        view = TravelerView(game, self.player)
        await self.player.send("Select a number to determine your alignment:", view=view)
        await view.wait()
## Trouble's Brewing ##
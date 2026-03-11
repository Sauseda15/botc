# === Refactored Townsfolk Roles ===
import random
from roles import Townsfolk
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

class Chef(Townsfolk):
    async def perform_night_action(self, game, night_number):
        if night_number == 1:
            pairs = 0
            players = game.players  # List of players in the game

            # Iterate through players and check adjacent pairs
            for i in range(len(players)):
                current_player = players[i]
                next_player = players[(i + 1) % len(players)]  # Wrap around

                # Check if both current and next player are minions or demons
                if (current_player.is_imp or current_player.is_minion) and (next_player.is_imp or next_player.is_minion):
                    pairs += 1

            # Send result to the Chef player
            await self.player.send(f"Pairs of evil players: {pairs}")

class Librarian(Townsfolk):
    async def perform_night_action(self, game, night_number, outsiders_in_play):
        possible_outsiders = []
        if night_number == 1:
            random_outsider = random.choice(outsiders_in_play)
            for player in game.players:
                if player.role_instance == random_outsider:
                    possible_outsiders.append(player)
            random_player = random.choice(game.players)
            possible_outsiders.append(random_player)
            await self.player.send(f"Outsider: {random_outsider} is either {possible_outsiders[0]} or {possible_outsiders[1]}")
        pass

class Washerwoman(Townsfolk):
    async def perform_night_action(self, game, night_number, townsfolk_in_play):
        possible_townsfolk = []
        if night_number == 1:
            random_townsfolk = random.choice(townsfolk_in_play)
            for player in game.players:
                if player.role_instance == random_townsfolk:
                    possible_townsfolk.append(player)
            random_player = random.choice(game.players)
            possible_townsfolk.append(random_player)
            await self.player.send(f"Townsfolk: {random_townsfolk} is either {possible_townsfolk[0]} or {possible_townsfolk[1]}")
        pass

class Investigator(Townsfolk):
    async def perform_night_action(self, game, minions_in_play, night_number):
        # Perform the night action for the investigator
        if night_number == 1:
            possible_minions = []
            random_minion = random.choice(minions_in_play)
            for player in game.players:
                if player.role_instance == random_minion:
                    possible_minions.append(player)
            random_player = random.choice(game.players.remove(possible_minions[0]))
            possible_minions.append(random_player)
            await self.player.send(f"Minion: {random_minion} is either {possible_minions[0]} or {possible_minions[1]}")
        pass

            ## CONDITIONAL ##

class Undertaker(Townsfolk):
    async def perform_night_action(self, game, night_number, dead_players):
        if night_number > 1:
            if len(dead_players) == 0:
                await self.player.send("No dead players to investigate.")
            else:
                view = UndertakerView(dead_players, game, self.player)
                await self.player.send("Select a dead player to learn their role:", view=view)
        pass

class Ravenkeeper(Townsfolk):
    async def perform_night_action(self, game, imp_kill):
        if imp_kill:
            view = RavekeeperView(game, imp_kill, self.player)
            await self.player.send("Select a player to learn their role:", view=view)
        pass

            ## INFORMATIONAL ##

class Monk(Townsfolk):
    async def perform_night_action(self, game, night_number):
        if night_number > 1:
            view = MonkView(game, self.player)
            await self.player.send("Select a player to protect:", view=view)
        pass

class Empath(Townsfolk):
    async def perform_night_action(self, game, players):
        # Perform the night action for the empath
        placesetting = self.player.numerical_value
        # Initialize neighbor alignments
        upper_neighbor_alignment = None
        lower_neighbor_alignment = None
        # Find upper neighbor
        upper_neighbor = placesetting + 1
        while upper_neighbor_alignment is None:
            if upper_neighbor > len(players):
                upper_neighbor = 1  # Wrap around to the first player
            found_upper = False
            for player in players:
                if player.numerical_value == upper_neighbor:
                    if not player.is_dead:  # Check if the player is alive
                        upper_neighbor_alignment = player.role_instance.alignment
                        found_upper = True
                        break
            if not found_upper:  # If no living player found, continue searching
                upper_neighbor += 1
        # Find lower neighbor
        lower_neighbor = placesetting - 1
        while lower_neighbor_alignment is None:
            if lower_neighbor < 1:
                lower_neighbor = len(players)  # Wrap around to the last player
            found_lower = False
            for player in players:
                if player.numerical_value == lower_neighbor:
                    if not player.is_dead:  # Check if the player is alive
                        lower_neighbor_alignment = player.role_instance.alignment
                        found_lower = True
                        break
            if not found_lower:  # If no living player found, continue searching
                lower_neighbor -= 1
        # Count bad neighbors
        bad_neighbors = 0
        if upper_neighbor_alignment == "Evil":
            bad_neighbors += 1
        if lower_neighbor_alignment == "Evil":
            bad_neighbors += 1
        await self.player.send(f"Number of evil neighbors: {bad_neighbors}")
        pass

class FortuneTeller(Townsfolk):
    async def perform_night_action(self, game):
        # Perform the night action for the fortune teller
        view = FortuneTellerView(game, self.player)
        await self.player.send("Select two player to learn if one of them are the Imp:", view=view)
        pass

class Soldier(Townsfolk):
    async def perform_night_action(self, game):
        #Does Nothing
        pass

class Mayor(Townsfolk):
    async def perform_night_action(self, game):
        # Does Nothing
        pass

class Virgin(Townsfolk):
    async def perform_night_action(self, game):
        # Does Nothing
        pass

class Slayer(Townsfolk):
    async def perform_night_action(self, game):
        # Does Nothing 
        pass

class Tea_Lady(Townsfolk):
    async def perform_night_action(self, game):
        # Does Nothing
        pass

class Courtier(Townsfolk):
    async def perform_night_action(self, game):
        # Perform the night action for the courtier
        if not self.player.ability_used:
            view = CourtierView(game, self.player)
            await self.player.send("Select a player to make them drunk for 3 days/3 nights:", view=view)

        pass

class Gambler(Townsfolk):
    async def perform_night_action(self, game, night_number):
        # Perform the night action for the gambler
        if night_number != 1:
            view = GamblerView(game, self.player)
            await self.player.send("Select a player to gamble with:", view=view)
        pass

class Innkeeper(Townsfolk):
    async def perform_night_action(self, game, night_number):
        # Perform the night action for the innkeeper
        if night_number != 1:
            view = InnkeeperView(game, self.player)
            await self.player.send("Select two players to protect:", view=view)
        pass

class Exorcist(Townsfolk):
    previous_target = None
    async def perform_night_action(self, game, night_number):
        # Perform the night action for the exorcist
        if night_number != 1:
            view = ExorcistView(game, self.player, self.previous_target)
            await self.player.send("Select a player to exorcise:", view=view)
        pass

class Sailor(Townsfolk):
    async def perform_night_action(self, game):
        # Perform the night action for the sailor
        view = SailorView(game, self.player)
        await self.player.send("Select a player:", view=view)
        pass

class Grandmother(Townsfolk):
    async def perform_night_action(self, game, night_number, townsfolk_in_play):
        # Perform the night action for the grandmother
        if night_number == 1:
            # Send a message to the player
            random_townsfolk = random.choice(townsfolk_in_play)
            for player in game.players:
                if player.role_instance == random_townsfolk:
                    player.is_grandmothered = True
                    await self.player.send(f"Townsfolk: {random_townsfolk} is {player}, if they die you will die too.")
        pass

class Fool(Townsfolk):
    ability_used = False
    async def perform_night_action(self, game):
        # Does Nothing
        pass

class Pacifist(Townsfolk):
    async def perform_night_action(self, game):
        # Does Nothing
        pass

class Minstrel(Townsfolk):
    async def perform_night_action(self, game, player_executed):
        # Perform the night action for the minstrel
        if player_executed.role_type == "Minion": # Check if the executed player was a minion, if so all players are drunk
            for player in game.players:
                player.is_drunk = True
                player.drunk_count = 1
        pass

class Professor(Townsfolk):
    ability_used = False
    async def perform_night_action(self, game, dead_players):
        if not self.ability_used:
            confirm_view = ConfirmView(self.player)
            use_ability = await self.player.send("Would you like to use your ability?", view=confirm_view)
            if use_ability:
                view = ProfessorView(game, self.player, dead_players)
                await self.player.send("Select a Townsfolk to resurrect:", view=view)
        pass

class Gossip(Townsfolk):
    gossip_true = False
    async def perform_night_action(self, game):
        # Does Nothing
        pass

class Chambermaid(Townsfolk):
    async def perform_night_action(self, game):
        view = ChambermaidView(game, self.player)
        await self.player.send("Select two players to see how many wake:", view=view)
        pass

class Dreamer(Townsfolk):
    async def perform_night_action(self, game):
        # Perform the night action for the dreamer
        view = DreamerView(game, self.player)
        await self.player.send("Select a player to learn their role:", view=view)
        pass

class Snake_Charmer(Townsfolk):
    async def perform_night_action(self, game):
        view = SnakeCharmerView(game, self.player)
        await self.player.send("Select a player to charm:", view=view)
        pass

class Mathematician(Townsfolk): #COME BACK LATER
    def __init__(self, player):
        super().__init__(player)
        self.abnoramlitys_detected = 0
    async def perform_night_action(self, game):
        # Perform the night action for the mathematician
        if self.abnoramlitys_detected == 0:
            await self.player.send("No abnormalities detected.")
        else:
            await self.player.send(f"{self.abnoramlitys_detected} abnormalities detected.")
        pass

class Flowergirl(Townsfolk):
    async def perform_night_action(self, game):
        # Perform the night action for the flowergirl
        if game.night_number != 1:
            for player in game.players:
                if player.is_demon and player.voted_to_execute:
                    self.player.send(f"The demon voted today.")
                else:
                    self.player.send(f"The demon did not vote today.")
        pass

class Town_Crier(Townsfolk):
    def __init__(self, player):
        super().__init__(player)
        self.minion_voted = False
    async def perform_night_action(self, game):
        # Perform the night action for the town crier
        if game.night_number != 1:
            for player in game.players:
                if player.is_minion and player.voted_to_execute:
                    if not self.minion_voted:
                        self.minion_voted = True
                if self.minion_voted:
                    self.player.send(f"A minion voted today.")
                else:
                    self.player.send(f"No minion\'s voted today.")
            self.minion_voted = False
        pass

class Oracle(Townsfolk):
    def __init__(self, player):
        super().__init__(player)
        self.dead_evil = 0
    async def perform_night_action(self, game):
        # Perform the night action for the oracle
        if game.night_number != 1:
            for player in game.players:
                if player.alignment == "Evil":
                    if player.is_dead:
                        self.dead_evil += 1
            if self.dead_evil == 0:
                self.player.send("No dead evil players.")
            else:
                self.player.send(f"Number of dead evil players: {self.dead_evil}")
        pass

class Clockmaker(Townsfolk):
    async def perform_night_action(self, game):
        # Perform the night action for the clockmaker
        nearest_minion_distance = float('inf')  # Initialize to infinity to find minimum
        for player in game.players:
            if player.is_demon:
                demon_position = player.numerical_value
                
                # Calculate upper and lower positions
                upper_player_position = (demon_position % len(game.players)) + 1
                lower_player_position = (demon_position - 2) % len(game.players) + 1
                
                # Check for nearest minion above
                upper_distance = 0
                current_position = upper_player_position
                
                while True:
                    upper_distance += 1
                    current_position = (current_position % len(game.players)) + 1  # Move to next player
                    if any(p.numerical_value == current_position and p.is_minion for p in game.players):
                        nearest_minion_distance = min(nearest_minion_distance, upper_distance)
                        break
                    # Break if we loop back to the demon
                    if current_position == demon_position:
                        break
                
                # Check for nearest minion below
                lower_distance = 0
                current_position = lower_player_position
                
                while True:
                    lower_distance += 1
                    current_position = (current_position - 2) % len(game.players) + 1  # Move to previous player
                    if any(p.numerical_value == current_position and p.is_minion for p in game.players):
                        nearest_minion_distance = min(nearest_minion_distance, lower_distance)
                        break
                    # Break if we loop back to the demon
                    if current_position == demon_position:
                        break
        
        if nearest_minion_distance == float('inf'):
            await self.player.send("No nearby minion found.")
        else:
            await self.player.send(f"Nearest minion distance: {nearest_minion_distance} steps.")

class Juggler(Townsfolk): #COME BACK LATER
    def __init__(self, player):
        super().__init__(player)
        self.juggler_guesses = []  # Initialize guesses as an empty list

    async def perform_night_action(self, game):
        if game.night_number == 2:
            self.juggler_guesses = game.juggler_guesses  # Assuming game.juggler_guesses is a list of tuples (player, role)
            self.correct_guesses = 0
            for guess in self.juggler_guesses:  # Guess is a tuple (player, role)
                guessed_player_id, guessed_role = guess  # Unpack the tuple
                # Find the player in the game
                guessed_player = next((p for p in game.players if p.user.id == guessed_player_id), None)

                if guessed_player and guessed_player.role_instance.role == guessed_role:
                    self.correct_guesses += 1
            if self.correct_guesses == 0:
                await self.player.send("No correct guesses.")
            else:
                await self.player.send(f"Correct guesses: {self.correct_guesses}")
        pass

                    

class Artist(Townsfolk):
    async def perform_night_action(self, game):
        # Does Nothing
        pass

class Philosopher(Townsfolk):
    def __init__(self, player):
        super().__init__(player)
        self.ability_used = False

    async def perform_night_action(self, game):
        # Perform the night action for the philosopher
        if not self.ability_used:
            confirm_view = ConfirmView(self.player)
            await self.player.send("Would you like to use your ability?", view=confirm_view)

            # Here you might want to handle the confirmation response if needed
            self.ability_used = True
            
            view = PhilosopherView(game, self.player)
            await self.player.send("Select a role to become:", view=view)

            # Wait for the player's selection from PhilosopherView
            selected_role = await view.wait()  # Use wait to get the selected role
            
            if selected_role:
                # Find the class of the selected role
                selected_role_class = globals()[selected_role]
                await selected_role_class.perform_night_action(game)  # Await the night action
                await self.player.send(f"You are now a {selected_role} for the night!")

                # Mark players of the same role as drunk
                for player in game.players:
                    if player.role_instance.role == selected_role:
                        player.is_drunk = True
        pass

class Seamstress(Townsfolk):
    def __init__(self, player):
        super().__init__(player)
        self.ability_used = False
    async def perform_night_action(self, game):
        # Perform the night action for the seamstress
        if not self.ability_used:
            confirm_view = ConfirmView(self.player)
            use_ability = await self.player.send("Would you like to use your ability?", view=confirm_view)
            if use_ability:
                view = SeamstressView(game, self.player)
                await self.player.send("Select two players to check alignment:", view=view)
            
        pass

class Savant(Townsfolk):
    async def perform_night_action(self, game):
        # Does Nothing
        pass

class Sage(Townsfolk):
    def __init__(self, player):
        super().__init__(player)
        self.demon_killed = False
    async def perform_night_action(self, game):
        # Perform the night action for the sage
        if self.demon_killed:
            for player in game.players.remove(self.player):
                if player.is_demon:
                    random_player = random.choice(game.players.remove(player))
                    await self.player.send(f"The demon is either {player} or {random_player}")
        pass


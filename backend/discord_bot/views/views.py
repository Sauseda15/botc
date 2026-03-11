import json
import random
import datetime
import logging
import os
from dataclasses import dataclass
from enum import Enum

import discord
from discord.ext import commands

from roles import *

# Load role data
BASE_DIR = os.path.dirname(__file__)
ROLE_DATA = os.path.join(BASE_DIR, '../utils/role_data.json')


# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())

# === UI VIEWS === #
class RoleSelectionView(discord.ui.View):
    def __init__(self, roles_enum, game):
        super().__init__(timeout=None)
        self.roles_enum = roles_enum
        self.game = game
        self.selected_roles = []

        self.add_item(
            discord.ui.Select(
                placeholder='Select roles for the game',
                options=[discord.SelectOption(label=role, value=role) for role in roles_enum],
                max_values=len(roles_enum),
                custom_id='role_select'
            )
        )

    @discord.ui.button(label="Submit Roles", style=discord.ButtonStyle.green, custom_id='submit_roles')
    async def submit_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        select: discord.ui.Select = self.children[0]
        self.selected_roles = select.values
        self.game.roles_in_play = self.selected_roles

        self.game.townsfolk_roles_not_in_play = [
            role for role in self.game.game_mode.townsfolk if role not in self.selected_roles
        ]

        self.game.bluffs = (
            random.sample(self.game.townsfolk_roles_not_in_play, 3)
            if len(self.game.townsfolk_roles_not_in_play) >= 3
            else self.game.townsfolk_roles_not_in_play
        )

        await interaction.response.send_message(
            f"Roles selected: {', '.join(self.selected_roles)}\nDemon Bluffs: {', '.join(self.game.bluffs)}",
            ephemeral=True
        )
        await self.game.assign_roles_to_players()


# === DATA CLASSES === #
@dataclass(frozen=True)
class GameMode:
    name: str
    description: str
    townsfolk: list
    minions: list
    outsiders: list
    demon: list
    travelers: list = None
    added_roles: list = None


# === GAME CLASSES === #
class Game:
    def __init__(self, bot, game_mode, players, storyteller_id):
        self.bot = bot
        self.game_mode = game_mode
        self.players = [
            Player(bot.get_user(pid), pid, self) 
            for pid in players
            ]
        self.storyteller = storyteller_id

        self.game_state = GameState.WAITING_FOR_PLAYERS
        self.roles_in_play = []
        self.townsfolk_roles_not_in_play = []
        self.bluffs = []
        self.is_active = True
        self.is_started = False
        self.date = datetime.datetime.now()

    async def start_game(self):
        self.is_started = True
        roles = self.game_mode.townsfolk + self.game_mode.minions + self.game_mode.outsiders + self.game_mode.demon
        storyteller_user = self.bot.get_user(self.storyteller)
        try:
            await storyteller_user.send("Please select the roles for the game:", view=RoleSelectionView(roles, self))
        except discord.Forbidden:
            logger.error(f"Storyteller has DMs disabled")

    async def assign_roles_to_players(self):
        random.shuffle(self.players)

        if len(self.roles_in_play) < len(self.players):
            logger.warning("Not enough roles selected for the number of players. Some players will not receive a role.")
            return

        for player, role_name in zip(self.players, self.roles_in_play):
            role_class = ROLE_CLASSES.get(role_name)

            if role_class:
                player.role_instance = role_class(player)
                await player.assign_role(role_name)
            else:
                logger.error(f"Role class not found for role: {role_name}")


    async def perform_night_actions(self):
        if self.game_state == GameState.NIGHT_PHASE:
            for player in self.players:
                if player.role_instance and player.is_alive:
                    await player.role_instance.perform_night_action()
            self.game_state = GameState.DAY_PHASE
            await self.perform_day_actions()

    async def perform_day_actions(self):
        if self.game_state == GameState.DAY_PHASE:
            for player in self.players:
                await player.role_instance.perform_day_action()

    async def perform_execution(self, player):
        if self.game_state == GameState.DAY_PHASE:
            await player.role_instance.perform_execution()

    async def collect_votes(self):
        if self.game_state == GameState.DAY_PHASE:
            for player in self.players:
                await player.role_instance.collect_vote()

    def end_game(self):
        self.is_active = False


class Player:
    def __init__(self, user, user_id, game):
        self.game = game
        self.user = user
        self.discord_id = user_id
        self.role_instance = None
        self.role = None
        self.is_alive = True

    def get_role_description(self, role):
        with open(ROLE_DATA) as f:
            data = json.load(f)
        return data.get(role, "Role description not found")

    async def assign_role(self, role):
        self.role = role
        role_desc = self.get_role_description(role)
        img_path = os.path.join(BASE_DIR, '../utils/photos', f'{role}.png')
        role_img = discord.File(img_path)
        color, footer = self.get_role_color_and_footer(role)

        embed = discord.Embed(title=f"Your role is {role}", description=role_desc, color=color)
        embed.set_image(url=f"attachment://{role}.png")
        embed.set_footer(text=footer)

        await self.user.send(file=role_img, embed=embed)

    def get_role_color_and_footer(self, role):
        if role in self.game.game_mode.townsfolk:
            return discord.Color.blue(), "You are a townsfolk. Work with others to eliminate the demon."
        elif role in self.game.game_mode.outsiders:
            return discord.Color.purple(), "You are an outsider. Assist the townsfolk to find the demon."
        elif role in self.game.game_mode.minions:
            return discord.Color.red(), "You are a minion. Protect the demon at all costs."
        elif role in self.game.game_mode.demon:
            return discord.Color.dark_red(), f"You are the demon. Eliminate the townsfolk. Bluffs: {', '.join(self.game.bluffs)}"
        return discord.Color.light_grey(), "Unknown role."


class GameState(Enum):
    WAITING_FOR_PLAYERS = 1
    NIGHT_PHASE = 2
    DAY_PHASE = 3
    GAME_OVER = 4


# === ENUMS FOR GAME MODES === #
class GameType(Enum):
    TROUBLE_BREWING = GameMode(
        name='Trouble Brewing',
        description='Classic beginner setup.',
        townsfolk=['Fortune Teller', 'Chef', 'Empath', 'Monk', 'Slayer', 'Soldier', 'Undertaker',
                   'Mayor', 'Librarian', 'Investigator', 'Washerwoman', 'Ravenkeeper', 'Virgin'],
        minions=['Spy', 'Scarlet Woman', 'Baron', 'Poisoner'],
        outsiders=['Butler', 'Drunk', 'Recluse', 'Saint'],
        demon=['Imp'],
        travelers=['Scapegoat', 'Gunslinger', 'Beggar', 'Bureaucrat', 'Thief']
    )
    BAD_MOON_RISING = GameMode(
        name='Bad Moon Rising',
        description='Advanced game mode focused on death and resurrection.',
        townsfolk=['Grandmother', 'Sailor', 'Chambermaid', 'Exorcist', 'Innkeeper', 'Gambler', 'Gossip',
                   'Courtier', 'Professor', 'Minstrel', 'Tea Lady', 'Pacifist', 'Fool'],
        minions=['Godfather', 'Devil\'s Advocate', 'Assassin', 'Mastermind'],
        outsiders=['Goon', 'Lunatic', 'Tinker', 'Moonchild'],
        demon=['Zombuul', 'Pukka', 'Shabaloth', 'Po'],
        travelers=['Apprentice', 'Matron', 'Voudon', 'Judge', 'Bishop']
    )
    SECTS_AND_VIOLETS = GameMode(
        name='Sects & Violets',
        description='Focused on complex information roles and deception.',
        townsfolk=['Clockmaker', 'Dreamer', 'Snake Charmer', 'Mathematician', 'Flowergirl', 'Town Crier', 'Oracle',
                   'Savant', 'Seamstress', 'Philosopher', 'Artist', 'Juggler', 'Sage'],
        minions=['Evil Twin', 'Witch', 'Warlock', 'Coven Leader'],
        outsiders=['Mutant', 'Sweetheart', 'Barber', 'Klutz'],
        demon=['Fang Gu', 'Vigor Mortis', 'No Dashii', 'Vortox'],
        travelers=['Butcher', 'Bone Collector', 'Harlot', 'Barista', 'Deviant']
    )
    FABLED = GameMode(
        name='Fabled',
        description='Custom rules and content.',
        townsfolk=[],
        minions=[],
        outsiders=[],
        demon=[],
        added_roles=['Doomslayer', 'Angel', 'Buddhist', 'Hell\'s Librarian', 'Revolutionary', 'Fiddler', 'Toymaker']
    )

ROLE_CLASSES = {
    'Fortune Teller': FortuneTeller,
    'Chef': Chef,
    'Empath': Empath,
    'Monk': Monk,
    'Slayer': Slayer,
    'Soldier': Soldier,
    'Undertaker': Undertaker,
    'Mayor': Mayor,
    'Librarian': Librarian,
    'Investigator': Investigator,
    'Washerwoman': Washerwoman,
    'Ravenkeeper': Ravenkeeper,
    'Virgin': Virgin,
    'Spy': Spy,
    'Scarlet Woman': Minion, #Revisit
    'Baron': Minion, #Revisit
    'Poisoner': Poisoner,
    'Butler': Butler,
    'Drunk': Outsider, #Revisit
    'Recluse': Recluse,
    'Saint': Saint, 
    'Imp': Imp,
    'Scapegoat': Scapegoat,
    'Gunslinger': Gunslinger,
    'Beggar': Beggar,
    'Bureaucrat': Bureaucrat,
    'Thief': Thief,
    'Grandmother': Grandmother,
    'Sailor': Sailor,
    'Chambermaid': Chambermaid,
    'Exorcist': Exorcist,
    'Innkeeper': Innkeeper,
    'Gambler': Gambler,
    'Gossip': Gossip,
    'Courtier': Courtier,
    'Professor': Professor,
    'Minstrel': Minstrel,
    'Tea Lady': Tea_Lady,
    'Pacifist': Pacifist,
    'Fool': Fool,
    'Godfather': Godfather,
    'Devil\'s Advocate': Devil_s_Advocate,
    'Assassin': Assassin,
    'Mastermind': Mastermind,
    'Goon': Goon,
    'Lunatic': Outsider, #Revisit
    'Tinker': Tinker,
    'Moonchild': Moonchild,
    'Zombuul': Zombuul,
    'Pukka': Pukka,
    'Shabaloth': Shabaloth,
    'Po': Po,
    'Apprentice': Apprentice,
    'Matron': Matron,
    'Voudon': Voudon,
    'Judge': Judge,
    'Bishop': Bishop,
    'Clockmaker': Clockmaker,
    'Dreamer': Dreamer,
    'Snake Charmer': Snake_Charmer,
    'Mathematician': Mathematician,
    'Flowergirl': Flowergirl,
    'Town Crier': Town_Crier,
    'Oracle': Oracle,
    'Savant': Savant,
    'Seamstress': Seamstress,
    'Philosopher': Philosopher,
    'Artist': Artist,
    'Juggler': Juggler,
    'Sage': Sage,
    'Evil Twin': Evil_Twin,
    'Witch': Witch,
    'Warlock': Warlock, #Revisit
    'Coven Leader': Coven_Leader, #Revisit
    'Mutant': Mutant,
    'Sweetheart': Sweetheart,
    'Barber': Barber,
    'Klutz': Klutz,
    'Fang Gu': Fang_Gu,
    'Vigor Mortis': Vigormortis,
    'No Dashii': No_Dashii,
    'Vortox': Vortox,
    'Butcher': Butcher,
    'Bone Collector': Bone_Collector,
    'Harlot': Harlot,
    'Barista': Barista,
    'Deviant': Deviant,
}

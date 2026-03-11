from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

SCRIPT_DEFINITIONS = {
    'troubles_brewing': {
        'label': 'Trouble Brewing',
        'roles': {
            'townsfolk': ['Fortune Teller', 'Chef', 'Empath', 'Monk', 'Slayer', 'Soldier', 'Undertaker', 'Mayor', 'Librarian', 'Investigator', 'Washerwoman', 'Ravenkeeper', 'Virgin'],
            'outsiders': ['Butler', 'Drunk', 'Recluse', 'Saint'],
            'minions': ['Spy', 'Scarlet Woman', 'Baron', 'Poisoner'],
            'demons': ['Imp'],
        },
    },
    'sects_and_violets': {
        'label': 'Sects and Violets',
        'roles': {
            'townsfolk': ['Clockmaker', 'Dreamer', 'Snake Charmer', 'Mathematician', 'Flowergirl', 'Town Crier', 'Oracle', 'Savant', 'Seamstress', 'Philosopher', 'Artist', 'Juggler', 'Sage'],
            'outsiders': ['Mutant', 'Sweetheart', 'Barber', 'Klutz'],
            'minions': ['Evil Twin', 'Witch', 'Cerenovus'],
            'demons': ['Fang Gu', 'Vigormortis', 'No Dashii', 'Vortox'],
        },
    },
    'bad_moon_rising': {
        'label': 'Bad Moon Rising',
        'roles': {
            'townsfolk': ['Grandmother', 'Sailor', 'Chambermaid', 'Exorcist', 'Innkeeper', 'Gambler', 'Gossip', 'Courtier', 'Professor', 'Minstrel', 'Tea Lady', 'Pacifist', 'Fool'],
            'outsiders': ['Goon', 'Lunatic', 'Tinker', 'Moonchild'],
            'minions': ['Godfather', "Devil's Advocate", 'Assassin', 'Mastermind'],
            'demons': ['Zombuul', 'Pukka', 'Shabaloth', 'Po'],
        },
    },
}

ALIGNMENT_BY_GROUP = {
    'townsfolk': 'Good',
    'outsiders': 'Good',
    'minions': 'Evil',
    'demons': 'Evil',
}

NIGHT_ACTION_TEMPLATES = {
    'Chef': {'order': 10, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Tell the Chef how many adjacent evil pairs are in play.'},
    'Librarian': {'order': 11, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Give the Librarian their first-night Outsider information.'},
    'Washerwoman': {'order': 12, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Give the Washerwoman their first-night Townsfolk information.'},
    'Investigator': {'order': 13, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Give the Investigator their first-night Minion information.'},
    'Empath': {'order': 20, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Tell the Empath how many living neighbors are evil.'},
    'Fortune Teller': {'order': 30, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 2 players to check tonight. Use names or seat numbers.', 'approval_prompt': 'Approve the Fortune Teller choice and return their yes/no information.'},
    'Monk': {'order': 35, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to protect tonight.', 'approval_prompt': 'Approve the Monk protection target.'},
    'Poisoner': {'order': 40, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to poison tonight.', 'approval_prompt': 'Approve the Poisoner target.'},
    'Spy': {'order': 41, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Show the Spy the grimoire or summarize the information you want them to have.'},
    'Scarlet Woman': {'order': 42, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Scarlet Woman is passive tonight unless the Demon dies.'},
    'Baron': {'order': 43, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Baron is passive tonight.'},
    'Imp': {'order': 50, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to kill tonight.', 'approval_prompt': 'Approve the Demon kill and record any storyteller outcome adjustments.'},
    'Ravenkeeper': {'order': 55, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'If the Ravenkeeper died tonight, wake them and give their learn-a-role information.'},
    'Undertaker': {'order': 56, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'If someone was executed today, tell the Undertaker their character.'},
    'Slayer': {'order': 90, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Slayer has no night action.'},
    'Soldier': {'order': 91, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Soldier has no night action.'},
    'Mayor': {'order': 92, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Mayor has no night action.'},
    'Virgin': {'order': 93, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Virgin has no night action.'},
    'Saint': {'order': 94, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Saint has no night action.'},
    'Recluse': {'order': 95, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Recluse has no night action.'},
    'Butler': {'order': 96, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose the player you must follow for voting tomorrow.', 'approval_prompt': 'Approve the Butler choice.'},
    'Drunk': {'order': 97, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Drunk thinks they are another character; resolve accordingly.'},

    'Clockmaker': {'order': 10, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Give the Clockmaker their first-night distance information.'},
    'Dreamer': {'order': 20, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to dream about tonight.', 'approval_prompt': 'Approve the Dreamer target and prepare the good/evil pair.'},
    'Snake Charmer': {'order': 21, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to charm tonight.', 'approval_prompt': 'Approve the Snake Charmer target and resolve any swap.'},
    'Mathematician': {'order': 22, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Tell the Mathematician how many abilities malfunctioned since dawn.'},
    'Flowergirl': {'order': 23, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Tell the Flowergirl whether a Demon voted today.'},
    'Town Crier': {'order': 24, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Tell the Town Crier whether a Minion nominated today.'},
    'Oracle': {'order': 25, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Tell the Oracle how many dead players are evil.'},
    'Savant': {'order': 26, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Prepare the Savant’s two statements for tomorrow.'},
    'Seamstress': {'order': 27, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'If using your once-per-game ability, choose 2 players to compare.', 'approval_prompt': 'Approve the Seamstress picks and respond with same/different alignment.'},
    'Philosopher': {'order': 28, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'If using your once-per-game ability, name the good character you want to become.', 'approval_prompt': 'Approve the Philosopher choice and apply drunkenness if needed.'},
    'Artist': {'order': 29, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Artist acts during the day, not at night.'},
    'Juggler': {'order': 30, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'If it is Juggler night, tell them how many guesses were correct.'},
    'Sage': {'order': 31, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'If the Sage died to the Demon, tell them the Demon is one of two players.'},
    'Mutant': {'order': 32, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Mutant has no night action.'},
    'Sweetheart': {'order': 33, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Sweetheart has no night action.'},
    'Barber': {'order': 34, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'If the Barber died, resolve any Demon swap tonight.'},
    'Klutz': {'order': 35, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Klutz acts on death, not during normal night order.'},
    'Evil Twin': {'order': 40, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Give Evil Twin first-night pairing info if needed.'},
    'Witch': {'order': 41, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to hex tonight.', 'approval_prompt': 'Approve the Witch target.'},
    'Cerenovus': {'order': 42, 'audience': 'storyteller', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player and 1 good character for tomorrow’s madness.', 'approval_prompt': 'Approve the Cerenovus target and madness character.'},
    'Fang Gu': {'order': 50, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to kill tonight.', 'approval_prompt': 'Approve the Fang Gu target and any jump outcome.'},
    'Vigormortis': {'order': 51, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to kill tonight.', 'approval_prompt': 'Approve the Vigormortis kill and any poisoning effect.'},
    'No Dashii': {'order': 52, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to kill tonight.', 'approval_prompt': 'Approve the No Dashii kill and poisoning neighbors.'},
    'Vortox': {'order': 53, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to kill tonight.', 'approval_prompt': 'Approve the Vortox kill and remember false info.'},

    'Grandmother': {'order': 10, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Give Grandmother their first-night player and character info.'},
    'Sailor': {'order': 20, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to drink with tonight.', 'approval_prompt': 'Approve the Sailor target and decide who becomes drunk.'},
    'Chambermaid': {'order': 21, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 2 players to learn how many woke tonight.', 'approval_prompt': 'Approve the Chambermaid picks and return the count.'},
    'Exorcist': {'order': 22, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to exorcise tonight.', 'approval_prompt': 'Approve the Exorcist target and determine whether the Demon is blocked.'},
    'Innkeeper': {'order': 23, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 2 players to keep safe tonight.', 'approval_prompt': 'Approve the Innkeeper targets and choose which becomes drunk.'},
    'Gambler': {'order': 24, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player and guess their character.', 'approval_prompt': 'Approve the Gambler guess and resolve death if wrong.'},
    'Gossip': {'order': 25, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Resolve whether today’s Gossip statement was true and whether a player dies tonight.'},
    'Courtier': {'order': 26, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'If using your once-per-game ability, choose a character to make drunk for 3 days and 3 nights.', 'approval_prompt': 'Approve the Courtier character choice.'},
    'Professor': {'order': 27, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'If using your once-per-game ability, choose a dead Townsfolk to resurrect.', 'approval_prompt': 'Approve the Professor resurrection target.'},
    'Minstrel': {'order': 28, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'If a Minion was executed today, mark the rest of the players drunk until dusk.'},
    'Tea Lady': {'order': 29, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Tea Lady is passive tonight.'},
    'Pacifist': {'order': 30, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Pacifist is passive tonight.'},
    'Fool': {'order': 31, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Fool is passive tonight.'},
    'Goon': {'order': 32, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Goon changes based on who targets them first.'},
    'Lunatic': {'order': 33, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'If Lunatic is in play, mirror a Demon prompt as needed.'},
    'Tinker': {'order': 34, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Tinker is passive unless you choose arbitrary death.'},
    'Moonchild': {'order': 35, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Moonchild acts on death, not in normal night order.'},
    'Godfather': {'order': 40, 'audience': 'storyteller', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Resolve Godfather information/kill if an Outsider died today.'},
    'Devil\'s Advocate': {'order': 41, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to protect from execution tomorrow.', 'approval_prompt': 'Approve the Devil’s Advocate protection.'},
    'Assassin': {'order': 42, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'If using your once-per-game ability, choose 1 player to kill.', 'approval_prompt': 'Approve the Assassin kill.'},
    'Mastermind': {'order': 43, 'audience': 'passive', 'requires_response': False, 'requires_approval': False, 'storyteller_prompt': 'Mastermind is passive tonight.'},
    'Zombuul': {'order': 50, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'If no one died today, choose 1 player to kill tonight.', 'approval_prompt': 'Approve the Zombuul kill.'},
    'Pukka': {'order': 51, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 1 player to poison tonight.', 'approval_prompt': 'Approve the Pukka poison and death rollover.'},
    'Shabaloth': {'order': 52, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose 2 players to kill tonight.', 'approval_prompt': 'Approve the Shabaloth kills and any regurgitation.'},
    'Po': {'order': 53, 'audience': 'player', 'requires_response': True, 'requires_approval': True, 'player_prompt': 'Choose whether to kill 1 player tonight or charge for a later 3-kill night.', 'approval_prompt': 'Approve the Po action.'},
}

ALIGNMENT_BY_GROUP = {
    'townsfolk': 'Good',
    'outsiders': 'Good',
    'minions': 'Evil',
    'demons': 'Evil',
}

PLAYER_SELECTION_COUNTS = {
    'Fortune Teller': {'target_count': 2},
    'Monk': {'target_count': 1, 'allow_self': False},
    'Poisoner': {'target_count': 1},
    'Imp': {'target_count': 1},
    'Butler': {'target_count': 1},
    'Dreamer': {'target_count': 1},
    'Snake Charmer': {'target_count': 1},
    'Seamstress': {'target_count': 2},
    'Witch': {'target_count': 1},
    'Fang Gu': {'target_count': 1},
    'Vigormortis': {'target_count': 1},
    'No Dashii': {'target_count': 1},
    'Vortox': {'target_count': 1},
    'Sailor': {'target_count': 1},
    'Chambermaid': {'target_count': 2},
    'Exorcist': {'target_count': 1},
    'Innkeeper': {'target_count': 2},
    'Devil\'s Advocate': {'target_count': 1},
    'Zombuul': {'target_count': 1},
    'Pukka': {'target_count': 1},
    'Shabaloth': {'target_count': 2},
}

BASE_DIR = Path(__file__).resolve().parent
ROLE_DATA_PATH = BASE_DIR / 'discord_bot' / 'utils' / 'role_data.json'
ROLE_IMAGE_DIR = BASE_DIR / 'discord_bot' / 'utils' / 'photos' / 'role_images'


@lru_cache(maxsize=1)
def load_role_descriptions() -> dict[str, str]:
    with ROLE_DATA_PATH.open('r', encoding='utf-8') as handle:
        raw = json.load(handle)
    return {name: str(description).strip('"') for name, description in raw.items()}


@lru_cache(maxsize=1)
def load_role_icon_map() -> dict[str, str]:
    payload: dict[str, str] = {}
    for image_path in ROLE_IMAGE_DIR.glob('*.png'):
        payload[image_path.stem] = f"/role-icons/{quote(image_path.name)}"
    return payload


def build_role_entry(name: str, group: str, descriptions: dict[str, str], icons: dict[str, str]) -> dict[str, str]:
    return {
        'name': name,
        'alignment': ALIGNMENT_BY_GROUP[group],
        'group': group,
        'description': descriptions.get(name, 'No role description available yet.'),
        'icon_url': icons.get(name, ''),
    }


def get_role_night_template(role_name: str | None) -> dict[str, object]:
    if not role_name:
        return {
            'order': 999,
            'audience': 'passive',
            'requires_response': False,
            'requires_approval': False,
            'storyteller_prompt': 'No role assigned yet.',
        }

    template = dict(
        NIGHT_ACTION_TEMPLATES.get(
            role_name,
            {
                'order': 500,
                'audience': 'storyteller',
                'requires_response': False,
                'requires_approval': False,
                'storyteller_prompt': f'Resolve {role_name} manually with storyteller judgment.',
            },
        )
    )

    selection_config = PLAYER_SELECTION_COUNTS.get(role_name)
    if selection_config:
        template['input_type'] = 'player_select'
        template['target_count'] = selection_config['target_count']
        template['allow_self'] = selection_config.get('allow_self', True)

    return template


def get_script_options() -> list[dict[str, object]]:
    descriptions = load_role_descriptions()
    icons = load_role_icon_map()
    payload: list[dict[str, object]] = []
    for script_id, script in SCRIPT_DEFINITIONS.items():
        roles: list[dict[str, str]] = []
        for group, names in script['roles'].items():
            for name in names:
                roles.append(build_role_entry(name, group, descriptions, icons))
        payload.append(
            {
                'id': script_id,
                'label': script['label'],
                'roles': roles,
            }
        )
    return payload


def get_script_reference(script_id: str) -> dict[str, object]:
    descriptions = load_role_descriptions()
    icons = load_role_icon_map()
    script = SCRIPT_DEFINITIONS.get(script_id)
    if not script:
        return {'id': script_id, 'label': script_id, 'roles': []}

    roles: list[dict[str, str]] = []
    for group, names in script['roles'].items():
        for name in names:
            roles.append(build_role_entry(name, group, descriptions, icons))

    return {
        'id': script_id,
        'label': script['label'],
        'roles': roles,
    }


def infer_alignment(script_id: str, role_name: str | None) -> str | None:
    if not role_name:
        return None
    script = SCRIPT_DEFINITIONS.get(script_id)
    if not script:
        return None
    for group, names in script['roles'].items():
        if role_name in names:
            return ALIGNMENT_BY_GROUP[group]
    return None


def build_night_prompt(script_id: str, role_name: str | None, alignment: str | None, reminders: list[str] | None = None) -> str | None:
    if not role_name:
        return None

    descriptions = load_role_descriptions()
    description = descriptions.get(role_name, 'No role description available yet.')
    reminder_block = ', '.join(reminders or []) if reminders else 'none'
    alignment = alignment or infer_alignment(script_id, role_name) or 'Unknown'
    night_template = get_role_night_template(role_name)

    if alignment == 'Evil':
        team_note = 'You are on the evil team. Submit only the action, target, or lie-support you want the storyteller to track tonight.'
    else:
        team_note = 'You are on the good team. Submit the exact target, choice, or question you want resolved tonight.'

    if night_template.get('audience') == 'passive':
        action_note = 'You usually do not choose anything at night unless the storyteller specifically asks for input.'
    else:
        action_note = str(night_template.get('player_prompt') or 'Use the field below to record your night action in plain language with names or seat numbers.')

    return '\n'.join(
        [
            f'Role: {role_name}',
            f'Alignment: {alignment}',
            f'Ability: {description}',
            f'Reminders: {reminder_block}',
            team_note,
            action_note,
        ]
    )



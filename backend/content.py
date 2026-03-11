from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

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

ROLE_DATA_PATH = Path(__file__).resolve().parent / 'discord_bot' / 'utils' / 'role_data.json'


@lru_cache(maxsize=1)
def load_role_descriptions() -> dict[str, str]:
    with ROLE_DATA_PATH.open('r', encoding='utf-8') as handle:
        raw = json.load(handle)
    return {name: str(description).strip('"') for name, description in raw.items()}


def get_script_options() -> list[dict[str, object]]:
    descriptions = load_role_descriptions()
    payload: list[dict[str, object]] = []
    for script_id, script in SCRIPT_DEFINITIONS.items():
        roles: list[dict[str, str]] = []
        for group, names in script['roles'].items():
            for name in names:
                roles.append(
                    {
                        'name': name,
                        'alignment': ALIGNMENT_BY_GROUP[group],
                        'group': group,
                        'description': descriptions.get(name, 'No role description available yet.'),
                    }
                )
        payload.append(
            {
                'id': script_id,
                'label': script['label'],
                'roles': roles,
            }
        )
    return payload


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

    if alignment == 'Evil':
        team_note = 'You are on the evil team. Submit only the action, target, or lie-support you want the storyteller to track tonight.'
    else:
        team_note = 'You are on the good team. Submit the exact target, choice, or question you want resolved tonight.'

    passive_roles = {'Soldier', 'Mayor', 'Virgin', 'Saint', 'Recluse', 'Tinker', 'Mutant', 'Sweetheart', 'Pacifist', 'Fool'}
    if role_name in passive_roles:
        action_note = 'You usually do not choose anything at night unless the storyteller specifically asks for input.'
    else:
        action_note = 'Use the field below to record your night action in plain language with names or seat numbers.'

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

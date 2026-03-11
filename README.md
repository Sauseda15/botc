# BOTC Web Control Layer

This repo is set up around one source of truth:

- Backend: authoritative game state, permissions, night prompts, votes, logs
- Website: public town board, player role sheet, player night actions, storyteller dashboard
- Discord OAuth: browser identity and access control

## Current Model

- Players log into the website with Discord OAuth
- Storyteller creates the game from the website dashboard
- Night actions are assigned and submitted in the player web view
- Day voting also happens on the website

## Prerequisites

- Python 3.12+
- Node.js 20+
- A Discord application with OAuth enabled

## Environment

Copy values into `.env` at the repo root.

Required fields:

- `DISCORD_CLIENT_ID`
- `DISCORD_CLIENT_SECRET`
- `DISCORD_REDIRECT_URI`
- `FRONTEND_BASE_URL`

Recommended fields:

- `STORYTELLER_DISCORD_IDS`
- `SESSION_DURATION_HOURS`
- `ENABLE_DISCORD_BOT=false`

For local development, use:

- `DISCORD_REDIRECT_URI=http://localhost:8000/api/auth/callback`
- `FRONTEND_BASE_URL=http://localhost:5173`

In the Discord developer portal, add this exact redirect URI:

- `http://localhost:8000/api/auth/callback`

## Install

Backend:

```powershell
cd "D:\botc py\botc\backend"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Frontend:

```powershell
cd "D:\botc py\botc\frontend"
npm install
```

## Run

Backend:

```powershell
cd "D:\botc py\botc\backend"
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd "D:\botc py\botc\frontend"
npm run dev
```

Then open:

- `http://localhost:5173`

## First End-to-End Test

1. Log in on the website with the storyteller Discord account.
2. Open the storyteller dashboard.
3. Create a game with real Discord user IDs in the setup JSON.
4. Set roles and alignments in that JSON before creating the game.
5. Move the game to `night`.
6. Assign a night prompt to a player from the storyteller dashboard.
7. Log in on another browser session as that player.
8. Open the player view and submit a night action.
9. Confirm the storyteller dashboard shows the submitted response.
10. Move the game to `day` and test voting from the player view.

## Sample Player JSON

```json
[
  {
    "discord_user_id": "123456789012345678",
    "display_name": "Alice",
    "seat": 0,
    "role_name": "Chef",
    "alignment": "Good",
    "reminders": []
  },
  {
    "discord_user_id": "234567890123456789",
    "display_name": "Bob",
    "seat": 1,
    "role_name": "Imp",
    "alignment": "Evil",
    "reminders": []
  }
]
```

## Notes

- The old Discord game-engine files are still in the repo but are not the active web flow.
- The checked-in virtualenv files at the repo root are legacy and should not be relied on for a clean setup.

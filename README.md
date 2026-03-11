# BOTC Web Control Layer

This repo is set up around one source of truth:

- Backend: authoritative game state, permissions, night prompts, votes, logs
- Website: public town board, player role sheet, player night actions, storyteller dashboard
- Discord OAuth: browser identity and access control
- Postgres: persistent storage for game state, lobby, sessions, and OAuth state

## Current Model

- Players log into the website with Discord OAuth
- Storyteller creates the game from the website dashboard
- Night actions are assigned and submitted in the player web view
- Day voting also happens on the website
- State survives Railway restarts when `DATABASE_URL` is configured

## Prerequisites

- Python 3.12+
- Node.js 20+
- A Discord application with OAuth enabled
- PostgreSQL for production persistence

## Environment

Copy values into `.env` at the repo root.

Required fields:

- `DISCORD_CLIENT_ID`
- `DISCORD_CLIENT_SECRET`
- `DISCORD_REDIRECT_URI`
- `FRONTEND_BASE_URL`

Recommended fields:

- `DATABASE_URL`
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

## Railway Postgres Setup

1. In Railway, open your single BOTC service project.
2. Click `New` and add a `PostgreSQL` database service.
3. Wait for Railway to provision it.
4. Open the Postgres service and copy the shared `DATABASE_URL` variable Railway generates.
5. In the app service, make sure `DATABASE_URL` is available in the `production` environment.
6. Redeploy the app service.
7. On startup, the backend will create its `app_state` table automatically and load/save the BOTC snapshot there.

## Notes

- The app uses a simple snapshot persistence layer right now, not a full migration stack.
- The old Discord game-engine files are still in the repo but are not the active web flow.
- The checked-in virtualenv files at the repo root are legacy and should not be relied on for a clean setup.
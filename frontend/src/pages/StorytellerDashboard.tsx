import React, { useEffect, useMemo, useState } from 'react';

import { apiUrl } from '../api';

type AuthState = {
  authenticated: boolean;
  user?: {
    discord_user_id: string;
    username: string;
    is_storyteller: boolean;
    is_player: boolean;
  };
};

type RoleOption = {
  name: string;
  alignment: string;
  group: string;
  description: string;
};

type ScriptOption = {
  id: string;
  label: string;
  roles: RoleOption[];
};

type LobbyPlayer = {
  discord_user_id: string;
  display_name: string;
  joined_at: string;
};

type SetupSeat = {
  discord_user_id: string;
  display_name: string;
  seat: number;
  is_alive: boolean;
  role_name: string | null;
  alignment: string | null;
  reminders: string[];
};

type PlayerRecord = {
  discord_user_id: string;
  display_name: string;
  seat: number;
  is_alive: boolean;
  role_name?: string | null;
  alignment?: string | null;
  reminders: string[];
  private_history: string[];
  night_action_prompt?: string | null;
  night_action_response?: string | null;
  night_action_submitted_at?: string | null;
};

type StorytellerState = {
  game_id: string;
  name: string;
  script: string;
  phase: string;
  storyteller_id?: string | null;
  players: PlayerRecord[];
  lobby_players: LobbyPlayer[];
  current_nomination?: {
    nominator_id: string;
    nominee_id: string;
    votes: Record<string, boolean>;
  } | null;
  log_entries: string[];
  night_feed: string[];
};

type Props = {
  auth: AuthState;
};

function buildBlankSeat(seat: number): SetupSeat {
  return {
    discord_user_id: '',
    display_name: '',
    seat,
    is_alive: true,
    role_name: null,
    alignment: null,
    reminders: [],
  };
}

function hydrateSeats(current: SetupSeat[], lobbyPlayers: LobbyPlayer[], playerCount: number): SetupSeat[] {
  const currentById = new Map(current.filter((seat) => seat.discord_user_id).map((seat) => [seat.discord_user_id, seat]));
  const usedIds = new Set<string>();

  return Array.from({ length: playerCount }, (_, seatIndex) => {
    const lobbyPlayer = lobbyPlayers[seatIndex];
    const existingSeat = current[seatIndex];
    const preservedSeat = lobbyPlayer
      ? currentById.get(lobbyPlayer.discord_user_id)
      : existingSeat && (!existingSeat.discord_user_id || !usedIds.has(existingSeat.discord_user_id))
        ? existingSeat
        : undefined;

    if (lobbyPlayer) {
      usedIds.add(lobbyPlayer.discord_user_id);
    } else if (preservedSeat?.discord_user_id) {
      usedIds.add(preservedSeat.discord_user_id);
    }

    return {
      ...buildBlankSeat(seatIndex),
      ...preservedSeat,
      discord_user_id: lobbyPlayer?.discord_user_id ?? preservedSeat?.discord_user_id ?? '',
      display_name: lobbyPlayer?.display_name ?? preservedSeat?.display_name ?? '',
      seat: seatIndex,
    };
  });
}

export default function StorytellerDashboard({ auth }: Props) {
  const [state, setState] = useState<StorytellerState | null>(null);
  const [scripts, setScripts] = useState<ScriptOption[]>([]);
  const [note, setNote] = useState('');
  const [scriptId, setScriptId] = useState('troubles_brewing');
  const [gameName, setGameName] = useState('Blood on the Clocktower');
  const [playerCount, setPlayerCount] = useState(7);
  const [setupSeats, setSetupSeats] = useState<SetupSeat[]>(() => hydrateSeats([], [], 7));
  const [selectedSeat, setSelectedSeat] = useState(0);
  const [nomination, setNomination] = useState({ nominator_id: '', nominee_id: '' });
  const [nightPrompt, setNightPrompt] = useState({ discord_user_id: '', prompt: '' });
  const [error, setError] = useState('');

  const activeScript = useMemo(
    () => scripts.find((script) => script.id === scriptId) ?? scripts[0],
    [scriptId, scripts]
  );

  const seatOptions = useMemo(() => state?.players ?? [], [state]);
  const lobbyPlayers = state?.lobby_players ?? [];

  const load = () => {
    fetch(apiUrl('/api/game/storyteller'), { credentials: 'include' })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error('Storyteller access is required for this dashboard.');
        }
        return response.json();
      })
      .then((payload: StorytellerState) => {
        setState(payload);
        setError('');
      })
      .catch((err: Error) => setError(err.message));
  };

  useEffect(() => {
    fetch(apiUrl('/api/game/setup-options'), { credentials: 'include' })
      .then((response) => response.json())
      .then((payload) => setScripts(payload.scripts ?? []))
      .catch(() => setScripts([]));
  }, []);

  useEffect(() => {
    if (!auth.user?.is_storyteller) {
      return;
    }

    load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, [auth.user?.is_storyteller]);

  useEffect(() => {
    setSetupSeats((current) => hydrateSeats(current, lobbyPlayers, playerCount));
    setSelectedSeat((current) => Math.min(current, Math.max(playerCount - 1, 0)));
  }, [playerCount, lobbyPlayers]);

  const updateSeat = (seatIndex: number, patch: Partial<SetupSeat>) => {
    setSetupSeats((current) =>
      current.map((seat, index) => (index === seatIndex ? { ...seat, ...patch } : seat))
    );
  };

  const assignRoleToSeat = (role: RoleOption) => {
    updateSeat(selectedSeat, { role_name: role.name, alignment: role.alignment });
  };

  const submitSetup = async () => {
    const emptySeats = setupSeats.filter((seat) => !seat.discord_user_id || !seat.display_name);
    if (emptySeats.length > 0) {
      setError('Wait for every player to log in with Discord so the storyteller lobby can fill all selected seats.');
      return;
    }

    const missingRoles = setupSeats.filter((seat) => !seat.role_name);
    if (missingRoles.length > 0) {
      setError('Every seated player needs a token before creating the game.');
      return;
    }

    const response = await fetch(apiUrl('/api/game/storyteller/game'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: gameName,
        script: scriptId,
        players: setupSeats,
      }),
    });

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setError(payload.detail ?? 'Game creation failed.');
      return;
    }

    const payload = await response.json();
    setState(payload.storyteller_state);
    setError('');
  };

  const setPhase = async (phase: string) => {
    const response = await fetch(apiUrl('/api/game/storyteller/phase'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phase }),
    });
    if (response.ok) {
      setState(await response.json());
    }
  };

  const openNomination = async () => {
    const response = await fetch(apiUrl('/api/game/storyteller/nomination'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(nomination),
    });
    if (response.ok) {
      setState(await response.json());
    }
  };

  const addNote = async (night: boolean) => {
    const response = await fetch(apiUrl('/api/game/storyteller/note'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: note, night }),
    });
    if (response.ok) {
      setState(await response.json());
      setNote('');
    }
  };

  const setAlive = async (discord_user_id: string, is_alive: boolean) => {
    const response = await fetch(apiUrl('/api/game/storyteller/alive'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ discord_user_id, is_alive }),
    });
    if (response.ok) {
      setState(await response.json());
    }
  };

  const sendNightPrompt = async () => {
    const response = await fetch(apiUrl('/api/game/storyteller/night-prompt'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(nightPrompt),
    });
    if (response.ok) {
      setState(await response.json());
      setNightPrompt({ discord_user_id: '', prompt: '' });
    }
  };

  if (!auth.user?.is_storyteller) {
    return <section className="panel"><p>Log in with a storyteller Discord account to use the dashboard.</p></section>;
  }

  return (
    <section className="panel stack">
      <div>
        <h2>Storyteller Dashboard</h2>
        <p className="muted">Players who log in with Discord now appear here automatically. Pick the script, set the player count, assign tokens, and create the game.</p>
        {error ? <p>{error}</p> : null}
      </div>

      <div className="card stack">
        <h3>Game Builder</h3>
        <div className="row">
          <input value={gameName} onChange={(event) => setGameName(event.target.value)} placeholder="Game name" />
          <select value={scriptId} onChange={(event) => setScriptId(event.target.value)}>
            {scripts.map((script) => (
              <option key={script.id} value={script.id}>{script.label}</option>
            ))}
          </select>
          <select value={playerCount} onChange={(event) => setPlayerCount(Number(event.target.value))}>
            {Array.from({ length: 11 }, (_, index) => index + 5).map((count) => (
              <option key={count} value={count}>{count} players</option>
            ))}
          </select>
        </div>

        <div className="card stack">
          <h3>Logged-in Lobby</h3>
          <p className="muted">Anyone who signs in with Discord and is not the storyteller shows up here automatically.</p>
          <div className="seat-grid">
            {lobbyPlayers.length > 0 ? lobbyPlayers.map((player) => (
              <article key={player.discord_user_id} className="seat">
                <strong>{player.display_name}</strong>
                <div className="muted">{player.discord_user_id}</div>
              </article>
            )) : <p className="muted">No players have logged in yet.</p>}
          </div>
        </div>

        <div className="setup-grid">
          <div className="stack">
            <h3>Auto-Seated Players</h3>
            <p className="muted">Seats fill in login order. Click a seat, then click a token to assign that character.</p>
            <div className="seat-grid">
              {setupSeats.map((seat, index) => (
                <article key={seat.seat} className="seat stack">
                  <div className="inline-form">
                    <button className={`seat-select ${selectedSeat === index ? 'active' : ''}`} onClick={() => setSelectedSeat(index)}>
                      Seat {seat.seat + 1}
                    </button>
                    {seat.role_name ? <span className="role-chip">{seat.role_name}</span> : null}
                  </div>
                  {seat.display_name ? (
                    <>
                      <strong>{seat.display_name}</strong>
                      <div className="muted">{seat.discord_user_id}</div>
                    </>
                  ) : (
                    <div className="muted">Waiting for a player login</div>
                  )}
                  <div className="muted">Alignment: {seat.alignment ?? 'Unassigned'}</div>
                </article>
              ))}
            </div>
          </div>

          <div className="stack">
            <h3>Playable Tokens</h3>
            <p className="muted">Select a seat, then click a token from the chosen script to assign it.</p>
            <div className="token-grid">
              {(activeScript?.roles ?? []).map((role) => (
                <button key={role.name} className={`token-button ${setupSeats[selectedSeat]?.role_name === role.name ? 'active' : ''}`} onClick={() => assignRoleToSeat(role)}>
                  {role.name}
                  <small>{role.group} · {role.alignment}</small>
                </button>
              ))}
            </div>
            {activeScript?.roles.find((role) => role.name === setupSeats[selectedSeat]?.role_name)?.description ? (
              <div className="card">
                <strong>{setupSeats[selectedSeat]?.role_name}</strong>
                <p className="muted">{activeScript?.roles.find((role) => role.name === setupSeats[selectedSeat]?.role_name)?.description}</p>
              </div>
            ) : null}
          </div>
        </div>

        <div className="inline-form">
          <button className="primary" onClick={submitSetup}>Create Game From Lobby</button>
          <button className="secondary" onClick={load}>Refresh Live State</button>
        </div>
      </div>

      <div className="split">
        <div className="stack">
          <div className="card stack">
            <h3>Phase Control</h3>
            <div className="inline-form">
              <button className="primary" onClick={() => setPhase('setup')}>Setup</button>
              <button className="primary" onClick={() => setPhase('night')}>Night</button>
              <button className="primary" onClick={() => setPhase('day')}>Day</button>
              <button className="secondary" onClick={() => setPhase('finished')}>Finish</button>
            </div>
          </div>

          <div className="card stack">
            <h3>Night Prompt Override</h3>
            <select value={nightPrompt.discord_user_id} onChange={(event) => setNightPrompt({ ...nightPrompt, discord_user_id: event.target.value })}>
              <option value="">Choose player</option>
              {seatOptions.map((player) => (
                <option key={player.discord_user_id} value={player.discord_user_id}>{player.display_name}</option>
              ))}
            </select>
            <textarea value={nightPrompt.prompt} onChange={(event) => setNightPrompt({ ...nightPrompt, prompt: event.target.value })} placeholder="Only tweak this if the auto-generated prompt needs custom storyteller context" />
            <button className="primary" onClick={sendNightPrompt}>Override Prompt</button>
          </div>

          <div className="card stack">
            <h3>Nomination</h3>
            <select value={nomination.nominator_id} onChange={(event) => setNomination({ ...nomination, nominator_id: event.target.value })}>
              <option value="">Choose nominator</option>
              {seatOptions.map((player) => (
                <option key={player.discord_user_id} value={player.discord_user_id}>{player.display_name}</option>
              ))}
            </select>
            <select value={nomination.nominee_id} onChange={(event) => setNomination({ ...nomination, nominee_id: event.target.value })}>
              <option value="">Choose nominee</option>
              {seatOptions.map((player) => (
                <option key={player.discord_user_id} value={player.discord_user_id}>{player.display_name}</option>
              ))}
            </select>
            <button className="primary" onClick={openNomination}>Open Nomination</button>
          </div>
        </div>

        <div className="stack">
          <div className="card">
            <h3>Grimoire</h3>
            <div className="seat-grid">
              {(state?.players ?? []).map((player) => (
                <article key={player.discord_user_id} className={`seat ${player.is_alive ? '' : 'dead'}`}>
                  <strong>{player.display_name}</strong>
                  <div>Seat {player.seat + 1}</div>
                  <div>{player.role_name ?? 'Unassigned'}</div>
                  <div className="muted">{player.alignment ?? 'Alignment hidden'}</div>
                  <div className="muted">Prompt ready: {player.night_action_prompt ? 'Yes' : 'No'}</div>
                  <div className="muted">Response: {player.night_action_response ?? 'Waiting'}</div>
                  <div className="inline-form">
                    <button className="secondary" onClick={() => setAlive(player.discord_user_id, !player.is_alive)}>
                      Mark {player.is_alive ? 'Dead' : 'Alive'}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </div>

          <div className="card stack">
            <h3>Storyteller Feed</h3>
            <textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add a log entry or a private night note" />
            <div className="inline-form">
              <button className="primary" onClick={() => addNote(false)}>Add Public Log</button>
              <button className="secondary" onClick={() => addNote(true)}>Add Night Feed Note</button>
            </div>
          </div>
        </div>
      </div>

      <div className="split">
        <div className="card">
          <h3>Game Log</h3>
          <ol className="log-list">
            {(state?.log_entries ?? []).map((entry, index) => (
              <li key={`${entry}-${index}`}>{entry}</li>
            ))}
          </ol>
        </div>
        <div className="card">
          <h3>Night Feed</h3>
          <ol className="log-list">
            {(state?.night_feed ?? []).map((entry, index) => (
              <li key={`${entry}-${index}`}>{entry}</li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
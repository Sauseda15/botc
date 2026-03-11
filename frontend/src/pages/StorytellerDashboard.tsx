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
  icon_url: string;
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
  storyteller_message?: string | null;
  status_markers?: string[];
  night_action_response?: string | null;
  night_action_submitted_at?: string | null;
  is_poisoned?: boolean;
  is_drunk?: boolean;
  pending_death?: boolean;
};

type ScriptReference = {
  id: string;
  label: string;
  roles: RoleOption[];
};

type NightStep = {
  step_id: string;
  order: number;
  role_name: string;
  player_id: string;
  player_name: string;
  audience: string;
  requires_response: boolean;
  requires_approval: boolean;
  player_prompt?: string | null;
  storyteller_prompt?: string | null;
  approval_prompt?: string | null;
  status: string;
  response_text?: string | null;
  resolution_note?: string | null;
};

type StorytellerState = {
  game_id: string;
  name: string;
  script: string;
  script_reference: ScriptReference;
  phase: string;
  storyteller_id?: string | null;
  players: PlayerRecord[];
  lobby_players: LobbyPlayer[];
  current_nomination?: {
    nominator_id: string;
    nominee_id: string;
    votes: Record<string, boolean>;
  } | null;
  current_night_step?: NightStep | null;
  night_steps: NightStep[];
  log_entries: string[];
  night_feed: string[];
};

type Props = {
  auth: AuthState;
};

const STATUS_PRESETS = [
  'Poisoned',
  'Drunk',
  'Dies at dawn',
  'Protected',
  'Mad',
  'Good Twin',
  'Fake Demon',
  'Show Grimoire',
];

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

function RoleIcon({ iconUrl, name }: { iconUrl?: string; name: string }) {
  if (!iconUrl) {
    return <div className="role-icon-fallback" aria-hidden="true">{name.slice(0, 1)}</div>;
  }
  return <img className="role-icon" src={iconUrl} alt={`${name} icon`} />;
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
  const [resolutionNote, setResolutionNote] = useState('');
  const [nightResolution, setNightResolution] = useState({
    death_target_id: '',
    poison_target_id: '',
    drunk_target_id: '',
    sober_target_id: '',
    healthy_target_id: '',
  });
  const [error, setError] = useState('');

  const activeScript = useMemo(
    () => scripts.find((script) => script.id === scriptId) ?? scripts[0],
    [scriptId, scripts]
  );

  const roleMap = new Map((state?.script_reference?.roles ?? activeScript?.roles ?? []).map((role) => [role.name, role]));
  const seatOptions = useMemo(() => state?.players ?? [], [state]);
  const lobbyPlayers = state?.lobby_players ?? [];
  const filledSeats = setupSeats.filter((seat) => seat.discord_user_id && seat.display_name).length;
  const assignedSeats = setupSeats.filter((seat) => seat.role_name).length;
  const playersNeeded = Math.max(playerCount - filledSeats, 0);
  const canCreateGame = filledSeats === playerCount && assignedSeats === playerCount;
  const currentNightStep = state?.current_night_step ?? null;

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
    if (!setupSeats[selectedSeat]?.discord_user_id) {
      setError('Pick a seat with a logged-in player before assigning a token.');
      return;
    }
    updateSeat(selectedSeat, { role_name: role.name, alignment: role.alignment });
    setError('');
  };

  const fillTestPlayers = async () => {
    const response = await fetch(apiUrl('/api/game/storyteller/test-players'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_count: playerCount }),
    });

    if (response.ok) {
      setState(await response.json());
      setError('');
    }
  };

  const clearTestPlayers = async () => {
    const response = await fetch(apiUrl('/api/game/storyteller/test-players/clear'), {
      method: 'POST',
      credentials: 'include',
    });

    if (response.ok) {
      setState(await response.json());
      setError('');
    }
  };
  const submitSetup = async () => {
    if (playersNeeded > 0) {
      setError(`You need ${playersNeeded} more logged-in player${playersNeeded === 1 ? '' : 's'} before starting this game.`);
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

  const updateStatus = async (
    discord_user_id: string,
    patch: {
      is_poisoned?: boolean;
      is_drunk?: boolean;
      pending_death?: boolean;
      add_statuses?: string[];
      remove_statuses?: string[];
    }
  ) => {
    const response = await fetch(apiUrl('/api/game/storyteller/status'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ discord_user_id, ...patch }),
    });
    if (response.ok) {
      setState(await response.json());
      setError('');
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

  const updateNightStep = async (mode: 'advance' | 'approve') => {
    const response = await fetch(apiUrl(`/api/game/storyteller/night/${mode}`), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        resolution_note: resolutionNote || null,
        death_target_ids: nightResolution.death_target_id ? [nightResolution.death_target_id] : [],
        poison_target_ids: nightResolution.poison_target_id ? [nightResolution.poison_target_id] : [],
        drunk_target_ids: nightResolution.drunk_target_id ? [nightResolution.drunk_target_id] : [],
        sober_target_ids: nightResolution.sober_target_id ? [nightResolution.sober_target_id] : [],
        healthy_target_ids: nightResolution.healthy_target_id ? [nightResolution.healthy_target_id] : [],
      }),
    });

    if (response.ok) {
      setState(await response.json());
      setResolutionNote('');
      setNightResolution({
        death_target_id: '',
        poison_target_id: '',
        drunk_target_id: '',
        sober_target_id: '',
        healthy_target_id: '',
      });
      setError('');
      return;
    }

    const payload = await response.json().catch(() => ({}));
    setError(payload.detail ?? 'Night step update failed.');
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
          <h3>Lobby Readiness</h3>
          <p><strong>{filledSeats}</strong> of <strong>{playerCount}</strong> players are checked in.</p>
          <p className="muted">
            {playersNeeded > 0
              ? `Waiting on ${playersNeeded} more player${playersNeeded === 1 ? '' : 's'} before you can start this table.`
              : assignedSeats < playerCount
                ? `Everyone is here. Assign ${playerCount - assignedSeats} more token${playerCount - assignedSeats === 1 ? '' : 's'} to start.`
                : 'Lobby is ready. You can create the game now.'}
          </p>
          <div className="inline-form">
            <button className="secondary" onClick={fillTestPlayers}>Fill With Test Players</button>
            <button className="secondary" onClick={clearTestPlayers}>Clear Test Players</button>
          </div>
        </div>

        <div className="setup-grid">
          <div className="stack">
            <h3>Auto-Seated Players</h3>
            <div className="seat-grid">
              {setupSeats.map((seat, index) => {
                const seatRole = seat.role_name ? roleMap.get(seat.role_name) : undefined;
                return (
                  <article key={seat.seat} className="seat stack">
                    <div className="inline-form">
                      <button className={`seat-select ${selectedSeat === index ? 'active' : ''}`} onClick={() => setSelectedSeat(index)}>
                        Seat {seat.seat + 1}
                      </button>
                      {seat.role_name ? (
                        <span className="role-chip">
                          <RoleIcon iconUrl={seatRole?.icon_url} name={seat.role_name} />
                          {seat.role_name}
                        </span>
                      ) : null}
                    </div>
                    {seat.display_name ? (
                      <>
                        <strong>{seat.display_name}</strong>
                        <div className="muted">{seat.discord_user_id}</div>
                      </>
                    ) : (
                      <div className="muted">Waiting for a player login</div>
                    )}
                  </article>
                );
              })}
            </div>
          </div>

          <div className="stack">
            <h3>Playable Tokens</h3>
            <div className="token-grid">
              {(activeScript?.roles ?? []).map((role) => (
                <button key={role.name} className={`token-button ${setupSeats[selectedSeat]?.role_name === role.name ? 'active' : ''}`} onClick={() => assignRoleToSeat(role)}>
                  <span className="token-heading">
                    <RoleIcon iconUrl={role.icon_url} name={role.name} />
                    <span>{role.name}</span>
                  </span>
                  <small>{role.group} · {role.alignment}</small>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="inline-form">
          <button className="primary" onClick={submitSetup} disabled={!canCreateGame}>Create Game From Lobby</button>
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
            <h3>Night Order</h3>
            {currentNightStep ? (
              <>
                <p><strong>Current Step:</strong> {currentNightStep.player_name} ({currentNightStep.role_name})</p>
                <p className="muted">Audience: {currentNightStep.audience} · Status: {currentNightStep.status}</p>
                {currentNightStep.player_prompt ? <p><strong>Player Prompt:</strong> {currentNightStep.player_prompt}</p> : null}
                {currentNightStep.storyteller_prompt ? <p><strong>Storyteller Prompt:</strong> {currentNightStep.storyteller_prompt}</p> : null}
                {currentNightStep.approval_prompt ? <p><strong>Approval Prompt:</strong> {currentNightStep.approval_prompt}</p> : null}
                {currentNightStep.response_text ? <p><strong>Player Response:</strong> {currentNightStep.response_text}</p> : null}
                {currentNightStep.resolution_note ? <p><strong>Last Resolution:</strong> {currentNightStep.resolution_note}</p> : null}
                <textarea value={resolutionNote} onChange={(event) => setResolutionNote(event.target.value)} placeholder="Information actually given, result returned, or judgment used for this step" />
                <div className="row">
                  <select value={nightResolution.death_target_id} onChange={(event) => setNightResolution({ ...nightResolution, death_target_id: event.target.value })}>
                    <option value="">No dawn death</option>
                    {seatOptions.map((player) => (
                      <option key={`death-${player.discord_user_id}`} value={player.discord_user_id}>{player.display_name}</option>
                    ))}
                  </select>
                  <select value={nightResolution.poison_target_id} onChange={(event) => setNightResolution({ ...nightResolution, poison_target_id: event.target.value })}>
                    <option value="">No poison update</option>
                    {seatOptions.map((player) => (
                      <option key={`poison-${player.discord_user_id}`} value={player.discord_user_id}>{player.display_name}</option>
                    ))}
                  </select>
                  <select value={nightResolution.drunk_target_id} onChange={(event) => setNightResolution({ ...nightResolution, drunk_target_id: event.target.value })}>
                    <option value="">No drunk update</option>
                    {seatOptions.map((player) => (
                      <option key={`drunk-${player.discord_user_id}`} value={player.discord_user_id}>{player.display_name}</option>
                    ))}
                  </select>
                </div>
                <div className="row">
                  <select value={nightResolution.sober_target_id} onChange={(event) => setNightResolution({ ...nightResolution, sober_target_id: event.target.value })}>
                    <option value="">No sober clear</option>
                    {seatOptions.map((player) => (
                      <option key={`sober-${player.discord_user_id}`} value={player.discord_user_id}>{player.display_name}</option>
                    ))}
                  </select>
                  <select value={nightResolution.healthy_target_id} onChange={(event) => setNightResolution({ ...nightResolution, healthy_target_id: event.target.value })}>
                    <option value="">No poison clear</option>
                    {seatOptions.map((player) => (
                      <option key={`healthy-${player.discord_user_id}`} value={player.discord_user_id}>{player.display_name}</option>
                    ))}
                  </select>
                </div>
                <div className="inline-form">
                  <button className="primary" onClick={() => updateNightStep('advance')}>Advance</button>
                  <button className="secondary" onClick={() => updateNightStep('approve')}>Approve And Continue</button>
                </div>
              </>
            ) : (
              <p className="muted">Move the game to night to generate the automatic night order.</p>
            )}
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
              {(state?.players ?? []).map((player) => {
                const playerRole = player.role_name ? roleMap.get(player.role_name) : undefined;
                return (
                  <article key={player.discord_user_id} className={`seat ${player.is_alive ? '' : 'dead'}`}>
                    <div className="role-heading">
                      <RoleIcon iconUrl={playerRole?.icon_url} name={player.role_name ?? player.display_name} />
                      <div>
                        <strong>{player.display_name}</strong>
                        <div>Seat {player.seat + 1}</div>
                      </div>
                    </div>
                    <div>{player.role_name ?? 'Unassigned'}</div>
                    <div className="muted">{player.alignment ?? 'Alignment hidden'}</div>
                    <div className="muted">Response: {player.night_action_response ?? 'Waiting'}</div>
                    <div className="muted">Status: {player.is_alive ? 'Alive' : 'Dead'}</div>
                    <div className="muted">Markers: {(player.status_markers ?? []).length > 0 ? (player.status_markers ?? []).join(' · ') : 'None'}</div>
                    {player.storyteller_message ? <div className="muted">Last Info: {player.storyteller_message}</div> : null}
                    <div className="inline-form">
                      <button className="secondary" onClick={() => setAlive(player.discord_user_id, !player.is_alive)}>
                        Mark {player.is_alive ? 'Dead' : 'Alive'}
                      </button>
                      <button className="secondary" onClick={() => updateStatus(player.discord_user_id, { pending_death: !player.pending_death })}>
                        {player.pending_death ? 'Clear Dawn Death' : 'Mark Dawn Death'}
                      </button>
                      <button className="secondary" onClick={() => updateStatus(player.discord_user_id, { is_poisoned: !player.is_poisoned })}>
                        {player.is_poisoned ? 'Clear Poison' : 'Poison'}
                      </button>
                      <button className="secondary" onClick={() => updateStatus(player.discord_user_id, { is_drunk: !player.is_drunk })}>
                        {player.is_drunk ? 'Clear Drunk' : 'Drunk'}
                      </button>
                    </div>
                    <div className="inline-form">
                      {STATUS_PRESETS.map((status) => {
                        const hasStatus = (player.status_markers ?? []).includes(status);
                        return (
                          <button
                            key={`${player.discord_user_id}-${status}`}
                            className="secondary"
                            onClick={() => updateStatus(player.discord_user_id, hasStatus ? { remove_statuses: [status] } : { add_statuses: [status] })}
                          >
                            {hasStatus ? `Clear ${status}` : status}
                          </button>
                        );
                      })}
                    </div>
                  </article>
                );
              })}
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



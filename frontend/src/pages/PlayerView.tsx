import React, { useEffect, useState } from 'react';

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

type PlayerRecord = {
  discord_user_id: string;
  display_name: string;
};

type PlayerState = {
  name: string;
  script: string;
  phase: string;
  players: Array<{
    discord_user_id: string;
    display_name: string;
    seat: number;
    is_alive: boolean;
  }>;
  current_nomination?: {
    nominator_id: string;
    nominee_id: string;
    votes: Record<string, boolean>;
  } | null;
  viewer?: {
    discord_user_id: string;
    display_name: string;
    role_name?: string | null;
    alignment?: string | null;
    reminders: string[];
    private_history: string[];
    night_action_prompt?: string | null;
    night_action_response?: string | null;
    night_action_submitted_at?: string | null;
  };
  viewer_context?: {
    requested_player_id: string;
    viewer_id: string;
    is_preview: boolean;
  };
};

type StorytellerState = {
  players: PlayerRecord[];
};

type Props = {
  auth: AuthState;
};

export default function PlayerView({ auth }: Props) {
  const [state, setState] = useState<PlayerState | null>(null);
  const [error, setError] = useState<string>('');
  const [nightAction, setNightAction] = useState('');
  const [storytellerPlayers, setStorytellerPlayers] = useState<PlayerRecord[]>([]);
  const [selectedPlayerId, setSelectedPlayerId] = useState('');

  const isStoryteller = Boolean(auth.user?.is_storyteller);
  const ownPlayerId = auth.user?.is_player ? auth.user.discord_user_id : '';

  const load = (targetPlayerId?: string) => {
    const requestedId = targetPlayerId ?? selectedPlayerId ?? ownPlayerId;
    const search = requestedId ? `?as_player=${encodeURIComponent(requestedId)}` : '';

    fetch(apiUrl(`/api/game/player${search}`), { credentials: 'include' })
      .then(async (response) => {
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.detail ?? 'Player view is only available to seated players.');
        }
        return response.json();
      })
      .then((payload: PlayerState) => {
        setState(payload);
        setNightAction(payload.viewer?.night_action_response ?? '');
        setSelectedPlayerId(payload.viewer?.discord_user_id ?? requestedId ?? '');
        setError('');
      })
      .catch((err: Error) => setError(err.message));
  };

  useEffect(() => {
    if (!auth.authenticated || !isStoryteller) {
      return;
    }

    fetch(apiUrl('/api/game/storyteller'), { credentials: 'include' })
      .then(async (response) => {
        if (!response.ok) {
          return { players: [] } as StorytellerState;
        }
        return response.json();
      })
      .then((payload: StorytellerState) => setStorytellerPlayers(payload.players ?? []))
      .catch(() => setStorytellerPlayers([]));
  }, [auth.authenticated, isStoryteller]);

  useEffect(() => {
    if (!auth.authenticated) {
      return;
    }

    if (ownPlayerId) {
      setSelectedPlayerId(ownPlayerId);
      load(ownPlayerId);
      return;
    }

    if (isStoryteller && storytellerPlayers.length > 0) {
      const firstPlayerId = storytellerPlayers[0].discord_user_id;
      setSelectedPlayerId(firstPlayerId);
      load(firstPlayerId);
      return;
    }

    if (isStoryteller) {
      setError('No seated players are available to preview yet.');
    }
  }, [auth.authenticated, ownPlayerId, isStoryteller, storytellerPlayers.length]);

  const castVote = async (approve: boolean) => {
    const response = await fetch(apiUrl('/api/game/player/vote'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approve }),
    });

    if (response.ok) {
      const payload = await response.json();
      setState(payload);
    }
  };

  const submitNightAction = async () => {
    const response = await fetch(apiUrl('/api/game/player/night-action'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ response: nightAction }),
    });

    if (response.ok) {
      const payload = await response.json();
      setState(payload);
      setError('');
      return;
    }

    const payload = await response.json();
    setError(payload.detail ?? 'Night action submission failed.');
  };

  if (!auth.authenticated) {
    return <section className="panel"><p>Log in with Discord to see your player view.</p></section>;
  }

  const isPreview = Boolean(state?.viewer_context?.is_preview);
  const isNight = state?.phase === 'night';
  const canSubmitNightAction = !isPreview && ownPlayerId === state?.viewer?.discord_user_id;

  return (
    <section className="panel split">
      <div className="stack">
        <div className="card stack">
          <h2>Player View</h2>
          {isStoryteller ? (
            <>
              <p className="muted">Storytellers can switch into player mode here to preview any seated player.</p>
              <select
                value={selectedPlayerId}
                onChange={(event) => {
                  const nextPlayerId = event.target.value;
                  setSelectedPlayerId(nextPlayerId);
                  load(nextPlayerId);
                }}
              >
                <option value="">Choose a player to preview</option>
                {storytellerPlayers.map((player) => (
                  <option key={player.discord_user_id} value={player.discord_user_id}>
                    {player.display_name}
                  </option>
                ))}
              </select>
            </>
          ) : null}
          {error ? <p>{error}</p> : null}
        </div>

        <div className="card">
          <h2>Your Role Sheet</h2>
          <p><strong>Role:</strong> {state?.viewer?.role_name ?? 'Hidden until storyteller assigns roles'}</p>
          <p><strong>Alignment:</strong> {state?.viewer?.alignment ?? 'Unknown'}</p>
          <p><strong>Phase:</strong> {state?.phase ?? 'setup'}</p>
          {isPreview ? <p className="muted">Preview mode is read-only for the storyteller.</p> : null}
        </div>

        <div className="card stack">
          <h3>Night Actions</h3>
          <p className="muted">Night actions now happen here in the player site instead of Discord.</p>
          {isNight ? (
            <>
              <p><strong>Prompt:</strong> {state?.viewer?.night_action_prompt ?? 'Wait for the storyteller to assign your night instruction.'}</p>
              <textarea
                value={nightAction}
                onChange={(event) => setNightAction(event.target.value)}
                placeholder="Enter your night action or question"
                disabled={!canSubmitNightAction}
              />
              <div className="inline-form">
                <button className="primary" onClick={submitNightAction} disabled={!canSubmitNightAction}>Submit Night Action</button>
                <button className="secondary" onClick={() => load()}>Refresh</button>
              </div>
              {!canSubmitNightAction ? <p className="muted">Preview mode can inspect prompts, but only the real player can submit the action.</p> : null}
              {state?.viewer?.night_action_submitted_at ? (
                <p className="muted">Last submitted at {new Date(state.viewer.night_action_submitted_at).toLocaleString()}.</p>
              ) : null}
            </>
          ) : (
            <p className="muted">The night-action panel becomes active when the storyteller moves the game to the night phase.</p>
          )}
        </div>

        <div className="card">
          <h3>Private History</h3>
          <ol className="log-list">
            {(state?.viewer?.private_history ?? []).map((entry, index) => (
              <li key={`${entry}-${index}`}>{entry}</li>
            ))}
          </ol>
        </div>
      </div>

      <div className="stack">
        <div className="card">
          <h3>Town Board</h3>
          <div className="seat-grid">
            {(state?.players ?? []).map((player) => (
              <article key={player.discord_user_id} className={`seat ${player.is_alive ? '' : 'dead'}`}>
                <strong>Seat {player.seat + 1}</strong>
                <div>{player.display_name}</div>
                <div className="muted">{player.is_alive ? 'Alive' : 'Dead'}</div>
              </article>
            ))}
          </div>
        </div>

        <div className="card stack">
          <h3>Voting</h3>
          <p className="muted">Daytime votes still happen here on the website.</p>
          <div className="inline-form">
            <button className="primary" onClick={() => castVote(true)} disabled={isPreview}>Vote Yes</button>
            <button className="secondary" onClick={() => castVote(false)} disabled={isPreview}>Vote No</button>
            <button className="secondary" onClick={() => load()}>Refresh</button>
          </div>
          {isPreview ? <p className="muted">Votes are disabled while the storyteller is previewing another player.</p> : null}
        </div>
      </div>
    </section>
  );
}
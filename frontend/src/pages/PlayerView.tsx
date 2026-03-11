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

type RoleReference = {
  name: string;
  alignment: string;
  group: string;
  description: string;
  icon_url: string;
};

type ScriptReference = {
  id: string;
  label: string;
  roles: RoleReference[];
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
  input_type?: string | null;
  target_count?: number | null;
  allow_self?: boolean;
  status: string;
  response_text?: string | null;
};

type PlayerRecord = {
  discord_user_id: string;
  display_name: string;
};

type PublicState = {
  name: string;
  script: string;
  script_reference: ScriptReference;
  phase: string;
  players: Array<{
    discord_user_id: string;
    display_name: string;
    seat: number;
    is_alive: boolean;
  }>;
};

type PlayerState = {
  name: string;
  script: string;
  script_reference: ScriptReference;
  phase: string;
  players: Array<{
    discord_user_id: string;
    display_name: string;
    seat: number;
    is_alive: boolean;
  }>;
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
  current_night_step?: NightStep | null;
};

type StorytellerState = {
  players: PlayerRecord[];
};

type Props = {
  auth: AuthState;
};

function RoleIcon({ iconUrl, name }: { iconUrl?: string; name: string }) {
  if (!iconUrl) {
    return <div className="role-icon-fallback" aria-hidden="true">{name.slice(0, 1)}</div>;
  }
  return <img className="role-icon" src={iconUrl} alt={`${name} icon`} />;
}

export default function PlayerView({ auth }: Props) {
  const [state, setState] = useState<PlayerState | null>(null);
  const [publicState, setPublicState] = useState<PublicState | null>(null);
  const [error, setError] = useState<string>('');
  const [nightAction, setNightAction] = useState('');
  const [selectedTargets, setSelectedTargets] = useState<string[]>([]);
  const [storytellerPlayers, setStorytellerPlayers] = useState<PlayerRecord[]>([]);
  const [selectedPlayerId, setSelectedPlayerId] = useState('');

  const isStoryteller = Boolean(auth.user?.is_storyteller);
  const ownPlayerId = auth.user?.is_player ? auth.user.discord_user_id : '';
  const roleMap = new Map((state?.script_reference?.roles ?? publicState?.script_reference?.roles ?? []).map((role) => [role.name, role]));
  const viewerRole = state?.viewer?.role_name ? roleMap.get(state.viewer.role_name) : undefined;
  const currentNightStep = state?.current_night_step ?? null;
  const activeTargetCount = currentNightStep?.input_type === 'player_select' ? (currentNightStep.target_count ?? 1) : 0;

  const selectablePlayers = state?.players.filter((player) => {
    if (currentNightStep?.allow_self === false && player.discord_user_id === state?.viewer?.discord_user_id) {
      return false;
    }
    return true;
  }) ?? [];

  const loadPublicState = () => {
    fetch(apiUrl('/api/game/public'), { credentials: 'include' })
      .then((response) => response.json())
      .then((payload: PublicState) => setPublicState(payload))
      .catch(() => setPublicState(null));
  };

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
        setSelectedTargets(
          (payload.viewer?.night_action_response ?? '')
            .split(',')
            .map((value) => value.trim())
            .filter(Boolean)
        );
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

    loadPublicState();

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
      return;
    }

    setState(null);
    setError('');
  }, [auth.authenticated, ownPlayerId, isStoryteller, storytellerPlayers.length]);

  useEffect(() => {
    if (currentNightStep?.input_type !== 'player_select') {
      return;
    }
    setSelectedTargets((current) => Array.from({ length: activeTargetCount }, (_, index) => current[index] ?? ''));
  }, [currentNightStep?.step_id, currentNightStep?.input_type, activeTargetCount]);

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

  const updateSelectedTarget = (index: number, value: string) => {
    setSelectedTargets((current) => {
      const next = Array.from({ length: activeTargetCount }, (_, targetIndex) => current[targetIndex] ?? '');
      next[index] = value;
      return next;
    });
  };

  const resolvedNightAction = currentNightStep?.input_type === 'player_select'
    ? selectedTargets.filter(Boolean).join(', ')
    : nightAction;

  const submitNightAction = async () => {
    const response = await fetch(apiUrl('/api/game/player/night-action'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ response: resolvedNightAction }),
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

  if (!ownPlayerId && !isStoryteller) {
    return (
      <section className="panel split">
        <div className="stack">
          <div className="card">
            <h2>Waiting Room</h2>
            <p><strong>{auth.user?.username}</strong>, you are checked in and visible to the storyteller.</p>
            <p className="muted">You will unlock your player sheet automatically once the storyteller seats you in the current game.</p>
          </div>
        </div>
      </section>
    );
  }

  const isPreview = Boolean(state?.viewer_context?.is_preview);
  const isNight = state?.phase === 'night';
  const isViewerTurn = currentNightStep?.player_id === state?.viewer?.discord_user_id && currentNightStep?.audience === 'player';
  const canSubmitNightAction = !isPreview && ownPlayerId === state?.viewer?.discord_user_id && Boolean(isViewerTurn);
  const currentTurnLabel = currentNightStep ? `${currentNightStep.player_name}'s` : 'the storyteller\'s';
  const needsPlayerSelect = currentNightStep?.input_type === 'player_select';
  const hasAllTargets = !needsPlayerSelect || selectedTargets.filter(Boolean).length === activeTargetCount;

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

        <div className="card stack">
          <h2>Your Role Sheet</h2>
          <div className="role-heading large">
            <RoleIcon iconUrl={viewerRole?.icon_url} name={state?.viewer?.role_name ?? 'Role'} />
            <div>
              <p><strong>Role:</strong> {state?.viewer?.role_name ?? 'Hidden until storyteller assigns roles'}</p>
              <p><strong>Alignment:</strong> {state?.viewer?.alignment ?? 'Unknown'}</p>
              <p><strong>Phase:</strong> {state?.phase ?? 'setup'}</p>
            </div>
          </div>
          {viewerRole?.description ? <p className="muted">{viewerRole.description}</p> : null}
          {isPreview ? <p className="muted">Preview mode is read-only for the storyteller.</p> : null}
        </div>

        <div className="card stack">
          <h3>Night Actions</h3>
          <p className="muted">Night actions now happen here in the player site instead of Discord.</p>
          {isNight ? (
            isViewerTurn ? (
              <>
                <p><strong>Prompt:</strong> {state?.viewer?.night_action_prompt ?? currentNightStep?.player_prompt ?? 'Wait for the storyteller to assign your night instruction.'}</p>
                {needsPlayerSelect ? (
                  <div className="stack">
                    {Array.from({ length: activeTargetCount }, (_, index) => (
                      <select key={index} value={selectedTargets[index] ?? ''} onChange={(event) => updateSelectedTarget(index, event.target.value)} disabled={!canSubmitNightAction}>
                        <option value="">Choose player {index + 1}</option>
                        {selectablePlayers.map((player) => (
                          <option key={`${index}-${player.discord_user_id}`} value={player.discord_user_id}>
                            {player.display_name} (Seat {player.seat + 1})
                          </option>
                        ))}
                      </select>
                    ))}
                  </div>
                ) : (
                  <textarea value={nightAction} onChange={(event) => setNightAction(event.target.value)} placeholder="Enter your night action or question" disabled={!canSubmitNightAction} />
                )}
                <div className="inline-form">
                  <button className="primary" onClick={submitNightAction} disabled={!canSubmitNightAction || !hasAllTargets}>Submit Night Action</button>
                  <button className="secondary" onClick={() => load()}>Refresh</button>
                </div>
                {currentNightStep?.status === 'awaiting_approval' ? <p className="muted">Your action is in. The storyteller is reviewing it before the night continues.</p> : null}
              </>
            ) : (
              <>
                <p className="muted">It is currently {currentTurnLabel} step.</p>
                {currentNightStep?.storyteller_prompt ? <p><strong>Storyteller is resolving:</strong> {currentNightStep.storyteller_prompt}</p> : null}
                <button className="secondary" onClick={() => load()}>Refresh</button>
              </>
            )
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
          <h3>Script Sheet</h3>
          <div className="role-reference-grid">
            {(state?.script_reference?.roles ?? []).map((role) => (
              <article key={role.name} className="role-reference-card">
                <div className="role-heading">
                  <RoleIcon iconUrl={role.icon_url} name={role.name} />
                  <div>
                    <strong>{role.name}</strong>
                    <div className="muted">{role.group} · {role.alignment}</div>
                  </div>
                </div>
                <p className="muted">{role.description}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="card stack">
          <h3>Voting</h3>
          <div className="inline-form">
            <button className="primary" onClick={() => castVote(true)} disabled={isPreview}>Vote Yes</button>
            <button className="secondary" onClick={() => castVote(false)} disabled={isPreview}>Vote No</button>
            <button className="secondary" onClick={() => load()}>Refresh</button>
          </div>
        </div>
      </div>
    </section>
  );
}

import React, { useEffect, useRef, useState } from 'react';

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
  statuses?: string[];
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
  current_nomination?: {
    nominator_id: string;
    nominee_id: string;
    opened_at: string;
    votes: Record<string, boolean>;
    vote_order: string[];
    current_voter_id?: string | null;
    seconds_remaining: number;
    resolved_at?: string | null;
    result_vote_count: number;
    required_votes: number;
  } | null;
  execution_candidate_id?: string | null;
  execution_candidate_votes?: number;
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
  current_nomination?: PublicState['current_nomination'];
  execution_candidate_id?: string | null;
  execution_candidate_votes?: number;
  viewer?: {
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
    dead_vote_available?: boolean;
  };
  viewer_evil_team?: Array<{
    discord_user_id: string;
    display_name: string;
    seat_label: string;
    team_role: string;
  }>;
  viewer_context?: {
    requested_player_id: string;
    viewer_id: string;
    is_preview: boolean;
  };
  current_night_step?: NightStep | null;
  viewer_grimoire?: Array<{
    discord_user_id: string;
    display_name: string;
    seat: number;
    is_alive: boolean;
    role_name?: string | null;
    alignment?: string | null;
    status_markers?: string[];
    reminders: string[];
  }> | null;
  viewer_demon_bluffs?: string[];
};

type StorytellerState = {
  players: PlayerRecord[];
};

type Props = {
  auth: AuthState;
};

type RoleIconProps = {
    iconUrl?: string | null;
    name: string;
    variant?: "default" | "player";
};

function RoleIcon({ iconUrl, name, variant = "default"}: RoleIconProps) {
    if (!iconUrl) return null;

    return (
        <img
            className={`role-icon ${variant === "player" ? "player-role-icon" : ""}`}
            src={iconUrl}
            alt={`${name} icon`}
        />
    );
}

export default function PlayerView({ auth }: Props) {
  const [state, setState] = useState<PlayerState | null>(null);
  const [publicState, setPublicState] = useState<PublicState | null>(null);
  const [error, setError] = useState<string>('');
  const [nightAction, setNightAction] = useState('');
  const [selectedTargets, setSelectedTargets] = useState<string[]>([]);
  const [storytellerPlayers, setStorytellerPlayers] = useState<PlayerRecord[]>([]);
  const [selectedPlayerId, setSelectedPlayerId] = useState('');
  const [nowMs, setNowMs] = useState(() => Date.now());
  const draftDirtyRef = useRef(false);
  const lastStepIdRef = useRef<string | null>(null);

  const isStoryteller = Boolean(auth.user?.is_storyteller);
  const ownPlayerId = auth.user?.discord_user_id ?? '';
  const roleMap = new Map((state?.script_reference?.roles ?? publicState?.script_reference?.roles ?? []).map((role) => [role.name, role]));
  const viewerRole = state?.viewer?.role_name ? roleMap.get(state.viewer.role_name) : undefined;
  const currentNightStep = state?.current_night_step ?? null;
  const activeTargetCount = currentNightStep?.input_type === 'player_select' ? (currentNightStep.target_count ?? 1) : 0;
  const viewerGrimoire = state?.viewer_grimoire ?? null;
  const viewerDemonBluffs = state?.viewer_demon_bluffs ?? [];
  const viewerEvilTeam = state?.viewer_evil_team ?? [];
  const nominationState = state?.current_nomination ?? publicState?.current_nomination ?? null;
  const executionCandidateId = state?.execution_candidate_id ?? publicState?.execution_candidate_id ?? null;
  const executionCandidateVotes = state?.execution_candidate_votes ?? publicState?.execution_candidate_votes ?? 0;
  const playerNameById = new Map((state?.players ?? publicState?.players ?? []).map((player) => [player.discord_user_id, player.display_name]));
  const pollIntervalMs = nominationState && !nominationState.resolved_at ? 1000 : 4000;
  const liveSecondsRemaining = nominationState && !nominationState.resolved_at ? Math.max(0, 5 - (Math.floor((nowMs - new Date(nominationState.opened_at).getTime()) / 1000) % 5)) : nominationState?.seconds_remaining ?? 0;

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
        const incomingStepId = payload.current_night_step?.step_id ?? null;
        const incomingResponse = payload.viewer?.night_action_response ?? '';
        const shouldSyncDraft =
          incomingStepId !== lastStepIdRef.current ||
          !draftDirtyRef.current ||
          Boolean(incomingResponse) ||
          payload.current_night_step?.status === 'awaiting_approval' ||
          payload.current_night_step?.status === 'complete' ||
          payload.current_night_step?.player_id !== payload.viewer?.discord_user_id;

        setState(payload);
        if (shouldSyncDraft) {
          setNightAction(incomingResponse);
          setSelectedTargets(
            incomingResponse
              .split(',')
              .map((value) => value.trim())
              .filter(Boolean)
          );
          draftDirtyRef.current = false;
        }
        lastStepIdRef.current = incomingStepId;
        setSelectedPlayerId(payload.viewer?.discord_user_id ?? requestedId ?? '');
        setError('');
      })
      .catch((err: Error) => setError(err.message));
  };


  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
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
    if (!auth.authenticated) {
      return;
    }

    const pollTargetId = ownPlayerId || selectedPlayerId || (isStoryteller && storytellerPlayers.length > 0 ? storytellerPlayers[0].discord_user_id : '');
    const refresh = () => {
      loadPublicState();
      if (pollTargetId) {
        load(pollTargetId);
      }
    };

    const timer = window.setInterval(refresh, pollIntervalMs);
    return () => window.clearInterval(timer);
  }, [auth.authenticated, ownPlayerId, selectedPlayerId, isStoryteller, storytellerPlayers, pollIntervalMs]);

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
    draftDirtyRef.current = true;
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
      body: JSON.stringify({
        response: resolvedNightAction,
        target_player_id: isPreview ? state?.viewer?.discord_user_id ?? null : null,
      }),
    });

    if (response.ok) {
      const payload = await response.json();
      setState(payload);
      draftDirtyRef.current = false;
      setError('');
      return;
    }

    const payload = await response.json();
    setError(payload.detail ?? 'Night action submission failed.');
  };

  const signalGrimoireReady = async () => {
    const response = await fetch(apiUrl('/api/game/player/night-ready'), {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_player_id: isPreview ? state?.viewer?.discord_user_id ?? null : null,
      }),
    });

    if (response.ok) {
      const payload = await response.json();
      setState(payload);
      setError('');
      return;
    }

    const payload = await response.json();
    setError(payload.detail ?? 'Ready signal failed.');
  };

  if (!auth.authenticated) {
    return <section className="panel"><p>Log in with Discord to see your player view.</p></section>;
  }

  if (!auth.user?.discord_user_id && !isStoryteller) {
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
  const canPreviewSubmit = isPreview && isStoryteller && Boolean(isViewerTurn);

  const needsPlayerSelect = currentNightStep?.input_type === 'player_select';
  const hasAllTargets = !needsPlayerSelect || selectedTargets.filter(Boolean).length === activeTargetCount;
  const canSignalGrimoireReady = Boolean(viewerGrimoire) && Boolean(isViewerTurn);
  const currentVoterId = nominationState?.current_voter_id ?? null;
  const isCurrentVoter = currentVoterId === state?.viewer?.discord_user_id;
  const nomineeName = nominationState?.nominee_id ? playerNameById.get(nominationState.nominee_id) ?? nominationState.nominee_id : null;
  const nominatorName = nominationState?.nominator_id ? playerNameById.get(nominationState.nominator_id) ?? nominationState.nominator_id : null;
  const executionCandidateName = executionCandidateId ? playerNameById.get(executionCandidateId) ?? executionCandidateId : null;

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
          <div className="role-heading large player-role-sheet">
            <RoleIcon iconUrl={viewerRole?.icon_url} name={viewerRole?.name ?? 'Role'} variant="player" />
            <div className="player-role-summary">
              <p className="role-line">
                <strong>Role:</strong> {state?.viewer?.role_name ?? 'Hidden until storyteller assigns roles'}
              </p>
              <p className="role-line">
                <strong>Alignment:</strong> {state?.viewer?.alignment ?? 'Unknown'}
              </p>
              <p className="role-line">
                <strong>Phase:</strong> {state?.phase ? state.phase.charAt(0).toUpperCase() + state.phase.slice(1) : 'Setup'}
              </p>
            </div>
          </div>

          {viewerRole?.description ? <p className="muted">{viewerRole.description}</p> : null}
          {isPreview ? <p className="muted">Preview mode lets the storyteller inspect this player view and test actions when it is this player's turn.</p> : null}
        </div>

        <div className="card stack">
          <h3>Night Actions</h3>
          <p className="muted">Your active night prompt and any storyteller-delivered result will appear here.</p>
          {viewerGrimoire ? <p><strong>Spy Info:</strong> The grimoire is visible until the storyteller advances past your night step.</p> : null}
          {isNight ? (
            isViewerTurn ? (
              <>
                <p><strong>Prompt:</strong> {state?.viewer?.night_action_prompt ?? currentNightStep?.player_prompt ?? 'Wait for the storyteller to assign your night instruction.'}</p>
                {state?.viewer?.storyteller_message ? <p><strong>Storyteller Info:</strong> {state.viewer.storyteller_message}</p> : null}
                {needsPlayerSelect ? (
                  <div className="stack">
                    {Array.from({ length: activeTargetCount }, (_, index) => (
                      <select key={index} value={selectedTargets[index] ?? ''} onChange={(event) => updateSelectedTarget(index, event.target.value)} disabled={!(canSubmitNightAction || canPreviewSubmit)}>
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
                  <textarea value={nightAction} onChange={(event) => { draftDirtyRef.current = true; setNightAction(event.target.value); }} placeholder="Enter your night action or question" disabled={!(canSubmitNightAction || canPreviewSubmit)} />
                )}
                <div className="inline-form">
                  <button className="primary" onClick={submitNightAction} disabled={(!(canSubmitNightAction || canPreviewSubmit)) || !hasAllTargets}>
                    {canPreviewSubmit ? 'Submit Test Night Action' : 'Submit Night Action'}
                  </button>
                  {canSignalGrimoireReady ? (
                    <button className="secondary" onClick={signalGrimoireReady}>
                      {isPreview ? 'Mark Spy Done (Test)' : 'I Reviewed The Grimoire'}
                    </button>
                  ) : null}
                  <button className="secondary" onClick={() => load()}>Refresh</button>
                </div>
                {canPreviewSubmit ? <p className="muted">Storyteller preview can submit a test action for this player while you are debugging.</p> : null}
                {currentNightStep?.status === 'awaiting_approval' ? <p className="muted">Your action is in. The storyteller is reviewing it before the night continues.</p> : null}
              </>
            ) : (
              <>
                {state?.viewer?.storyteller_message ? <p><strong>Storyteller Info:</strong> {state.viewer.storyteller_message}</p> : <p className="muted">Another player's night step is currently being resolved.</p>}
                <button className="secondary" onClick={() => load()}>Refresh</button>
              </>
            )
          ) : (
            <p className="muted">The night-action panel becomes active when the storyteller moves the game to the night phase.</p>
          )}
        </div>

        {viewerEvilTeam.length > 0 ? (
          <div className="card stack bluff-card">
            <h3>Evil Team</h3>
            <p className="muted">With 8 or more players in the night, evil learns who else is on the evil team.</p>
            <div className="role-reference-grid compact">
              {viewerEvilTeam.map((player) => (
                <article key={player.discord_user_id} className="role-reference-card compact">
                  <strong>{player.display_name}</strong>
                  <div className="muted">{player.team_role} · {player.seat_label}</div>
                </article>
              ))}
            </div>
          </div>
        ) : null}

        {viewerDemonBluffs.length > 0 ? (
          <div className="card stack bluff-card">
            <h3>Demon Bluffs</h3>
            <p className="muted">These are the storyteller-provided out-of-play roles you can bluff as.</p>
            <div className="role-reference-grid compact">
              {viewerDemonBluffs.map((roleName) => {
                const bluffRole = roleMap.get(roleName);
                return (
                  <article key={roleName} className="role-reference-card compact">
                    <div className="role-heading">
                      <RoleIcon iconUrl={bluffRole?.icon_url} name={roleName} />
                      <div>
                        <strong>{roleName}</strong>
                        <div className="muted">{bluffRole?.group ?? 'Role'} · {bluffRole?.alignment ?? 'Unknown'}</div>
                      </div>
                    </div>
                    {bluffRole?.description ? <p className="muted">{bluffRole.description}</p> : null}
                  </article>
                );
              })}
            </div>
          </div>
        ) : null}

        {viewerGrimoire ? (
          <div className="card stack">
            <h3>Visible Grimoire</h3>
            <div className="seat-grid">
              {viewerGrimoire.map((player) => {
                const grimRole = player.role_name ? roleMap.get(player.role_name) : undefined;
                return (
                  <article key={player.discord_user_id} className={`seat ${player.is_alive ? '' : 'dead'}`}>
                    <div className="role-heading">
                      <RoleIcon iconUrl={grimRole?.icon_url} name={player.role_name ?? player.display_name} />
                      <div>
                        <strong>{player.display_name}</strong>
                        <div>Seat {player.seat + 1}</div>
                      </div>
                    </div>
                    <div>{player.role_name ?? 'Unknown Role'}</div>
                    <div className="muted">{player.alignment ?? 'Unknown alignment'}</div>
                    <div className="muted">{player.is_alive ? 'Alive' : 'Dead'}</div>
                    <div className="muted">Markers: {(player.status_markers ?? []).length ? player.status_markers?.join(' · ') : 'None'}</div>
                    <div className="muted">Reminders: {(player.reminders ?? []).length ? player.reminders.join(' · ') : 'None'}</div>
                  </article>
                );
              })}
            </div>
          </div>
        ) : null}

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
                    <div className="muted">{role.group.charAt(0).toUpperCase() + role.group.slice(1)} · {role.alignment}</div>
                  </div>
                </div>
                <p className="muted">{role.description}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="card stack">
          <h3>Voting</h3>
          {nominationState ? (
            <>
              <p><strong>Nominator:</strong> {nominatorName ?? 'Unknown'}<br /><strong>Nominee:</strong> {nomineeName ?? 'Unknown'}</p>
              {nominationState.resolved_at ? (
                <p className="muted">Vote locked: {nominationState.result_vote_count} yes vote(s). {nominationState.result_vote_count >= nominationState.required_votes ? 'The nomination reached the execution threshold.' : 'The nomination failed to reach the execution threshold.'}</p>
              ) : (
                <p className="muted">Current voter: {currentVoterId ? (playerNameById.get(currentVoterId) ?? currentVoterId) : 'Locking votes'} · {liveSecondsRemaining}s remaining</p>
              )}
              {executionCandidateName ? <p className="muted">Currently marked for execution: {executionCandidateName} ({executionCandidateVotes} vote(s))</p> : <p className="muted">No player is currently marked for execution.</p>}
              <div className="inline-form">
                <button className="primary" onClick={() => castVote(true)} disabled={isPreview || !isCurrentVoter || Boolean(nominationState.resolved_at) || (!state?.viewer?.is_alive && !state?.viewer?.dead_vote_available)}>Vote Yes</button>
                <button className="secondary" onClick={() => castVote(false)} disabled={isPreview || !isCurrentVoter || Boolean(nominationState.resolved_at)}>Vote No</button>
                <button className="secondary" onClick={() => load()}>Refresh</button>
              </div>
              {!state?.viewer?.is_alive ? <p className="muted">Dead vote token: {state?.viewer?.dead_vote_available ? 'Available' : 'Already used'}</p> : null}
            </>
          ) : (
            <>
              {executionCandidateName ? <p className="muted">Currently marked for execution: {executionCandidateName} ({executionCandidateVotes} vote(s))</p> : <p className="muted">No nomination is active right now.</p>}
              <button className="secondary" onClick={() => load()}>Refresh</button>
            </>
          )}
        </div>
      </div>
    </section>
  );
}




















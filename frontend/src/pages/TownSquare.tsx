import React, { useEffect, useState } from 'react';

import { apiUrl } from '../api';

type PublicPlayer = {
  discord_user_id: string;
  display_name: string;
  seat: number;
  is_alive: boolean;
};

type PublicState = {
  name: string;
  script: string;
  phase: string;
  players: PublicPlayer[];
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
  log_entries: string[];
};

export default function TownSquare() {
  const [state, setState] = useState<PublicState | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  const nominationState = state?.current_nomination ?? null;
  const playerNameById = new Map((state?.players ?? []).map((player) => [player.discord_user_id, player.display_name]));
  const liveElapsedSeconds = nominationState && !nominationState.resolved_at
    ? Math.max(0, Math.floor((nowMs - new Date(nominationState.opened_at).getTime()) / 1000))
    : 0;
  const liveSecondsRemaining = nominationState && !nominationState.resolved_at
    ? Math.max(0, 10 - (liveElapsedSeconds % 10))
    : nominationState?.seconds_remaining ?? 0;
  const liveVoteIndex = nominationState && !nominationState.resolved_at
    ? Math.floor(liveElapsedSeconds / 10)
    : -1;
  const liveCurrentVoterId = nominationState && !nominationState.resolved_at
    ? (nominationState.vote_order[Math.min(liveVoteIndex, Math.max(nominationState.vote_order.length - 1, 0))] ?? null)
    : null;
  const liveCurrentVoterName = liveCurrentVoterId ? (playerNameById.get(liveCurrentVoterId) ?? liveCurrentVoterId) : 'Locking votes';
  const nominatorName = nominationState?.nominator_id ? (playerNameById.get(nominationState.nominator_id) ?? nominationState.nominator_id) : 'Unknown';
  const nomineeName = nominationState?.nominee_id ? (playerNameById.get(nominationState.nominee_id) ?? nominationState.nominee_id) : 'Unknown';
  const executionCandidateName = state?.execution_candidate_id ? (playerNameById.get(state.execution_candidate_id) ?? state.execution_candidate_id) : null;

  useEffect(() => {
    const load = () => {
      fetch(apiUrl('/api/game/public'), { credentials: 'include' })
        .then((response) => response.json())
        .then(setState)
        .catch(() => setState(null));
    };

    load();
    const timer = window.setInterval(load, nominationState && !nominationState.resolved_at ? 1000 : 4000);
    return () => window.clearInterval(timer);
  }, [nominationState?.opened_at, nominationState?.resolved_at]);

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <section className="panel stack">
      <div>
        <h2>Town Square</h2>
        <p className="muted">Public state only. No secret roles, hidden tokens, or private notes.</p>
      </div>

      <div className="row">
        <div className="card"><strong>Game</strong><div>{state?.name ?? 'No active game'}</div></div>
        <div className="card"><strong>Script</strong><div>{state?.script ?? 'Unassigned'}</div></div>
        <div className="card"><strong>Phase</strong><div>{state?.phase ?? 'setup'}</div></div>
      </div>

      <div>
        <h3>Seats</h3>
        <div className="seat-grid">
          {state?.players?.map((player) => (
            <article key={player.discord_user_id} className={`seat ${player.is_alive ? '' : 'dead'}`}>
              <strong>Seat {player.seat}</strong>
              <div>{player.display_name}</div>
              <div className="muted">{player.is_alive ? 'Alive' : 'Dead'}</div>
            </article>
          ))}
        </div>
      </div>

      <div className="split">
        <div className="card">
          <h3>Current Nomination</h3>
          {nominationState ? (
            <div className="stack">
              <span>Nominator: {nominatorName}</span>
              <span>Nominee: {nomineeName}</span>
              <span>Votes cast: {Object.keys(nominationState.votes).length}</span>
              {nominationState.resolved_at ? (
                <span>Vote locked: {nominationState.result_vote_count} yes vote(s)</span>
              ) : (
                <span>Current voter: {liveCurrentVoterName} · {liveSecondsRemaining}s remaining</span>
              )}
              {executionCandidateName ? (
                <span>Marked for execution: {executionCandidateName} ({state?.execution_candidate_votes ?? 0} vote(s))</span>
              ) : null}
            </div>
          ) : (
            <p className="muted">No open nomination.</p>
          )}
        </div>

        <div className="card">
          <h3>Public Log</h3>
          <ol className="log-list">
            {(state?.log_entries ?? []).map((entry, index) => (
              <li key={`${entry}-${index}`}>{entry}</li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

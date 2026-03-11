import React, { useEffect, useState } from 'react';

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
    votes: Record<string, boolean>;
  } | null;
  log_entries: string[];
};

export default function TownSquare() {
  const [state, setState] = useState<PublicState | null>(null);

  useEffect(() => {
    fetch('/api/game/public', { credentials: 'include' })
      .then((response) => response.json())
      .then(setState)
      .catch(() => setState(null));
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
          {state?.current_nomination ? (
            <div className="stack">
              <span>Nominator: {state.current_nomination.nominator_id}</span>
              <span>Nominee: {state.current_nomination.nominee_id}</span>
              <span>Votes cast: {Object.keys(state.current_nomination.votes).length}</span>
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
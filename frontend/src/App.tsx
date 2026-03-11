import React, { useEffect, useState } from 'react';

import { apiUrl } from './api';
import GameSetup from './pages/GameSetup';
import PlayerView from './pages/PlayerView';
import StorytellerDashboard from './pages/StorytellerDashboard';
import TownSquare from './pages/TownSquare';

type AuthState = {
  authenticated: boolean;
  user?: {
    discord_user_id: string;
    username: string;
    is_storyteller: boolean;
    is_player: boolean;
  };
};

type ViewKey = 'public' | 'player' | 'storyteller';

export default function App() {
  const [auth, setAuth] = useState<AuthState>({ authenticated: false });
  const [activeView, setActiveView] = useState<ViewKey>('public');

  useEffect(() => {
    fetch(apiUrl('/api/auth/me'), { credentials: 'include' })
      .then((response) => response.json())
      .then((payload: AuthState) => {
        setAuth(payload);
        if (payload.user?.is_storyteller) {
          setActiveView('storyteller');
        } else if (payload.user?.is_player) {
          setActiveView('player');
        }
      })
      .catch(() => setAuth({ authenticated: false }));
  }, []);

  return (
    <div className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Blood on the Clocktower</p>
          <h1>Black glass, red control, live Discord lobby.</h1>
          <p className="lede">
            Players log in with Discord, appear in the storyteller lobby automatically, get seated into the game, and the storyteller can still jump into a player-facing preview whenever needed.
          </p>
        </div>
        <GameSetup auth={auth} />
      </header>

      <nav className="tabs">
        <button className={activeView === 'public' ? 'active' : ''} onClick={() => setActiveView('public')}>Town Square</button>
        <button className={activeView === 'player' ? 'active' : ''} onClick={() => setActiveView('player')}>Player View</button>
        <button className={activeView === 'storyteller' ? 'active' : ''} onClick={() => setActiveView('storyteller')}>Storyteller</button>
      </nav>

      <main className="panel-grid">
        {activeView === 'public' && <TownSquare />}
        {activeView === 'player' && <PlayerView auth={auth} />}
        {activeView === 'storyteller' && <StorytellerDashboard auth={auth} />}
      </main>
    </div>
  );
}
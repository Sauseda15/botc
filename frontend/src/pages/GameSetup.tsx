import React from 'react';

type AuthState = {
  authenticated: boolean;
  user?: {
    discord_user_id: string;
    username: string;
    is_storyteller: boolean;
    is_player: boolean;
  };
};

type Props = {
  auth: AuthState;
};

export default function GameSetup({ auth }: Props) {
  const loginUrl = '/api/auth/login?next=/';

  const logout = async () => {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
    });
    window.location.reload();
  };

  return (
    <section className="card stack">
      <div>
        <h2>Web Access</h2>
        <p className="muted">Use Discord OAuth in the browser so the storyteller and players land in the right control layer automatically.</p>
      </div>

      {!auth.authenticated ? (
        <a className="primary" href={loginUrl}>Log In With Discord</a>
      ) : (
        <>
          <div>
            <strong>{auth.user?.username}</strong>
            <p className="muted">
              {auth.user?.is_storyteller ? 'Storyteller access enabled.' : auth.user?.is_player ? 'Player access enabled.' : 'Viewer access only.'}
            </p>
          </div>
          <button className="secondary" onClick={logout}>Log Out</button>
        </>
      )}

      <div className="stack muted">
        <span>Primary color system: black base with red action states</span>
        <span>Storyteller flow: choose script, choose player count, assign tokens, then run the game</span>
        <span>Night flow: backend generates prompts automatically from assigned roles</span>
      </div>
    </section>
  );
}

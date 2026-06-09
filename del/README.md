# ADK Porch

A wrapper service that adds Google OAuth sign-in ahead of the stock `adk web` developer UI. Users authenticate once, tokens are stored for the agents, and their browser traffic is proxied to the upstream ADK Web server only after login.

## How it works

- `/login` starts the Google OAuth flow using the credentials in `credentials.json` and the scopes used by the Gmail, Calendar, and Tasks agents.
- `/oauth2/callback` exchanges the authorization code, writes the resulting refresh token to `token.json`, and issues a signed session cookie.
- Authenticated users are redirected to `/dev-ui/`, which transparently proxies HTTP and WebSocket traffic to the ADK Web server running on `http://127.0.0.1:8000` by default.

## Running locally

1. Create `porch/.env` (copy `porch/.env.example` as a starting point) and set `GOOGLE_REDIRECT_URI` to match the OAuth client redirect you configured (defaults to `http://127.0.0.1:5000/oauth2/callback`). Keep the hostname consistent with how you access the porch server; the app automatically normalizes to that host using `PORCH_CANONICAL_NETLOC` (derived from the redirect URI unless overridden). You can also set secrets such as `PORCH_SESSION_SECRET` or override `PORCH_ADK_BASE_URL` here.
2. Start ADK Web in one terminal:
   ```powershell
   uv run --directory .\host_agent_adk -- adk web
   ```
3. Start the porch server in another terminal:
   ```powershell
   uv run python -m porch
   ```
4. Open `http://127.0.0.1:5000/`, click **Sign in with Google**, complete the OAuth flow, then continue into `/dev-ui/`.

Environment variables like `PORCH_ADK_BASE_URL`, `PORCH_LOGIN_REDIRECT`, `PORCH_PORT`, and `PORCH_SESSION_SECRET` can be defined inside `porch/.env` to customize the proxy destination, redirect path (for example `/adk/dev-ui/`), listening port, and cookie signing secret.

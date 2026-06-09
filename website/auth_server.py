"""Tiny Flask web server that demonstrates the Google OAuth web flow.

Endpoints
---------
GET /oauth2/start
    Begins the OAuth dance. Returns the Google authorization URL for the caller
    to open in a browser.
GET /oauth2/callback
    Handles Google's redirect, exchanges the authorization code for tokens, and
    shows the response payload (for demo purposes only!).

Setup
-----
1. Create a "Web application" OAuth client in Google Cloud console.
2. Add the callback URL (for example, https://your-host.example/oauth2/callback)
   to the client's Authorized redirect URIs.
3. Download the credentials JSON and place it next to this file.
4. Export the following environment variables before running the server:
       set GOOGLE_REDIRECT_URI=https://your-host.example/oauth2/callback
       set FLASK_SECRET_KEY=replace_me
5. Run the server (for local tests you can use `flask --app auth_server run`).

This code stores state and PKCE verifier values in the browser session. Replace
with a database or cache when adapting beyond the demo.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, request, session
from google_auth_oauthlib.flow import Flow
from werkzeug.middleware.proxy_fix import ProxyFix

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/calendar",
]

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-do-not-use")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)


def _get_redirect_uri() -> str:
    return os.environ.get(
        "GOOGLE_REDIRECT_URI",
        "https://teriyakitwo.tailf6cfcb.ts.net/oauth2/callback",
    )


def _build_flow(*, state: Optional[str] = None, code_verifier: Optional[str] = None) -> Flow:
    """Create a Flow object with consistent configuration."""
    flow = Flow.from_client_secrets_file(
        "credentials.json",
        scopes=SCOPES,
        redirect_uri=_get_redirect_uri(),
        state=state,
    )
    if code_verifier:
        flow.code_verifier = code_verifier
    return flow


@app.get("/")
def index():
    return {
        "message": "Ready. Call /oauth2/start to begin the Google OAuth web flow.",
        "redirect_uri": _get_redirect_uri(),
        "scopes": SCOPES,
    }


@app.get("/oauth2/start")
def oauth_start():
    flow = _build_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    # Persist state + PKCE verifier so we can validate/exchange on callback.
    session["oauth_state"] = state
    session["code_verifier"] = flow.code_verifier

    print(f"[start] Generated authorization_url={authorization_url}")
    print(f"[start] state={state}")

    return jsonify(
        {
            "authorization_url": authorization_url,
            "state": state,
            "note": "Open authorization_url in a browser to continue.",
        }
    )


@app.get("/oauth2/callback")
def oauth_callback():
    expected_state = session.get("oauth_state")
    if not expected_state:
        return jsonify({"error": "No stored OAuth state; restart the flow."}), 400

    incoming_state = request.args.get("state")
    if incoming_state != expected_state:
        return jsonify({"error": "State mismatch; possible CSRF."}), 400

    code_verifier = session.get("code_verifier")
    flow = _build_flow(state=expected_state, code_verifier=code_verifier)

    print("[callback] Exchanging authorization code for tokens...")
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials

    # Clear session entries now that they are no longer needed.
    session.pop("oauth_state", None)
    session.pop("code_verifier", None)

    print("[callback] Token exchange successful.")
    print(f"[callback] access_token={credentials.token}")
    print(f"[callback] refresh_token={credentials.refresh_token}")
    print(f"[callback] expiry={credentials.expiry}")

    # Return details for demo visibility. Do NOT do this in production.
    return jsonify(
        {
            "message": "OAuth success (demo).",
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
            "scopes": list(credentials.scopes or []),
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)

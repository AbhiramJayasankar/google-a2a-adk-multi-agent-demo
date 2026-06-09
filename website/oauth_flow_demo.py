"""Minimal console driver for the Google web OAuth flow.

Run this script after setting GOOGLE_REDIRECT_URI to the redirect endpoint
that you registered in Google Cloud (for example https://your-host/oauth2/callback)
and make sure credentials.json is in the working directory.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/calendar",
]
DEFAULT_REDIRECT_URI = "https://teriyakitwo.tailf6cfcb.ts.net/oauth2/callback"
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_redirect_uri() -> str:
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI")
    if redirect_uri:
        print(f"[config] Found GOOGLE_REDIRECT_URI={redirect_uri}")
        return redirect_uri

    # Fall back to the same default URI used by the demo web server so the flow keeps working.
    print("[config] GOOGLE_REDIRECT_URI not set; using demo default.")
    return DEFAULT_REDIRECT_URI


def run_demo() -> None:
    redirect_uri = _get_redirect_uri()

    print("[step 1] Constructing OAuth flow with credentials.json and requested scopes...")
    flow = Flow.from_client_secrets_file(
        "credentials.json",
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

    print("[step 2] Generating authorization URL for Google consent screen...")
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    print("[info] Persist this state value if you handle multiple concurrent flows:")
    print(f"        state={state}")
    print("[action] Open the following URL in a browser and complete the Google consent flow:")
    print(f"        {authorization_url}\n")

    print("[step 3] After Google redirects back to your redirect URI, paste the entire callback URL here.")
    callback_response = input("Callback URL: ").strip()
    if not callback_response:
        print("[error] No callback URL provided; aborting.")
        sys.exit(1)

    print("[step 4] Exchanging authorization code for access and refresh tokens...")
    flow.fetch_token(authorization_response=callback_response)

    credentials = flow.credentials
    print("[result] Token exchange successful. Details:")
    print(f"        access_token = {credentials.token}")
    print(f"        refresh_token = {credentials.refresh_token or '(not returned; ensure access_type="offline" is set)'}")
    print(f"        expiry = {credentials.expiry}")
    print(f"        scopes = {credentials.scopes}")

    print("[done] Serialize credentials as needed, e.g. credentials.to_json().")


if __name__ == "__main__":
    run_demo()

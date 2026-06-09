"""OAuth helpers and cookie/session utilities for the porch server."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from google_auth_oauthlib.flow import Flow
from itsdangerous import BadSignature, URLSafeSerializer

from . import settings


class TokenStore:
    """Persist Google OAuth credentials so agents can reuse them."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def write(self, credentials: Any) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.loads(credentials.to_json())
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)


class CookieSerializer:
    """Utility for issuing and validating signed cookies."""

    def __init__(self, secret: str, salt: str) -> None:
        self._serializer = URLSafeSerializer(secret_key=secret, salt=salt)

    def dumps(self, data: dict[str, Any]) -> str:
        return self._serializer.dumps(data)

    def loads(self, value: str) -> Optional[dict[str, Any]]:
        try:
            return self._serializer.loads(value)
        except BadSignature:
            return None


class SessionManager:
    """Tracks short-lived cookies for auth state and login sessions."""

    def __init__(self) -> None:
        self._session_cookie = CookieSerializer(settings.SESSION_SECRET, "porch-session")
        self._state_cookie = CookieSerializer(settings.STATE_SECRET, "porch-state")

    def issue_auth_cookie(self) -> str:
        return self._session_cookie.dumps({"issued_at": int(time.time())})

    def verify_auth_cookie(self, value: Optional[str]) -> bool:
        if not value:
            return False
        return self._session_cookie.loads(value) is not None

    def issue_state_cookie(self, state: str, code_verifier: Optional[str]) -> str:
        return self._state_cookie.dumps(
            {
                "state": state,
                "code_verifier": code_verifier,
                "issued_at": int(time.time()),
            }
        )

    def consume_state_cookie(self, value: Optional[str]) -> Optional[tuple[str, Optional[str]]]:
        if not value:
            return None
        payload = self._state_cookie.loads(value)
        if not payload:
            return None
        state = payload.get("state")
        code_verifier = payload.get("code_verifier")
        if not state:
            return None
        return state, code_verifier


def build_flow(*, state: Optional[str] = None, code_verifier: Optional[str] = None) -> Flow:
    """Create a Google OAuth Flow configured for this project."""
    flow = Flow.from_client_secrets_file(
        str(settings.CREDENTIALS_PATH),
        scopes=settings.SCOPES,
        redirect_uri=settings.REDIRECT_URI,
        state=state,
    )
    if code_verifier:
        flow.code_verifier = code_verifier
    return flow


session_manager = SessionManager()
token_store = TokenStore(settings.TOKEN_PATH)

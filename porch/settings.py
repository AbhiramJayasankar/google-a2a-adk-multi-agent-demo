"""Configuration helpers for the BFF."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
BFF_DIR = Path(__file__).resolve().parent
ENV_PATH = BFF_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

DEFAULT_PORT = int(os.environ.get("BFF_PORT", "7000"))

# Comma-separated list of A2A sub-agent base URLs the host should connect to.
FRIEND_AGENT_URLS = [
    url.strip()
    for url in os.environ.get(
        "FRIEND_AGENT_URLS",
        "http://localhost:10002,http://localhost:10003,http://localhost:10004",
    ).split(",")
    if url.strip()
]

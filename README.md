# Agent2Agent

Lightweight playground for coordinating Gmail, Calendar, and Tasks automations through specialized agents orchestrated by a host. Each agent focuses on one Google surface so you can test end-to-end intent handling or plug the pieces into your own workflows.

## What’s Inside
- **host_agent_adk**: spins up the host agent that brokers requests and exposes an ADK web UI for testing.
- **gmail**: tools for searching, reading, and sending email.
- **calendar_agent**: handlers around listing, creating, updating, and deleting calendar events.
- **tasks_agent**: helpers for managing Google Tasks lists and items.

## Run It
All commands use the project’s `uv` environment manager.

```
uv sync
uv run --directory .\host_agent_adk -- adk web
uv run python .\gmail\__main__.py
uv run python .\calendar_agent\__main__.py
uv run python .\tasks_agent\__main__.py
```

Launch each long-running service in its own terminal. Launch the sub agents first. The ADK UI will be available once the host process is up; the individual agents connect automatically.

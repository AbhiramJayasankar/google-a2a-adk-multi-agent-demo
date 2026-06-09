# TriAgent Relay

Multi-agent system on Google's A2A + ADK. A host agent routes natural-language requests to three specialized sub-agents (Gmail, Calendar, Tasks). A FastAPI BFF serves a custom React operations console that streams the host's responses over SSE.

See **[PROJECT.md](./PROJECT.md)** for the full getting-started guide, project structure, and architecture.

## Stack

- **Python 3.13+** · `uv` workspace · `google-adk` · `a2a-sdk` · FastAPI
- **React 19** · Vite · Tailwind 4 · zustand

## Run

```powershell
uv sync

# 1. Sub-agents (one terminal each, start first)
uv run python .\gmail\__main__.py
uv run python .\calendar_agent\__main__.py
uv run python .\tasks_agent\__main__.py

# 2. Host agent
uv run --directory .\host_agent_adk -- adk web

# 3. BFF
uv run python -m porch

# 4. Console (dev)
cd website\frontend && npm install && npm run dev
```

The console runs on `:5173`, BFF on `:7000`, host on `:8000`, sub-agents on `:10002–10004`. Drop a Google OAuth `credentials.json` at the repo root before first run.

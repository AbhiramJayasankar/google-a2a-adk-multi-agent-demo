# TriAgent Relay

A multi-agent system built on Google's [A2A](https://github.com/google/A2A) protocol and the [Agent Development Kit (ADK)](https://github.com/google/adk-python), with a custom React operations console. A **host agent** orchestrates three specialized sub-agents that each handle one Google surface — **Gmail**, **Calendar**, and **Tasks** — and a **BFF (porch)** sits in front of the host to serve a web UI and stream responses back over Server-Sent Events.

This document covers:
1. Getting started (install + run)
2. Project structure and what every file does
3. Architecture and runtime data flow

---

## 1. Getting Started

### Prerequisites

- **Python 3.13+** (the workspace is pinned to `>=3.13.0` in `pyproject.toml`)
- **uv** — the Astral Python package/project manager used throughout
- **Node.js 18+** and **npm** for the React frontend (developed against Node 22)
- A **Google Cloud project** with the OAuth client ID/secret downloaded as `credentials.json`
- The three Google APIs enabled for that project: **Gmail API**, **Calendar API**, **Tasks API**

> On Windows the commands below use PowerShell. On macOS/Linux replace backslashes with forward slashes — `uv` is identical.

### 1.1 Clone and sync dependencies

```powershell
git clone <your-fork-url> triagent
cd triagent
uv sync
```

`uv sync` reads the workspace `pyproject.toml` at the repo root and creates `.venv/` with every dependency the host agent, the three sub-agents, and the porch BFF need.

### 1.2 Configure Google OAuth

1. In the Google Cloud Console, create an **OAuth 2.0 Client ID** of type **Web application**.
2. Add these **Authorized redirect URIs** (match them to whatever host/port you run on):
   - `http://127.0.0.1:5000/oauth2/callback` (porch)
   - `http://localhost:8000/oauth2/callback` (sub-agents, optional)
3. Enable the **Gmail API**, **Google Calendar API**, and **Google Tasks API**.
4. Download the client config as `credentials.json` and place it at the **repo root**.

### 1.3 Configure environment

Each sub-agent and the porch reads its own `.env`. Copy the example files if present, or create them by hand:

```powershell
# repo root (for the sub-agents)
copy credentials.json credentials.json  # already at root

# sub-agents pick these up automatically
# (Gmail, Calendar, Tasks) — see their .env files
```

The porch reads `porch/.env`:

```env
BFF_PORT=7000
FRIEND_AGENT_URLS=http://localhost:10002,http://localhost:10003,http://localhost:10004
PORCH_SESSION_SECRET=<long random string>
GOOGLE_REDIRECT_URI=http://127.0.0.1:5000/oauth2/callback
```

`FRIEND_AGENT_URLS` is the **comma-separated list of A2A endpoints** the host will connect to. The defaults match the three sub-agents the project ships with (Gmail on `:10002`, Calendar on `:10003`, Tasks on `:10004`).

### 1.4 Run the system (dev mode)

You need **four terminals** (or run the first three in the background) — start them in this order:

1. **Sub-agents** — one per terminal, start them first so the host has someone to talk to:
   ```powershell
   uv run python .\gmail\__main__.py
   uv run python .\calendar_agent\__main__.py
   uv run python .\tasks_agent\__main__.py
   ```
   Each one boots an A2A server on its port and exposes a well-known agent card at `/.well-known/agent.json`.

2. **Host agent** — drives the ADK web UI on `http://127.0.0.1:8000`:
   ```powershell
   uv run --directory .\host_agent_adk -- adk web
   ```

3. **Porch BFF** — sits on `http://127.0.0.1:7000` and either (a) proxies to ADK Web after OAuth, or (b) serves the built SPA with `/api/*` going to the host:
   ```powershell
   uv run python -m porch
   ```

4. **React console** (optional in dev — use the BFF-built SPA otherwise):
   ```powershell
   cd website\frontend
   npm install
   npm run dev
   ```
   The dev server runs on `http://127.0.0.1:5173` and proxies `/api/*` to the BFF at `:7000` (configured in `vite.config.ts`).

### 1.5 Production build of the frontend

The porch will serve the built SPA from `website/dist/` if it exists. To produce that:

```powershell
cd website\frontend
npm run build
```

This runs `tsc -b && vite build` and writes to `../dist/`. Then start the porch as above and open `http://127.0.0.1:7000/`.

### 1.6 First-time OAuth

The first time you hit an endpoint that touches Google (in the ADK Web UI or via the porch if you wire it through), you'll be redirected to Google's consent screen. The resulting refresh token is written to whichever `token*.json` the relevant component manages (e.g. `token.json` for the host, `token_calendar.json` for the calendar agent). Subsequent runs reuse the stored token.

### 1.7 Useful one-liners

```powershell
# TypeScript check the frontend
cd website\frontend && npm run typecheck

# Production build the frontend
cd website\frontend && npm run build

# Preview the built frontend on :5173
cd website\frontend && npm run preview

# Watch the porch BFF logs
Get-Content .\_bff.log -Wait
```

---

## 2. Project Structure

```
agent2agent/
├── pyproject.toml              # uv workspace manifest; one set of deps for the whole monorepo
├── uv.lock                     # locked dependency graph
├── credentials.json            # Google OAuth client config (not for git)
├── token.json                  # host agent's stored Google refresh token
├── token_calendar.json         # calendar sub-agent token
├── token_tasks.json            # tasks sub-agent token
│
├── host_agent_adk/             # The host / orchestrator agent (ADK)
├── gmail/                      # Gmail sub-agent (A2A server)
├── calendar_agent/             # Calendar sub-agent (A2A server)
├── tasks_agent/                # Tasks sub-agent (A2A server)
├── porch/                      # Backend-for-frontend (FastAPI)
├── website/                    # React operations console
│
├── README.md                   # short, 1-page overview (legacy)
├── PROJECT.md                  # this file
├── TEMP.MD                     # scratch notes
└── todo.md                     # working notes
```

### 2.1 `host_agent_adk/` — the orchestrator

The host is the entry point the user talks to. It uses Google's ADK (Agent Development Kit) to drive an LLM (Gemini), exposes an A2A client that calls the three sub-agents, and ships with a built-in dev UI (`adk web`).

- `host_agent_adk/__init__.py` — package marker.
- `host_agent_adk/__main__.py` — module entry point (used by `uv run`).
- `host_agent_adk/agent.py` — declares the host's ADK agent: its system instructions, the tools it can call (mostly wrappers around `agent_executor.invoke_remote_agent`), and its model name.
- `host_agent_adk/agent_executor.py` — the A2A glue. Speaks the A2A protocol to each registered sub-agent, normalizes their streamed chunks into the host's own chunk shape, and exposes `stream(query, session_id)` which the porch consumes.

### 2.2 `gmail/`, `calendar_agent/`, `tasks_agent/`

Each sub-agent has the **same shape**: an ADK agent whose tools are thin wrappers over a specific Google API. All three expose A2A server endpoints (default ports 10002, 10003, 10004) and respond to `/.well-known/agent.json` with their agent card.

#### `gmail/`
- `gmail/__main__.py` — boots the A2A server on `:10002`.
- `gmail/agent.py` — ADK agent declaration (instructions, model, tool list).
- `gmail/agent_executor.py` — A2A request handler. Reads A2A tasks, calls the Gmail tools, streams results back as A2A artifacts.
- `gmail/search_tool.py` — `search_emails(query, max_results, ...)` — wraps `users.messages.list` + `users.messages.get`.
- `gmail/email_details_tool.py` — fetch a single message by id, parse headers + body, return a structured summary.
- `gmail/send_email_tool.py` — send a new email (to/subject/body/html).
- `gmail/attachment_tool.py` — download an attachment by message id + attachment id.

#### `calendar_agent/`
- `calendar_agent/__main__.py` — A2A server on `:10003`.
- `calendar_agent/agent.py` / `agent_executor.py` — same ADK + A2A scaffold.
- `calendar_agent/list_events_tool.py` — list events in a time window.
- `calendar_agent/create_event_tool.py` — create a new calendar event.
- `calendar_agent/update_event_tool.py` — patch an existing event.
- `calendar_agent/delete_event_tool.py` — delete by event id.
- `calendar_agent/search_events_tool.py` — free-text search across events.

#### `tasks_agent/`
- `tasks_agent/__main__.py` — A2A server on `:10004`.
- `tasks_agent/agent.py` / `agent_executor.py` — same scaffold.
- `tasks_agent/list_tasklists_tool.py` — list all task lists for the user.
- `tasks_agent/list_tasks_tool.py` — list tasks in a list, optionally filtered by completion/due date.
- `tasks_agent/create_task_tool.py` — create a task in a list.
- `tasks_agent/update_task_tool.py` — patch title/notes/due/status.
- `tasks_agent/complete_task_tool.py` — mark a task as completed.
- `tasks_agent/delete_task_tool.py` — delete a task.

### 2.3 `porch/` — the Backend-for-Frontend

A thin FastAPI app. It is **not** in the data path of the agents themselves — it only fronts the host so the React UI has somewhere to POST.

- `porch/__init__.py` — package marker, plus a default FastAPI `app` if you want a single import.
- `porch/__main__.py` — module entry point used by `uv run python -m porch`.
- `porch/main.py` — defines `app`, mounts the API router, mounts the built SPA, and runs uvicorn.
- `porch/api.py` — the BFF routes:
  - `GET /api/agents` — returns the list of sub-agent cards.
  - `POST /api/chat/stream` — SSE stream from `HostAgent.stream(query, session_id)`.
  - `GET /api/session/{id}` — debug view over the host's ADK session (event count, state keys).
  - `GET /api/health` — pings each sub-agent's `/.well-known/agent.json` in parallel.
  - `mount_spa()` — serves `website/dist/` at `/` and `/<anything>` when no API/static route matches.
- `porch/proxy.py` — older, OAuth-aware reverse proxy for the **stock `adk web` dev UI**. Used when you want the porch to act as a login wall in front of the ADK web UI instead of (or in addition to) the custom console.
- `porch/auth.py` — Google OAuth flow, session cookie signing, token persistence.
- `porch/settings.py` — reads `porch/.env`, exposes `BFF_PORT`, `FRIEND_AGENT_URLS`, `ADK_BASE_URL`, session cookie names, etc.

### 2.4 `website/` — the React operations console

A Vite + React 19 + Tailwind 4 SPA styled as a diagnostic instrument panel. Streams from the BFF and visualizes the host's delegation graph in real time.

```
website/
├── auth_server.py              # legacy: minimal OAuth demo (not used in the main flow)
├── oauth_flow_demo.py          # legacy: standalone OAuth walk-through
├── todo.md                     # working notes
├── dist/                       # vite build output (gitignored; served by porch)
└── frontend/
    ├── index.html              # html shell, font preconnect, mounts #root
    ├── package.json            # scripts: dev / build / preview / typecheck
    ├── vite.config.ts          # dev server + /api proxy → porch :7000
    ├── tsconfig*.json
    ├── src/
    │   ├── main.tsx            # React 19 createRoot mount
    │   ├── App.tsx             # shell: StatusBar + Sidebar | ChatLog+Composer | Inspector
    │   ├── index.css           # design tokens + base styles + signature animations
    │   ├── store.ts            # zustand store: messages, events, agent states, session
    │   ├── api.ts              # fetchAgents / fetchHealth / fetchSessionInfo / streamChat
    │   ├── types.ts            # shared TS types (AgentMessage, LogEvent, SubAgent, …)
    │   └── components/
    │       ├── StatusBar.tsx   # top hairline: brand, state, session, counters, model, clock
    │       ├── Sidebar.tsx     # left rail: host + sub-agent topology, recent delegations
    │       ├── ChatLog.tsx     # logbook-style conversation view + per-turn signal trace
    │       ├── Composer.tsx    # terminal-prompt input row
    │       └── Inspector.tsx   # right rail: raw SSE event list + JSON detail pane
    └── node_modules/
```

### 2.5 Other files

- `__patch_agent_state.py`, `__patch_sidebar_agentstate.py` — one-off scripts that were used to hot-patch the store and Sidebar during development. Safe to delete; not part of the runtime.
- `del/` — old/experimental code kept for reference.
- `credentials.json` — Google OAuth client secrets. Already in `.gitignore`.
- `token.json`, `token_calendar.json`, `token_tasks.json` — per-component refresh tokens, one per sub-agent + the host.

---

## 3. Architecture & Runtime

### 3.1 The big picture

```
                 ┌──────────────────────────────┐
                 │       React Console          │
                 │   (website/frontend, :5173)  │
                 └──────────────┬───────────────┘
                                │  /api/chat/stream (SSE)
                                │  /api/agents, /api/health
                                ▼
                 ┌──────────────────────────────┐
                 │     Porch BFF (FastAPI)      │
                 │        :7000                 │
                 │   api.py · auth.py · proxy   │
                 └──────────────┬───────────────┘
                                │  HostAgent.stream(query, session_id)
                                │  HostAgent.cards (agent cards)
                                ▼
                 ┌──────────────────────────────┐
                 │       Host Agent (ADK)       │
                 │ host_agent_adk/agent.py      │
                 │ host_agent_adk/agent_exec.py │
                 │  ─ adk web UI on :8000 ─     │
                 └──────┬───────┬───────┬───────┘
                        │       │       │       A2A protocol
                        ▼       ▼       ▼
                 ┌──────┐ ┌──────┐ ┌──────┐
                 │Gmail │ │Cal   │ │Tasks │   (each: ADK agent + Google API tools)
                 │:10002│ │:10003│ │:10004│
                 └──────┘ └──────┘ └──────┘
                        │       │       │
                        ▼       ▼       ▼
                 Gmail API  Cal API   Tasks API
```

The React console never talks to the host, the sub-agents, or Google directly. It only ever talks to **the BFF**. The BFF is the single integration point.

### 3.2 Protocol layers

- **A2A** between the host and each sub-agent. An A2A *task* has a unique id, a history of messages, and a list of *artifacts* (the produced output). The host's `agent_executor.invoke_remote_agent` opens an A2A client, sends a `tasks/sendSubscribe` request, and consumes the streamed events.
- **SSE** between the BFF and the React console. The BFF transcodes the host's chunk iterator into `data: <json>\n\n` lines, one chunk per line, so the browser can use plain `fetch` + `ReadableStream` (the browser's native `EventSource` can't POST a body).
- **REST** for everything else: agent discovery (`GET /api/agents`), session debug (`GET /api/session/{id}`), health (`GET /api/health`).

### 3.3 The host agent, in detail

`host_agent_adk/agent.py` declares an ADK `Agent` with:
- a **system prompt** that tells Gemini its job is to choose between the sub-agents and to call the right `send_message` tool with a clear natural-language task;
- a list of **tools** (effectively one per sub-agent) that wrap `agent_executor.invoke_remote_agent(agent_url, task)`;
- a **model** name (e.g. a Gemini flash variant).

`host_agent_adk/agent_executor.py` does the heavy lifting on the A2A side. When the host decides to delegate, the executor:
1. Opens an `httpx.AsyncClient` and a `ClientFactory` to the target sub-agent.
2. Sends a `message/send` (or stream) request.
3. Walks the resulting event stream, normalizing each event into the host's own `StreamChunk` shape (turn metadata, updates, delegation, tool_call, tool_result, chunk, complete, error).
4. Re-emits the normalized chunks upstream so the BFF can stream them to the browser.

The normalized shape is what the React store keys off of — every event in the **Inspector** is one of these chunks, and the `state` field on each agent message is derived from the order in which these chunks arrive (`working → delegating → streaming → done | error`).

### 3.4 The BFF, in detail

`porch/api.py` exposes four functional routes plus the SPA mount:

- **`GET /api/agents`** — asks the host for its `cards` (the A2A agent cards of every sub-agent it knows about) and returns them as a JSON array the Sidebar can render. The BFF initializes the host lazily on the first request so the porch can boot even when ADK isn't ready.
- **`POST /api/chat/stream`** — the hot path. Takes `{ query, session_id? }`, calls `host.stream(query, session_id)`, and wraps the resulting async iterator in a `StreamingResponse(media_type="text/event-stream")`. Each yielded dict is JSON-encoded into a `data: …\n\n` SSE frame. Headers disable proxy buffering (`X-Accel-Buffering: no`) and any caching.
- **`GET /api/session/{id}`** — debug-only. Returns the host's `runner.session_service.get_session(...)` view: existence, app name, user id, last update time, event count, state keys.
- **`GET /api/health`** — for the Sidebar's live indicators. In parallel, GETs each sub-agent's `/.well-known/agent.json`, records ok/error/latency, and returns the snapshot. The frontend polls this every 5s.
- **`mount_spa(app)`** — if `website/dist/` exists, mounts `/assets/*` as static files and registers a catch-all route for `/<full_path>` that serves the file if it exists, otherwise falls back to `index.html`. Crucially, the catch-all uses `path_regex` to exclude `/api/*` and `/assets/*` so those always win over the SPA.

`porch/main.py` is the uvicorn entry point. `porch/settings.py` loads `porch/.env` and exposes the port and the comma-separated `FRIEND_AGENT_URLS` that the host should talk to.

### 3.5 The React console, in detail

The frontend is a thin client. It owns no business logic — it just renders whatever the BFF streams.

**State** lives in a single zustand store (`src/store.ts`):
- `messages: AgentMessage[]` — the conversation. Each user message and each agent message is a row.
- `events: LogEvent[]` — append-only SSE log. Mirrors the Inspector's view.
- `agents: SubAgent[]` — the cards from `/api/agents`.
- `agentStates: Record<string, "ok" | "working" | "idle" | "err">` — per-sub-agent runtime state, updated by the store whenever a delegation/tool_call/tool_result/complete/error event fires. This is what powers the live "busy / idle / down" dots in the Sidebar.
- `health: SubAgentHealth[]` — last `/api/health` snapshot, polled every 5s.
- `sessionId`, `sending`, `error`, `activeModel`, `totalChunks`, `totalToolCalls`, `streamingStartedAt` — session/streaming UI state.

The most subtle piece is `mergeChunk(current, delta)` in the store. The BFF occasionally re-emits a near-full copy of the reply on the final non-partial text chunk (the host's delta logic can miss spaces/punctuation in the closing chunk). Naive concatenation would render the reply twice. The merger handles three cases: suffix duplication, full re-send, and cross-boundary word stitching.

**API** (`src/api.ts`) is just four functions: `fetchAgents`, `fetchHealth`, `fetchSessionInfo`, and `streamChat(query, sessionId, onChunk)`. `streamChat` is the only non-trivial one: it POSTs to `/api/chat/stream`, then loops on `reader.read()`, accumulating text into a buffer and parsing one `data: <json>\n\n` frame per `\n\n` boundary.

**Layout** (`src/App.tsx`) is a 3-column grid: the StatusBar is a 36-px hairline across the top of the whole window; below it, a flex row holds the Sidebar, the chat column (ChatLog + Composer), and the Inspector. The Inspector is a fixed-width drawer that mounts/unmounts based on the toggle in the StatusBar.

**The conversation view** (`ChatLog.tsx`) is laid out as a logbook: a narrow monospace gutter (turn number, role tag, timestamp) on the left, and the message body on the right. Each agent message also has a per-turn **signal trace** above its content that renders every delegation, tool call, and tool result as a row in time order, with a tiny animated hairline under in-flight rows.

**The Inspector** (`Inspector.tsx`) is a raw event tap. A filter strip on top, a hairline-divided event list on the left, and a JSON detail pane on the right. Clicking a row pins the event and renders its raw payload; the **jump to message** button scrolls the originating bubble into view.

**The Composer** (`Composer.tsx`) is a `>`-prefixed terminal input. Enter sends, Shift+Enter inserts a newline, the input auto-grows up to ~5 lines, and the send button switches to a signal-orange "transmit" while a stream is in flight.

### 3.6 How a turn flows end-to-end

Here's what happens from the moment you press Enter in the React console to the moment the host's reply finishes streaming.

1. **Composer** trims the input, clears the textarea, and calls `useChat.send(query)`.
2. The **store** pushes a `user` message and a placeholder `agent` message into `messages`, marks `sending: true`, and calls `streamChat` (POST `/api/chat/stream`).
3. The **BFF** receives the request, lazily initializes the host (if it isn't already), grabs the host's async iterator, and starts yielding `data: <chunk>\n\n` SSE frames.
4. Each frame lands in `streamChat`'s reader loop, which JSON-parses it and calls the store's `onChunk` callback.
5. The **store** updates the placeholder agent message in place, mutates `events`, and bumps `totalChunks` / `totalToolCalls` / `agentStates` as appropriate. Each per-chunk mutation triggers a re-render, so the UI updates in real time.
6. The **host** is itself receiving the LLM's stream from Gemini. When Gemini decides to call a sub-agent, the host's `agent_executor.invoke_remote_agent` opens an A2A client to that sub-agent and consumes its stream. Each event from the sub-agent is normalized into a `StreamChunk` and yielded up to the BFF, so by the time it reaches the browser, the chunks are already in a single uniform shape regardless of which sub-agent produced them.
7. The **store** recognizes the chunks and flips the relevant sub-agent's `agentStates[name]` between `working` / `idle` / `err`, which lights up the matching Sidebar dot.
8. The **store** also derives the agent message's `state` from the chunk sequence: `working` (stream open, no chunks yet) → `delegating` (a delegation event arrived) → `streaming` (content chunks are flowing) → `done` (the `is_task_complete: true` chunk arrived) | `error` (an `error` event arrived).
9. When the SSE stream closes, the store sets `sending: false`, `streamingStartedAt: null`, and the StatusBar's signal trace stops sweeping.

### 3.7 Session and history

The BFF does **not** persist chat history. The host does — via the ADK session service, keyed by `(app_name, user_id, session_id)`. The frontend generates a fresh UUID per session (see `newSession()` in `store.ts`) and reuses it for the lifetime of the session. The `GET /api/session/{id}` endpoint exists purely so the console can show "ADK has N events for this session" without having to persist anything itself.

When you click **New session** in the Sidebar, the store rotates the session id, clears `messages`, and lets the BFF lazily re-issue a session on the next message.

### 3.8 Where to look first

- **Wiring question** (where does X go?) → `porch/api.py`
- **Host behavior** (what does the LLM actually do?) → `host_agent_adk/agent.py` for the prompt, `host_agent_adk/agent_executor.py` for the A2A plumbing
- **Adding a new sub-agent** → copy the shape of `gmail/` (an `__main__.py` that boots the A2A server, an `agent.py` that declares the ADK agent and tool list, an `agent_executor.py` that handles A2A requests, and one tool file per Google-API action)
- **UI question** (where does this render?) → `src/components/*`; layout shell is `src/App.tsx`
- **Stream/state weirdness** → `src/store.ts` (especially `mergeChunk` and the per-chunk `patch.agentStates` accumulator)
- **Styling** → `src/index.css`; the design tokens (`--color-paper`, `--color-ink`, `--color-signal`, …) are the only place colors and type come from

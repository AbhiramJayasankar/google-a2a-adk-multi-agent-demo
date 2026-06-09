"""Backend-for-frontend: thin FastAPI layer over HostAgent.

Exposes:
  GET  /api/agents        -> list of connected sub-agent cards
  POST /api/chat/stream   -> Server-Sent Events stream from HostAgent.stream()

No auth, no OAuth, no canonical-host middleware. Pure local-dev BFF.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, AsyncIterable, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

from . import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


def _format_sse(payload: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


async def _get_or_build_host_agent(request: Request) -> Any:
    host = getattr(request.app.state, "host_agent", None)
    if host is not None:
        return host

    # Late import so the module only loads when we actually need the agent
    # (avoids pulling in ADK/Genai on a simple --help).
    from host_agent_adk.host.agent import HostAgent  # type: ignore

    logger.info("initializing HostAgent against %s", settings.FRIEND_AGENT_URLS)
    host = await HostAgent.create(remote_agent_addresses=settings.FRIEND_AGENT_URLS)
    request.app.state.host_agent = host
    return host


@router.get("/agents")
async def list_agents(request: Request) -> list[dict[str, Any]]:
    try:
        host = await _get_or_build_host_agent(request)
    except Exception as exc:  # noqa: BLE001
        logger.exception("agents init failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"host init failed: {exc}")
    out: list[dict[str, Any]] = []
    for name, card in host.cards.items():
        entry: dict[str, Any] = {
            "name": card.name,
            "description": card.description or "",
            "url": str(getattr(card, "url", "") or ""),
            "version": str(getattr(card, "version", "") or ""),
            "provider": str(getattr(getattr(card, "provider", None), "organization", "") or ""),
            "skills": [
                {"id": s.id, "name": s.name, "description": s.description or ""}
                for s in (getattr(card, "skills", []) or [])
            ],
            "capabilities": {
                "streaming": bool(getattr(getattr(card, "capabilities", None), "streaming", False)),
                "push_notifications": bool(getattr(getattr(card, "capabilities", None), "push_notifications", False)),
                "state_transition_history": bool(getattr(getattr(card, "capabilities", None), "state_transition_history", False)),
            },
            "default_input_modes": list(getattr(card, "default_input_modes", []) or []),
            "default_output_modes": list(getattr(card, "default_output_modes", []) or []),
        }
        out.append(entry)
    return out


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequest):
    from fastapi.responses import StreamingResponse

    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    try:
        host = await _get_or_build_host_agent(request)
    except Exception as exc:  # noqa: BLE001
        logger.exception("host init failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"host init failed: {exc}")

    session_id = body.session_id or str(uuid.uuid4())

    async def event_gen() -> AsyncIterable[bytes]:
        yield _format_sse({"is_task_complete": False, "updates": "Starting..."})
        try:
            async for chunk in host.stream(query, session_id):
                yield _format_sse(chunk)
        except Exception as exc:  # noqa: BLE001
            logger.exception("chat stream error: %s", exc)
            yield _format_sse(
                {"is_task_complete": True, "content": f"[error] {exc}"}
            )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/session/{session_id}")
async def session_info(request: Request, session_id: str) -> dict[str, Any]:
    """Return host session metadata for the given session id.

    The BFF does not retain chat history; this is a thin debug view
    over the ADK session service so the frontend can display session
    age, last-update time, and stored state keys.
    """
    try:
        host = await _get_or_build_host_agent(request)
    except Exception as exc:  # noqa: BLE001
        logger.exception("host init failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"host init failed: {exc}")
    try:
        session = await host._runner.session_service.get_session(  # type: ignore[attr-defined]
            app_name=host._agent.name,  # type: ignore[attr-defined]
            user_id=host._user_id,  # type: ignore[attr-defined]
            session_id=session_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))
    if session is None:
        return {"exists": False, "session_id": session_id}
    return {
        "exists": True,
        "session_id": session.id,
        "app_name": session.app_name,
        "user_id": session.user_id,
        "last_update_time": getattr(session, "last_update_time", None),
        "events_count": len(getattr(session, "events", []) or []),
        "state_keys": list((getattr(session, "state", {}) or {}).keys()),
    }


@router.get("/health")
async def health() -> dict[str, Any]:
    """BFF + sub-agent health snapshot.

    Pings each sub-agent's well-known agent card endpoint in
    parallel to give the frontend a live 'up/down' indicator per
    agent without waiting on a chat request.
    """
    import asyncio
    import time
    import httpx

    from . import settings as _settings

    urls = [u.rstrip("/") + "/.well-known/agent.json" for u in _settings.FRIEND_AGENT_URLS]

    async def _probe(url: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(url)
            return {
                "url": url.replace("/.well-known/agent.json", ""),
                "ok": r.status_code == 200,
                "status": r.status_code,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "url": url.replace("/.well-known/agent.json", ""),
                "ok": False,
                "error": str(exc),
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }

    results = await asyncio.gather(*(_probe(u) for u in urls))
    return {"bff": True, "sub_agents": results}


def mount_spa(app: Any) -> None:
    """Serve the built Vite SPA from website/dist if it exists.

    Uses Starlette's path_regex to exclude /api/* at the routing layer so
    the api router always wins.
    """
    dist_dir = Path(__file__).resolve().parents[1] / "website" / "dist"
    if not dist_dir.exists():
        logger.info("website/dist not found; SPA not served by porch")
        return

    from fastapi.staticfiles import StaticFiles

    app.mount(
        "/assets",
        StaticFiles(directory=dist_dir / "assets"),
        name="spa-assets",
    )

    @app.get("/", include_in_schema=False)
    async def spa_root():
        return FileResponse(dist_dir / "index.html")

    async def _spa_fallback(full_path: str):
        candidate = dist_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist_dir / "index.html")

    # path_regex excludes api/, assets/, docs, openapi, redoc so those
    # paths fall through to the api router or static mount.
    app.add_api_route(
        r"/{full_path:path}",
        _spa_fallback,
        methods=["GET"],
        include_in_schema=False,
    )

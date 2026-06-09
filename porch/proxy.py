"""HTTP and WebSocket proxy helpers used to surface ADK Web."""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import Iterable
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
import websockets

from . import auth, settings

HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

router = APIRouter()


def _build_response(upstream: httpx.Response) -> Response:
    headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in HOP_HEADERS
    }
    media_type = upstream.headers.get("content-type")
    response = Response(content=upstream.content, status_code=upstream.status_code)
    if media_type:
        response.headers["content-type"] = media_type
    for key, value in headers.items():
        if key.lower() == "content-type":
            continue
        response.headers[key] = value
    return response


def _filtered_cookie_header(raw_cookie: str | None) -> str | None:
    if not raw_cookie:
        return None
    fragments: list[str] = []
    for part in raw_cookie.split(";"):
        name, _, value = part.strip().partition("=")
        if not name:
            continue
        if name in {settings.SESSION_COOKIE_NAME, settings.STATE_COOKIE_NAME}:
            continue
        fragments.append(f"{name}={value}")
    return "; ".join(fragments) if fragments else None


async def ensure_authenticated(request: Request) -> bool:
    cookie_value = request.cookies.get(settings.SESSION_COOKIE_NAME)
    return auth.session_manager.verify_auth_cookie(cookie_value)


@router.get("/")
async def home(request: Request) -> Response:
    is_authed = await ensure_authenticated(request)
    if is_authed:
                        return HTMLResponse(
                                f"""
                                <html>
                                    <head><title>ADK Porch</title></head>
                                    <body>
                                        <h1>Welcome</h1>
                                        <p>You are signed in and can access the <a href="{settings.LOGIN_REDIRECT_PATH}">ADK Web UI</a>.</p>
                                        <form method="post" action="/logout"><button type="submit">Sign out</button></form>
                                    </body>
                                </html>
                                """
                        )
    return HTMLResponse(
        """
        <html>
          <head><title>ADK Porch</title></head>
          <body>
            <h1>Google Agent Playground</h1>
            <p>Sign in with Google to continue.</p>
            <a href="/login"><button>Sign in with Google</button></a>
          </body>
        </html>
        """
    )


@router.get("/login")
async def login() -> Response:
    flow = auth.build_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    code_verifier = getattr(flow, "code_verifier", None)
    state_cookie = auth.session_manager.issue_state_cookie(state, code_verifier)
    response = RedirectResponse(authorization_url, status_code=HTTPStatus.FOUND)
    response.set_cookie(
        key=settings.STATE_COOKIE_NAME,
        value=state_cookie,
        path="/",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )
    return response


@router.get("/oauth2/callback")
async def oauth_callback(request: Request) -> Response:
    state_cookie = request.cookies.get(settings.STATE_COOKIE_NAME)
    state_data = auth.session_manager.consume_state_cookie(state_cookie)
    if not state_data:
        return JSONResponse({"detail": "Missing or invalid OAuth state."}, status_code=HTTPStatus.BAD_REQUEST)

    state, code_verifier = state_data
    incoming_state = request.query_params.get("state")
    if incoming_state != state:
        return JSONResponse({"detail": "State mismatch; restart login."}, status_code=HTTPStatus.BAD_REQUEST)

    flow = auth.build_flow(state=state, code_verifier=code_verifier)
    flow.fetch_token(authorization_response=str(request.url))
    auth.token_store.write(flow.credentials)

    response = RedirectResponse(settings.LOGIN_REDIRECT_PATH, status_code=HTTPStatus.SEE_OTHER)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=auth.session_manager.issue_auth_cookie(),
        path="/",
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )
    response.delete_cookie(settings.STATE_COOKIE_NAME, path="/")
    return response


@router.post("/logout")
async def logout() -> Response:
    response = RedirectResponse("/", status_code=HTTPStatus.SEE_OTHER)
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    return response


async def _prepare_headers(request: Request) -> dict[str, str]:
    host_header, _ = settings.adk_origin()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_HEADERS
    }
    headers["host"] = host_header
    filtered_cookie = _filtered_cookie_header(headers.get("cookie"))
    if filtered_cookie is not None:
        headers["cookie"] = filtered_cookie
    else:
        headers.pop("cookie", None)
    return headers


SPECIAL_PATHS = {"login", "oauth2/callback", "logout"}

# When the SPA is mounted, /api/* and /assets/* are handled by the
# backend-for-frontend router and the static mount respectively. Skip them
# here so the upstream ADK proxy does not try to fetch them.
PROXY_SKIP_PREFIXES = ("api/", "assets/")


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def proxy_http(request: Request, path: str) -> Response:
    if path in SPECIAL_PATHS:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
    if any(path.startswith(prefix) for prefix in PROXY_SKIP_PREFIXES):
        # Route past the proxy; FastAPI will try the next matching route
        # (api router or static mount). If nothing matches, the SPA
        # fallback in api.mount_spa will serve index.html.
        return Response(status_code=HTTPStatus.NOT_FOUND)
    if not await ensure_authenticated(request):
        if request.method.upper() == "GET":
            return RedirectResponse("/", status_code=HTTPStatus.SEE_OTHER)
        return JSONResponse({"detail": "Unauthorized"}, status_code=HTTPStatus.UNAUTHORIZED)

    target_path = "/" + path if path else "/"
    client: httpx.AsyncClient = request.app.state.http_client
    headers = await _prepare_headers(request)
    try:
        upstream = await client.request(
            request.method,
            target_path,
            params=request.query_params,
            headers=headers,
            content=await request.body(),
            follow_redirects=False,
        )
    except httpx.RequestError as exc:
        return JSONResponse(
            {"detail": "ADK Web upstream unavailable.", "error": str(exc)},
            status_code=HTTPStatus.BAD_GATEWAY,
        )
    return _build_response(upstream)


def _build_ws_url(path: str, query: str) -> str:
    parsed = urlparse(settings.ADK_BASE_URL)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    base = f"{scheme}://{parsed.netloc}"
    suffix = f"/{path}" if path else "/"
    if query:
        return f"{base}{suffix}?{query}"
    return f"{base}{suffix}"


@router.websocket("/{path:path}")
async def proxy_websocket(websocket: WebSocket, path: str) -> None:
    if path in SPECIAL_PATHS:
        await websocket.close(code=4404)
        return
    cookie_value = websocket.cookies.get(settings.SESSION_COOKIE_NAME)
    if not auth.session_manager.verify_auth_cookie(cookie_value):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    ws_target = _build_ws_url(path, websocket.scope.get("query_string", b"").decode())
    host_header, _ = settings.adk_origin()
    extra_headers: Iterable[tuple[str, str]] = [
        ("host", host_header),
    ]
    async with websockets.connect(ws_target, extra_headers=extra_headers) as upstream:
        async def client_to_server() -> None:
            try:
                while True:
                    message = await websocket.receive()
                    mtype = message.get("type")
                    if mtype == "websocket.disconnect":
                        await upstream.close()
                        break
                    if mtype != "websocket.receive":
                        continue
                    if "text" in message:
                        await upstream.send(message["text"])
                    elif "bytes" in message:
                        await upstream.send(message["bytes"])
            except Exception:
                await upstream.close()

        async def server_to_client() -> None:
            try:
                while True:
                    data = await upstream.recv()
                    if isinstance(data, str):
                        await websocket.send_text(data)
                    else:
                        await websocket.send_bytes(data)
            except Exception:
                await websocket.close()

    await asyncio.gather(client_to_server(), server_to_client(), return_exceptions=True)
    await websocket.close()
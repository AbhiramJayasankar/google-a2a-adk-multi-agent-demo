import asyncio
import json
import sys
import uuid
from datetime import datetime
from typing import Any, AsyncIterable, List

import httpx
import nest_asyncio
from a2a.client import A2ACardResolver
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
    SendMessageResponse,
    SendMessageSuccessResponse,
    Task,
)
from dotenv import load_dotenv
from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.tool_context import ToolContext
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

from .remote_agent_connection import RemoteAgentConnections

load_dotenv()
nest_asyncio.apply()


class HostAgent:
    """The Host agent."""

    def __init__(
        self,
    ):
        self.remote_agent_connections: dict[str, RemoteAgentConnections] = {}
        self.cards: dict[str, AgentCard] = {}
        self.agents: str = ""
        self._agent = self.create_agent()
        self._user_id = "host_agent"
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    async def _async_init_components(self, remote_agent_addresses: List[str]):
        async with httpx.AsyncClient(timeout=30) as client:
            for address in remote_agent_addresses:
                card_resolver = A2ACardResolver(client, address)
                try:
                    card = await card_resolver.get_agent_card()
                    remote_connection = RemoteAgentConnections(
                        agent_card=card, agent_url=address
                    )
                    self.remote_agent_connections[card.name] = remote_connection
                    self.cards[card.name] = card
                except httpx.ConnectError as e:
                    print(f"ERROR: Failed to get agent card from {address}: {e}")
                except Exception as e:
                    print(f"ERROR: Failed to initialize connection for {address}: {e}")

        agent_info = [
            json.dumps({"name": card.name, "description": card.description})
            for card in self.cards.values()
        ]
        print("agent_info:", agent_info)
        self.agents = "\n".join(agent_info) if agent_info else "No friends found"

    @classmethod
    async def create(
        cls,
        remote_agent_addresses: List[str],
    ):
        instance = cls()
        await instance._async_init_components(remote_agent_addresses)
        return instance

    def create_agent(self) -> Agent:
        return Agent(
            model="gemini-3.1-flash-lite",
            name="Host_Agent",
            instruction=self.root_instruction,
            description="This Host agent orchestrates multiple sub agents.",
            tools=[
                self.send_message,
            ],
        )

    def root_instruction(self, context: ReadonlyContext) -> str:
        return f"""
        **Role:** You are the Host Agent, an expert orchestration agent, which uses the available agents.

        **Today's Date (YYYY-MM-DD):** {datetime.now().strftime("%Y-%m-%d")}
        *give timezone to the calender agent for relevant tasks (Indian Standard Time)*

        <Available Agents>
        {self.agents}
        </Available Agents>
        """

    async def stream(
        self, query: str, session_id: str
    ) -> AsyncIterable[dict[str, Any]]:
        """
        Streams the agent's response to a given query.
        """
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name,
            user_id=self._user_id,
            session_id=session_id,
        )
        content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name,
                user_id=self._user_id,
                state={},
                session_id=session_id,
            )
        # Use the default (NONE) streaming mode.
        #
        # SSE streaming mode was a regression: in that mode ADK does
        # not expose the model's text reply after a tool call -- the
        # parts on the final event have no .text field, so the reply
        # is silently dropped. With NONE mode, run_async delivers a
        # single aggregated final event whose parts contain the full
        # text reply, which the frontend can then render.
        run_config = RunConfig()

        # BFF-side accumulator. We track the authoritative full text and
        # emit only the *new suffix* per chunk so the frontend can
        # append. To handle ADK's occasionally non-monotonic chunks, we
        # compute the longest common prefix between the previous full
        # text and the new text, then emit what comes after it. This
        # never loses content and never duplicates.
        prev_full = ""
        yielded_final = False
        model_name = getattr(self._agent, "model", None) or "unknown"
        run_started_at = int(datetime.now().timestamp() * 1000)
        event_seq = 0
        tool_calls: list[dict[str, Any]] = []
        turn_text_len = 0
        current_tool_started_at: int | None = None
        # Per-turn preamble so the frontend can render host-level metadata
        # even before the first chunk arrives.
        yield {
            "is_task_complete": False,
            "turn_meta": {
                "model": model_name,
                "session_id": session_id,
                "agent": self._agent.name,
                "started_at": run_started_at,
            },
        }
        event_seq += 1

        def _next_event_id() -> int:
            nonlocal event_seq
            eid = event_seq
            event_seq += 1
            return eid

        def _emit_delta(new_full: str) -> None:
            nonlocal prev_full
            # Longest common prefix length.
            i = 0
            n = min(len(prev_full), len(new_full))
            while i < n and prev_full[i] == new_full[i]:
                i += 1
            d = new_full[i:]
            prev_full = new_full
            if d:
                # Use a local yield via a sent-in queue? No: we can't
                # yield from a nested function in an async generator
                # reliably. Instead, return the delta and let the caller
                # yield it.
                delta_buffer.append(d)

        async for event in self._runner.run_async(
            user_id=self._user_id,
            session_id=session.id,
            new_message=content,
            run_config=run_config,
        ):
            now_ms = int(datetime.now().timestamp() * 1000)
            author = getattr(event, "author", None) or self._agent.name
            # Tool call phase: emit delegation events and reset the
            # accumulator so the post-tool text phase starts fresh.
            if event.content and event.content.parts and any(
                p.function_call for p in event.content.parts
            ):
                prev_full = ""
                for part in event.content.parts:
                    if not part.function_call:
                        continue
                    fc = part.function_call
                    args = dict(fc.args or {})
                    fc_id = getattr(fc, "id", None) or _next_event_id()
                    current_tool_started_at = now_ms
                    if fc.name == "send_message":
                        agent = str(args.get("agent_name", "sub-agent"))
                        detail = str(args.get("task", "delegating..."))[:280]
                        tool_calls.append(
                            {"id": fc_id, "name": fc.name, "agent": agent, "task": detail, "args": args, "started_at": now_ms}
                        )
                        yield {
                            "is_task_complete": False,
                            "delegation": {
                                "agent": agent,
                                "detail": detail,
                                "at": now_ms,
                            },
                            "tool_call": {
                                "id": fc_id,
                                "name": fc.name,
                                "agent": agent,
                                "args": {k: (v if isinstance(v, (str, int, float, bool)) else str(v)) for k, v in args.items()},
                                "at": now_ms,
                            },
                            "event_id": _next_event_id(),
                            "author": author,
                        }
                    else:
                        tool_calls.append(
                            {"id": fc_id, "name": fc.name, "agent": "", "task": "", "args": args, "started_at": now_ms}
                        )
                        yield {
                            "is_task_complete": False,
                            "updates": f"Calling {fc.name}...",
                            "tool_call": {
                                "id": fc_id,
                                "name": fc.name,
                                "args": {k: (v if isinstance(v, (str, int, float, bool)) else str(v)) for k, v in args.items()},
                                "at": now_ms,
                            },
                            "event_id": _next_event_id(),
                            "author": author,
                        }
                continue

            # Text-bearing event: compute the delta against our
            # authoritative accumulator and emit only the new suffix.
            #
            # ADK in SSE streaming mode hands us several shapes for the
            # model's reply text:
            #   1. Plain text parts (p.text set) - the normal partial
            #      streaming case.
            #   2. The post-tool final reply, where ADK concatenates
            #      the LLM text into event.content.parts[*].text. The
            #      original `any(p.text for p in parts)` check works
            #      here.
            #   3. Edge cases where p.text is None on every part but
            #      the raw text is recoverable via the part's JSON
            #      dump (e.g. when ADK surfaces a thought_signature
            #      blob as a Part with no .text). Fall back to that
            #      so we never silently drop the model's reply.
            if event.content and event.content.parts and any(
                p.function_response for p in event.content.parts
            ):
                # Tool result event. Summarize it and surface it to the
                # frontend so the inspector shows what came back.
                for part in event.content.parts:
                    fr = getattr(part, "function_response", None)
                    if not fr:
                        continue
                    fr_name = getattr(fr, "name", None) or "tool"
                    fr_response = getattr(fr, "response", None)
                    summary = ""
                    try:
                        if isinstance(fr_response, dict):
                            dump = json.dumps(fr_response, ensure_ascii=False)
                        else:
                            dump = str(fr_response)
                        summary = dump[:300]
                    except Exception:
                        summary = ""
                    if current_tool_started_at is not None and tool_calls:
                        tool_calls[-1]["finished_at"] = now_ms
                        tool_calls[-1]["duration_ms"] = now_ms - current_tool_started_at
                        tool_calls[-1]["result_summary"] = summary
                    yield {
                        "is_task_complete": False,
                        "tool_result": {
                            "name": fr_name,
                            "summary": summary,
                            "at": now_ms,
                        },
                        "event_id": _next_event_id(),
                        "author": author,
                    }
                current_tool_started_at = None
                continue

            if event.content and event.content.parts:
                new_full = "".join(
                    p.text for p in event.content.parts if getattr(p, "text", None)
                )
                if not new_full:
                    for p in event.content.parts:
                        if (
                            getattr(p, "function_call", None)
                            or getattr(p, "function_response", None)
                            or getattr(p, "inline_data", None)
                            or getattr(p, "file_data", None)
                        ):
                            continue
                        try:
                            dump = p.model_dump_json() if hasattr(p, "model_dump_json") else str(p)
                        except Exception:
                            dump = ""
                        if dump and "thought_signature" not in dump and "Part(" not in dump:
                            new_full += dump
                # Longest common prefix.
                i = 0
                n = min(len(prev_full), len(new_full))
                while i < n and prev_full[i] == new_full[i]:
                    i += 1
                d = new_full[i:]
                prev_full = new_full
                turn_text_len = len(prev_full)
                finish_reason = None
                if not getattr(event, "partial", False):
                    finish_reason = "STOP"
                if d:
                    yield {
                        "is_task_complete": False,
                        "content": d,
                        "event_id": _next_event_id(),
                        "author": author,
                        "ts": now_ms,
                        "latency_ms": now_ms - run_started_at,
                        "text_len": turn_text_len,
                    }
                # Non-partial text event = end of this turn.
                if not getattr(event, "partial", False):
                    yield {
                        "is_task_complete": True,
                        "content": "",
                        "event_id": _next_event_id(),
                        "author": author,
                        "ts": now_ms,
                        "latency_ms": now_ms - run_started_at,
                        "finish_reason": finish_reason or "STOP",
                        "text_len": turn_text_len,
                        "tool_calls": list(tool_calls),
                    }
                    yielded_final = True
                continue

            # Pure final event with no new text: close the turn.
            if event.is_final_response() and not yielded_final:
                yield {
                    "is_task_complete": True,
                    "content": "",
                    "event_id": _next_event_id(),
                    "author": author,
                    "ts": int(datetime.now().timestamp() * 1000),
                    "latency_ms": int(datetime.now().timestamp() * 1000) - run_started_at,
                    "finish_reason": "STOP",
                    "text_len": turn_text_len,
                    "tool_calls": list(tool_calls),
                }
                yielded_final = True

    async def send_message(self, agent_name: str, task: str, tool_context: ToolContext):
        """Sends a task to a remote agent."""
        if agent_name not in self.remote_agent_connections:
            raise ValueError(f"Agent {agent_name} not found")
        client = self.remote_agent_connections[agent_name]

        if not client:
            raise ValueError(f"Client not available for {agent_name}")

        # Simplified task and context ID management
        state = tool_context.state
        task_id = state.get("task_id", str(uuid.uuid4()))
        context_id = state.get("context_id", str(uuid.uuid4()))
        message_id = str(uuid.uuid4())

        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": task}],
                "messageId": message_id,
                "taskId": task_id,
                "contextId": context_id,
            },
        }

        message_request = SendMessageRequest(
            id=message_id, params=MessageSendParams.model_validate(payload)
        )
        send_response: SendMessageResponse = await client.send_message(message_request)
        # Reconfigure stdout to UTF-8 so print() never raises
        # UnicodeEncodeError on Windows when the response contains
        # non-ASCII characters (e.g. emoji in email subjects).
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            print("send_response", send_response)
        except UnicodeEncodeError:
            print("send_response [non-printable]")

        if not isinstance(
            send_response.root, SendMessageSuccessResponse
        ) or not isinstance(send_response.root.result, Task):
            try:
                print("Received a non-success or non-task response. Cannot proceed.")
            except UnicodeEncodeError:
                pass
            return

        response_content = send_response.root.model_dump_json(exclude_none=True)
        json_content = json.loads(response_content)

        resp = []
        if json_content.get("result", {}).get("artifacts"):
            for artifact in json_content["result"]["artifacts"]:
                if artifact.get("parts"):
                    resp.extend(artifact["parts"])
        return resp


def _get_initialized_host_agent_sync():
    """Synchronously creates and initializes the HostAgent."""

    async def _async_main():
        # Hardcoded URLs for the friend agents
        friend_agent_urls = [
            "http://localhost:10002",  # Gmail Agent
            "http://localhost:10003",  # Calender Agent
            "http://localhost:10004",  # Tasks Agent
        ]

        print("initializing host agent")
        hosting_agent_instance = await HostAgent.create(
            remote_agent_addresses=friend_agent_urls
        )
        print("HostAgent initialized")
        return hosting_agent_instance.create_agent()

    try:
        return asyncio.run(_async_main())
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            print(
                f"Warning: Could not initialize HostAgent with asyncio.run(): {e}. "
                "This can happen if an event loop is already running (e.g., in Jupyter). "
                "Consider initializing HostAgent within an async function in your application."
            )
        else:
            raise


root_agent = _get_initialized_host_agent_sync()

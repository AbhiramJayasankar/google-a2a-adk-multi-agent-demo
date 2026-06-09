import { create } from "zustand";
import type {
  AgentMessage,
  LogEvent,
  SessionInfo,
  SubAgent,
  SubAgentHealth,
  ToolCallRecord,
} from "./types";
import { fetchAgents, fetchHealth, fetchSessionInfo, streamChat } from "./api";

interface State {
  sessionId: string;
  messages: AgentMessage[];
  /** Flat append-only log of every SSE event for the inspector drawer. */
  events: LogEvent[];
  agents: SubAgent[];
  agentsLoading: boolean;
  /**
   * Per-sub-agent runtime state map. Updated explicitly by the store
   * when a delegation/tool_call/tool_result/complete/error event fires
   * for a given agent. Used by the Sidebar to render the live dot.
   * Possible values:
   *   - "ok"       : never been called (or reset)
   *   - "working"  : a delegation is in flight to this agent
   *   - "idle"     : the last delegation to this agent has completed
   *   - "err"      : the last delegation to this agent errored
   */
  agentStates: Record<string, "ok" | "working" | "idle" | "err">;
  /** Live per-sub-agent health snapshot from /api/health. */
  health: SubAgentHealth[];
  healthLoading: boolean;
  /** Last fetched session info from /api/session/{id}. */
  sessionInfo: SessionInfo | null;
  /** The most recently observed host model name (turn_meta). */
  activeModel: string | null;
  sending: boolean;
  error: string | null;
  /** Total chunks received across the current session. */
  totalChunks: number;
  /** Total tool calls observed across the current session. */
  totalToolCalls: number;
  /** Wall-clock start of the most recent in-flight stream, for elapsed UI. */
  streamingStartedAt: number | null;
}

interface Actions {
  loadAgents: () => Promise<void>;
  loadHealth: () => Promise<void>;
  loadSessionInfo: () => Promise<void>;
  send: (query: string) => Promise<void>;
  resetSession: () => void;
  clearInspector: () => void;
}

const newId = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

const newSession = () => newId();

/**
 * Merge a streaming delta into the accumulated message text.
 *
 * The BFF/host occasionally re-emits a near-full or full copy of the
 * reply on the final non-partial text event (the LCP in the host's
 * delta logic misses it when ADK inserts spaces or reorders punctuation
 * in the closing chunk). If we naively concatenated we'd render the
 * reply twice. So:
 *   - If `delta` is already a suffix of `current`, ignore it.
 *   - If `current` is a prefix of `delta` (the host re-sent the whole
 *     thing), use `delta` as-is.
 *   - Otherwise, append the longest non-empty suffix of `current` that
 *     matches a prefix of `delta`, then the rest of `delta` (so words
 *     split across a chunk boundary are stitched without duplication).
 */
function mergeChunk(current: string, delta: string): string {
  if (!delta) return current;
  if (!current) return delta;
  if (current.endsWith(delta)) return current;
  if (delta.startsWith(current)) return delta;

  // Find the largest k such that current ends with delta[:k] and k < len(delta).
  const max = Math.min(current.length, delta.length);
  let k = 0;
  for (let len = max; len > 0; len--) {
    if (current.endsWith(delta.slice(0, len))) {
      k = len;
      break;
    }
  }
  return current + delta.slice(k);
}

function pushEvent(
  events: LogEvent[],
  messageId: string,
  ev: Omit<LogEvent, "id" | "at" | "messageId">,
): LogEvent[] {
  const next: LogEvent = {
    id: newId(),
    messageId,
    at: Date.now(),
    ...ev,
  };
  return [...events, next];
}

export const useChat = create<State & Actions>((set, get) => ({
  sessionId: newSession(),
  messages: [],
  events: [],
  agents: [],
  agentsLoading: false,
  health: [],
  agentStates: {},
  healthLoading: false,
  sessionInfo: null,
  activeModel: null,
  sending: false,
  error: null,
  totalChunks: 0,
  totalToolCalls: 0,
  streamingStartedAt: null,

  loadAgents: async () => {
    set({ agentsLoading: true });
    try {
      const agents = await fetchAgents();
      set({ agents, agentsLoading: false });
    } catch {
      // Silent on transient failure. The chat path is unaffected; if the
      // BFF is down the user will see it on the next send(). Don't
      // poison the top-level error banner for a background poll.
      set({ agentsLoading: false });
    }
  },

  loadHealth: async () => {
    set({ healthLoading: true });
    try {
      const res = await fetchHealth();
      const now = Date.now();
      const snap: SubAgentHealth[] = res.sub_agents.map((s) => ({
        url: s.url,
        ok: s.ok,
        status: s.status,
        error: s.error,
        latencyMs: s.latency_ms,
        seenAt: now,
      }));
      set({ health: snap, healthLoading: false });
    } catch {
      // Silent on transient poll failure. The previous behaviour was
      // to set the top-level `error` field, which lit up a red banner
      // in the topbar even though the chat itself was unaffected. A
      // failed /api/health poll is a side concern; only the user-facing
      // send() path should light the topbar red.
      set({ healthLoading: false });
    }
  },

  loadSessionInfo: async () => {
    const id = get().sessionId;
    try {
      const info = await fetchSessionInfo(id);
      set({ sessionInfo: info });
    } catch {
      // Silent: session may not exist yet. The /api/session/{id}
      // endpoint is best-effort debug info.
    }
  },

  send: async (query: string) => {
    const trimmed = query.trim();
    if (!trimmed || get().sending) return;

    const startedAt = Date.now();
    const userMsg: AgentMessage = {
      id: newId(),
      role: "user",
      content: trimmed,
      updates: [],
      streaming: false,
      state: "done",
      chunks: 0,
      createdAt: startedAt,
      completedAt: startedAt,
    };
    const agentMsg: AgentMessage = {
      id: newId(),
      role: "agent",
      content: "",
      updates: [],
      streaming: true,
      state: "working",
      chunks: 0,
      createdAt: startedAt,
    };

    set((s) => ({
      messages: [...s.messages, userMsg, agentMsg],
      events: [
        ...s.events,
        ...pushEvent([], userMsg.id, {
          kind: "session",
          detail: `User -> ${trimmed.slice(0, 80)}`,
          raw: { query: trimmed },
        }),
        ...pushEvent([], agentMsg.id, {
          kind: "session",
          detail: "Stream opened",
        }),
      ],
      sending: true,
      error: null,
      streamingStartedAt: startedAt,
    }));

    let localChunks = 0;
    let localToolCalls = 0;
    // Per-chunk accumulator for cross-branch updates (e.g. delegations
    // and tool_results both touching the per-agent state map). Cleared
    // at the start of every chunk.
    let patch: { agentStates?: Record<string, "ok" | "working" | "idle" | "err"> } = {};
    try {
      await streamChat(trimmed, get().sessionId, (chunk) => {
        const state = get();
        const msgs = state.messages;
        const events = state.events;
        const idx = msgs.findIndex((m) => m.id === agentMsg.id);
        if (idx === -1) return;
        patch = {};
        const current = msgs[idx];
        const next: AgentMessage = { ...current };
        const now = Date.now();
        let newEvent: LogEvent | null = null;
        let chunksDelta = 0;
        let toolDelta = 0;

        // Per-turn preamble from the host: model, session id, agent name.
        if (chunk.turn_meta) {
          next.model = chunk.turn_meta.model;
          next.agentName = chunk.turn_meta.agent;
          set({ activeModel: chunk.turn_meta.model });
          newEvent = {
            id: newId(),
            messageId: agentMsg.id,
            at: now,
            kind: "turn_meta",
            detail: `${chunk.turn_meta.model} · ${chunk.turn_meta.agent}`,
            model: chunk.turn_meta.model,
            author: chunk.turn_meta.agent,
            eventId: chunk.event_id,
            raw: chunk,
          };
        }

        if (chunk.updates) {
          next.updates = [...current.updates, chunk.updates];
          next.state = current.state === "done" ? "done" : "working";
          newEvent = newEvent ?? {
            id: newId(),
            messageId: agentMsg.id,
            at: now,
            kind: "update",
            detail: chunk.updates,
            eventId: chunk.event_id,
            author: chunk.author,
            latencyMs: chunk.latency_ms,
            raw: chunk,
          };
        }

        if (chunk.delegation) {
          next.delegation = [...(current.delegation ?? []), chunk.delegation];
          next.state = "delegating";
          // Mark the sub-agent as "working" in the per-agent state map
          // so the Sidebar dot turns to busy. The "idle"/"err" state
          // is set when the corresponding tool_result or complete chunk
          // for this turn arrives below.
          patch.agentStates = {
            ...state.agentStates,
            [chunk.delegation.agent]: "working",
          };
          newEvent = newEvent ?? {
            id: newId(),
            messageId: agentMsg.id,
            at: now,
            kind: "delegation",
            agent: chunk.delegation.agent,
            detail: chunk.delegation.detail,
            eventId: chunk.event_id,
            author: chunk.author,
            latencyMs: chunk.latency_ms,
            raw: chunk,
          };
        }

        if (chunk.tool_call) {
          toolDelta += 1;
          const record: ToolCallRecord = {
            id: chunk.tool_call.id,
            name: chunk.tool_call.name,
            agent: chunk.tool_call.agent,
            args: chunk.tool_call.args,
            startedAt: chunk.tool_call.at,
          };
          next.toolCalls = [...(current.toolCalls ?? []), record];
          if (chunk.tool_call.agent) {
            patch.agentStates = {
              ...(patch.agentStates ?? state.agentStates),
              [chunk.tool_call.agent]: "working",
            };
          }
          newEvent = newEvent ?? {
            id: newId(),
            messageId: agentMsg.id,
            at: now,
            kind: "tool_call",
            detail: `${chunk.tool_call.name}(${Object.keys(chunk.tool_call.args).join(", ")})`,
            agent: chunk.tool_call.agent,
            eventId: chunk.event_id,
            author: chunk.author,
            toolArgs: chunk.tool_call.args,
            toolName: chunk.tool_call.name,
            toolCallId: chunk.tool_call.id,
            latencyMs: chunk.latency_ms,
            raw: chunk,
          };
        }

        if (chunk.tool_result) {
          // Attach the result summary to the matching in-flight tool call.
          const tcs = next.toolCalls ?? current.toolCalls ?? [];
          // Find the most-recent in-flight tool call for the SAME tool
          // name. That is the one this result corresponds to; any other
          // tool calls in flight (rare, but possible) keep their state.
          let matchedAgent: string | undefined;
          for (let i = tcs.length - 1; i >= 0; i--) {
            const tc = tcs[i];
            if (tc.name === chunk.tool_result!.name && tc.finishedAt == null) {
              matchedAgent = tc.agent;
              break;
            }
          }
          const updated: ToolCallRecord[] = tcs.map((tc) => {
            if (tc.id === (newEvent as LogEvent | null)?.toolCallId) {
              return {
                ...tc,
                finishedAt: chunk.tool_result!.at,
                resultSummary: chunk.tool_result!.summary,
              };
            }
            return tc;
          });
          next.toolCalls = updated;
          if (matchedAgent) {
            patch.agentStates = {
              ...(patch.agentStates ?? state.agentStates),
              [matchedAgent]: "idle",
            };
          }
          newEvent = newEvent ?? {
            id: newId(),
            messageId: agentMsg.id,
            at: now,
            kind: "tool_result",
            detail: `${chunk.tool_result.name}: ${chunk.tool_result.summary.slice(0, 100)}`,
            eventId: chunk.event_id,
            author: chunk.author,
            toolName: chunk.tool_result.name,
            toolResultSummary: chunk.tool_result.summary,
            latencyMs: chunk.latency_ms,
            raw: chunk,
          };
        }

        if (chunk.is_task_complete) {
          if (chunk.content) {
            next.content = mergeChunk(current.content, chunk.content);
          }
          next.streaming = false;
          next.state = "done";
          next.completedAt = next.completedAt ?? now;
          next.totalMs = (next.completedAt ?? now) - next.createdAt;
          next.ttfbMs =
            next.ttfbMs ??
            (next.firstChunkAt ? next.firstChunkAt - next.createdAt : undefined);
          next.finishReason = chunk.finish_reason ?? next.finishReason;
          next.tokenEstimate = Math.round(next.content.length / 4);
          if (chunk.tool_calls && chunk.tool_calls.length) {
            const seen = new Set((next.toolCalls ?? []).map((t) => t.id));
            for (const tc of chunk.tool_calls) {
              if (seen.has(tc.id)) continue;
              next.toolCalls = [...(next.toolCalls ?? []), tc];
            }
          }
          // Flip every agent that was "working" for this turn to
          // "idle" (or "err" if the message is in the error state).
          // We use the resolved `next.toolCalls` plus any agents we
          // observed in the delegation list for this turn. The
          // patch.agentStates accumulator carries earlier flips from
          // the tool_result branch.
          const turnAgents = new Set<string>();
          for (const d of next.delegation ?? []) turnAgents.add(d.agent);
          for (const tc of next.toolCalls ?? []) {
            if (tc.agent) turnAgents.add(tc.agent);
          }
          // next.state was set to "done" just above; the "error" branch
          // is handled in the catch block. The union narrows away the
          // "error" arm here, so we hard-code "idle" -- the success
          // path is the only one that runs in this branch.
          const finalAgentState: "err" | "idle" = "idle";
          const states = {
            ...(patch.agentStates ?? state.agentStates),
          };
          for (const a of turnAgents) {
            if (states[a] === "working") states[a] = finalAgentState;
          }
          patch.agentStates = states;
          const toolCount = (next.toolCalls ?? []).length;
          localToolCalls = Math.max(localToolCalls, toolCount);
          newEvent = newEvent ?? {
            id: newId(),
            messageId: agentMsg.id,
            at: now,
            kind: "complete",
            detail: `done in ${next.totalMs}ms · ${toolCount} tool call${toolCount === 1 ? "" : "s"}`,
            eventId: chunk.event_id,
            author: chunk.author,
            latencyMs: chunk.latency_ms,
            finishReason: chunk.finish_reason,
            textLen: chunk.text_len ?? next.content.length,
            raw: chunk,
          };
        } else if (chunk.content) {
          next.content = mergeChunk(current.content, chunk.content);
          next.chunks = current.chunks + 1;
          next.firstChunkAt = current.firstChunkAt ?? now;
          next.ttfbMs =
            next.ttfbMs ?? (next.firstChunkAt ? next.firstChunkAt - next.createdAt : undefined);
          next.state = "streaming";
          next.tokenEstimate = Math.round(next.content.length / 4);
          localChunks += 1;
          chunksDelta = 1;
          newEvent = newEvent ?? {
            id: newId(),
            messageId: agentMsg.id,
            at: now,
            kind: "chunk",
            agent: chunk.author ?? "host",
            detail:
              chunk.content.length > 120
                ? chunk.content.slice(0, 120) + "..."
                : chunk.content,
            eventId: chunk.event_id,
            author: chunk.author,
            latencyMs: chunk.latency_ms,
            textLen: chunk.text_len,
            raw: chunk,
          };
        }

        const copy = msgs.slice();
        copy[idx] = next;
        set({
          messages: copy,
          events: newEvent ? [...events, newEvent] : events,
          totalChunks: state.totalChunks + chunksDelta,
          totalToolCalls: state.totalToolCalls + toolDelta,
          ...(patch.agentStates ? { agentStates: patch.agentStates } : {}),
        });
      });
    } catch (e) {
      const errText = e instanceof Error ? e.message : String(e);
      set((s) => ({
        error: errText,
        events: pushEvent(s.events, agentMsg.id, {
          kind: "error",
          detail: errText,
        }),
      }));
      const msgs = get().messages;
      const idx = msgs.findIndex((m) => m.id === agentMsg.id);
      if (idx !== -1) {
        const copy = msgs.slice();
        const now = Date.now();
        const failed = copy[idx];
        copy[idx] = {
          ...failed,
          streaming: false,
          state: "error",
          content: failed.content || "(stream error)",
          completedAt: now,
        };
        // Flip every agent that was "working" at the time of the error
        // to "err" so the Sidebar dot does not stay stuck on busy.
        const states = { ...get().agentStates };
        for (const d of failed.delegation ?? []) {
          if (states[d.agent] === "working") states[d.agent] = "err";
        }
        for (const tc of failed.toolCalls ?? []) {
          if (tc.agent && states[tc.agent] === "working") {
            states[tc.agent] = "err";
          }
        }
        set({ messages: copy, agentStates: states });
      }
    } finally {
      set({ sending: false, streamingStartedAt: null });
    }
  },

  resetSession: () => {
    set((s) => ({
      sessionId: newSession(),
      messages: [],
      events: [
        ...s.events,
        {
          id: newId(),
          messageId: "-",
          at: Date.now(),
          kind: "session",
          detail: "Session reset",
        },
      ],
      sessionInfo: null,
      totalToolCalls: 0,
      totalChunks: 0,
      agentStates: {},
      error: null,
    }));
  },

  clearInspector: () => set({ events: [] }),
}));

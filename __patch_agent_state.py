from pathlib import Path

# 1) Extend store with a per-agent state map and a small helper to update
#    it. The Sidebar's "working/idle" derivation by walking the event log
#    was buggy because the closing events (tool_result, complete) don't
#    carry the sub-agent name in their `agent` field — only the host
#    author's name. So the walk stopped at the first `delegation` event
#    for each agent and never saw a closing event with that same agent
#    name, leaving every agent stuck at "working" forever.
p = Path(r"website\frontend\src\store.ts")
src = p.read_text(encoding="utf-8")

# 1a) Extend the State interface.
old_state = '''  /** Live per-sub-agent health snapshot from /api/health. */
  health: SubAgentHealth[];'''
new_state = '''  /**
   * Per-sub-agent runtime state map. Updated explicitly by the store
   * when a delegation/tool_call/tool_result/complete/error event fires
   * for a given agent. Used by the Sidebar to render the live dot.
   * Possible values:
   *   - "ok"       : never been called (or reset)
   *   - "working"  : a delegation is in flight to this agent
   *   - "idle"     : the last delegation to this agent has completed
   *   - "err"      : the last delegation to this agent errored
   */
  agentStates: Record<string, "ok" | "working" | "idle" | "err">;'''
assert old_state in src
src = src.replace(old_state, new_state, 1)

# 1b) Add the new field to the initial state defaults.
old_init_state = '''  health: [],'''
new_init_state = '''  health: [],
  agentStates: {},'''
assert old_init_state in src
src = src.replace(old_init_state, new_init_state, 1)

# 1c) Update agent-state on each relevant event. The cleanest place is
#     inside the existing stream chunk handler in `send()`. We patch
#     the four branches that touch an agent (delegation, tool_call,
#     tool_result, complete/error).
#
# The `delegation` branch:
old_delegation = '''        if (chunk.delegation) {
          next.delegation = [...(current.delegation ?? []), chunk.delegation];
          next.state = "delegating";
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
        }'''
new_delegation = '''        if (chunk.delegation) {
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
        }'''
assert old_delegation in src
src = src.replace(old_delegation, new_delegation, 1)

# The `tool_call` branch is reached for any function call. For our host
# the only function is `send_message`, and when its `agent` field is
# set (always for delegation) it implies the same "working" mark.
old_tool_call = '''        if (chunk.tool_call) {
          toolDelta += 1;
          const record: ToolCallRecord = {
            id: chunk.tool_call.id,
            name: chunk.tool_call.name,
            agent: chunk.tool_call.agent,
            args: chunk.tool_call.args,
            startedAt: chunk.tool_call.at,
          };
          next.toolCalls = [...(current.toolCalls ?? []), record];
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
        }'''
new_tool_call = '''        if (chunk.tool_call) {
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
        }'''
assert old_tool_call in src
src = src.replace(old_tool_call, new_tool_call, 1)

# The `tool_result` branch: when a tool result comes back, the matching
# agent is done. We need to know which agent's tool returned, so we
# match the result name to the last in-flight tool call on this message
# that named the same tool/agent.
old_tool_result = '''        if (chunk.tool_result) {
          // Attach the result summary to the matching in-flight tool call.
          const tcs = next.toolCalls ?? current.toolCalls ?? [];
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
        }'''
new_tool_result = '''        if (chunk.tool_result) {
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
        }'''
assert old_tool_result in src
src = src.replace(old_tool_result, new_tool_result, 1)

# The `is_task_complete` branch: when the host closes the turn, every
# sub-agent that was marked "working" for this turn is now "idle". Use
# the per-message `toolCalls` (which has been fully resolved by now) to
# figure out which agents to flip.
old_complete = '''        if (chunk.is_task_complete) {
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
          const toolCount = (next.toolCalls ?? []).length;
          localToolCalls = Math.max(localToolCalls, toolCount);'''
new_complete = '''        if (chunk.is_task_complete) {
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
          const finalAgentState =
            next.state === "error" ? "err" : "idle";
          const states = {
            ...(patch.agentStates ?? state.agentStates),
          };
          for (const a of turnAgents) {
            if (states[a] === "working") states[a] = finalAgentState;
          }
          patch.agentStates = states;
          const toolCount = (next.toolCalls ?? []).length;
          localToolCalls = Math.max(localToolCalls, toolCount);'''
assert old_complete in src
src = src.replace(old_complete, new_complete, 1)

# 1d) The stream chunk handler uses a local `patch` accumulator that is
#     not yet declared. Declare it just before the stream callback and
#     merge it into the final set() call.
old_try = '''    let localChunks = 0;
    let localToolCalls = 0;
    try {
      await streamChat(trimmed, get().sessionId, (chunk) => {
        const state = get();
        const msgs = state.messages;
        const events = state.events;
        const idx = msgs.findIndex((m) => m.id === agentMsg.id);
        if (idx === -1) return;
        const current = msgs[idx];
        const next: AgentMessage = { ...current };
        const now = Date.now();
        let newEvent: LogEvent | null = null;
        let chunksDelta = 0;
        let toolDelta = 0;'''
new_try = '''    let localChunks = 0;
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
        let toolDelta = 0;'''
assert old_try in src
src = src.replace(old_try, new_try, 1)

# 1e) Merge the `patch` accumulator into the final set() call.
old_set = '''        const copy = msgs.slice();
        copy[idx] = next;
        set({
          messages: copy,
          events: newEvent ? [...events, newEvent] : events,
          totalChunks: state.totalChunks + chunksDelta,
          totalToolCalls: state.totalToolCalls + toolDelta,
        });
      });'''
new_set = '''        const copy = msgs.slice();
        copy[idx] = next;
        set({
          messages: copy,
          events: newEvent ? [...events, newEvent] : events,
          totalChunks: state.totalChunks + chunksDelta,
          totalToolCalls: state.totalToolCalls + toolDelta,
          ...(patch.agentStates ? { agentStates: patch.agentStates } : {}),
        });
      });'''
assert old_set in src
src = src.replace(old_set, new_set, 1)

# 1f) The error branch (catch block) should also flip any agents that
#     were "working" at the time of the error to "err".
old_catch = '''    } catch (e) {
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
        copy[idx] = {
          ...copy[idx],
          streaming: false,
          state: "error",
          content: copy[idx].content || "(stream error)",
          completedAt: now,
        };
        set({ messages: copy });
      }
    } finally {'''
new_catch = '''    } catch (e) {
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
    } finally {'''
assert old_catch in src
src = src.replace(old_catch, new_catch, 1)

# 1g) resetSession clears the agent-state map.
old_reset = '''  resetSession: () => {
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
      error: null,
    }));
  },'''
new_reset = '''  resetSession: () => {
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
  },'''
assert old_reset in src
src = src.replace(old_reset, new_reset, 1)

p.write_text(src, encoding="utf-8")
print("store.ts updated, size:", len(src))

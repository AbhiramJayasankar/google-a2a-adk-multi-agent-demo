from pathlib import Path

# 2) Update Sidebar to use the new `agentStates` map from the store
#    instead of re-deriving it from the event log.
p = Path(r"website\frontend\src\components\Sidebar.tsx")
src = p.read_text(encoding="utf-8")

old_use = '''export function Sidebar() {
  const { agents, agentsLoading, loadAgents, resetSession, events, sending, messages } = useChat();'''
new_use = '''export function Sidebar() {
  const {
    agents,
    agentsLoading,
    loadAgents,
    resetSession,
    events,
    sending,
    messages,
    agentStates,
  } = useChat();'''
assert old_use in src
src = src.replace(old_use, new_use, 1)

old_memo = '''  // Derive a per-agent status from the event log: "working" if the most
  // recent delegation to that agent hasn't been followed by a complete,
  // otherwise "idle". Falls back to "ok" when no events have been seen.
  const agentStatus = useMemo(() => {
    const map = new Map<string, "working" | "idle">();
    // Walk events newest -> oldest, first hit per agent wins.
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i];
      const name = e.agent;
      if (!name || map.has(name)) continue;
      if (e.kind === "delegation") map.set(name, "working");
      else if (e.kind === "complete" || e.kind === "error") map.set(name, "idle");
    }
    return map;
  }, [events]);'''
new_memo = '''  // Per-agent state comes directly from the store, which maintains a
  // `Map<agent, state>` by tagging every delegation/tool_call as
  // "working" and the matching tool_result/complete/error as
  // "idle"/"err". This avoids the previous bug where the Sidebar
  // derived state by walking the event log: the closing events
  // (tool_result, complete) don't carry the sub-agent name in their
  // `agent` field, so the walk stopped at the most recent delegation
  // and left every agent stuck at "working" forever.
  const agentStatus = useMemo(
    () => new Map(Object.entries(agentStates)),
    [agentStates],
  );'''
assert old_memo in src
src = src.replace(old_memo, new_memo, 1)

p.write_text(src, encoding="utf-8")
print("Sidebar.tsx updated, size:", len(src))

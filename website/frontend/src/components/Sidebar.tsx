import { useEffect, useMemo } from "react";
import { useChat } from "../store";
import type { SubAgentHealth } from "../types";

/**
 * Left rail — the topology board.
 *
 * Reads as an instrument panel: section labels in small caps, agent
 * rows as field entries with a state pip, a one-line description, and
 * a tiny live latency meter. Hairline rules separate sections; nothing
 * has rounded corners.
 */
export function Sidebar() {
  const {
    agents,
    agentsLoading,
    loadAgents,
    resetSession,
    sending,
    messages,
    agentStates,
    health,
    healthLoading,
    loadHealth,
    loadSessionInfo,
    sessionId,
  } = useChat();

  useEffect(() => {
    void loadAgents();
  }, [loadAgents]);

  useEffect(() => {
    void loadHealth();
    void loadSessionInfo();
    const id = setInterval(() => {
      void loadHealth();
      void loadSessionInfo();
    }, 5000);
    return () => clearInterval(id);
    // sessionId is in the closure to refresh session info when it rotates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadHealth, loadSessionInfo, sessionId]);

  const healthByUrl = useMemo(() => {
    const m = new Map<string, SubAgentHealth>();
    for (const h of health) m.set(h.url, h);
    return m;
  }, [health]);

  const healthForAgent = (url: string | undefined) =>
    url ? healthByUrl.get(url) : undefined;

  const agentStatus = useMemo(
    () => new Map(Object.entries(agentStates)),
    [agentStates],
  );

  const lastDelegations = useMemo(() => {
    const seen = new Set<string>();
    const out: { agent: string; detail: string; at: number }[] = [];
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role !== "agent") continue;
      for (let j = (m.delegation?.length ?? 0) - 1; j >= 0; j--) {
        const d = m.delegation![j];
        if (seen.has(d.agent)) continue;
        seen.add(d.agent);
        out.push({ agent: d.agent, detail: d.detail, at: d.at });
        if (out.length >= 3) break;
      }
      if (out.length >= 3) break;
    }
    return out;
  }, [messages]);

  const sessionStart = messages[0]?.createdAt;
  const sessionAge = sessionStart
    ? formatAge(Date.now() - sessionStart)
    : "0s";

  const upCount = health.filter((h) => h.ok).length;
  const totalCount = health.length;
  const totalMs = Math.max(
    1,
    health.reduce((acc, h) => acc + (h.latencyMs ?? 0), 0),
  );

  return (
    <aside
      className="w-64 shrink-0 border-r border-[var(--color-grid)] bg-[var(--color-panel)] flex flex-col"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {/* Topology header. */}
      <div className="px-3 py-2.5 border-b border-[var(--color-grid)]">
        <div className="flex items-baseline justify-between">
          <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--color-mute)]">
            topology
          </div>
          <div className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-mute)] tabular-nums">
            {healthLoading
              ? "probing…"
              : totalCount > 0
                ? `${upCount}/${totalCount} up`
                : "—"}
          </div>
        </div>
        <div className="mt-2 flex items-center gap-2 text-[11px] text-[var(--color-ink-2)]">
          <span
            className={`inline-block h-1.5 w-1.5 ${
              sending
                ? "bg-[var(--color-signal)] signal-blink"
                : "bg-[var(--color-ok)]"
            }`}
            style={{ transform: "rotate(45deg)" }}
          />
          <span className="uppercase tracking-wider">
            {sending ? "busy" : "idle"}
          </span>
          <span className="text-[var(--color-mute-2)]">·</span>
          <span className="text-[var(--color-mute)] uppercase">run</span>
          <span className="text-[var(--color-ink)] tabular-nums">
            {messages.length}
          </span>
          <span className="text-[var(--color-mute-2)]">·</span>
          <span className="text-[var(--color-mute)] uppercase">age</span>
          <span className="text-[var(--color-ink)] tabular-nums">
            {sessionAge}
          </span>
        </div>
      </div>

      {/* Agents list. */}
      <div className="px-2 py-2 border-b border-[var(--color-grid)]">
        <AgentRow
          name="Host_Agent"
          status={sending ? "working" : "idle"}
          detail="Core orchestrator"
          meta="local"
        />
        <div className="my-1.5 mx-2 border-t border-dashed border-[var(--color-grid-2)]" />
        {agentsLoading && (
          <div className="text-[11px] text-[var(--color-mute)] px-2 py-1">
            probing sub-agents…
          </div>
        )}
        {!agentsLoading && agents.length === 0 && (
          <div className="text-[11px] text-[var(--color-mute)] px-2 py-1">
            no sub-agents connected
          </div>
        )}
        {agents.map((a) => {
          const live = agentStatus.get(a.name);
          const h = healthForAgent(a.url);
          const finalStatus: "ok" | "working" | "idle" | "warn" | "err" =
            h && !h.ok
              ? "err"
              : live === "working"
                ? "working"
                : "ok";
          const detail = a.description;
          const metaParts: string[] = [];
          if (a.version) metaParts.push(`v${a.version}`);
          if (a.provider) metaParts.push(a.provider);
          return (
            <AgentRow
              key={a.name}
              name={a.name}
              status={finalStatus}
              detail={detail}
              meta={metaParts.join(" · ")}
              healthError={h && !h.ok ? h.error ?? `HTTP ${h.status ?? "?"}` : undefined}
              latencyMs={h?.latencyMs}
              maxLatencyMs={totalMs}
              lastSeenAt={h?.seenAt}
            />
          );
        })}
      </div>

      {/* Recent delegations. */}
      {lastDelegations.length > 0 && (
        <div className="px-3 py-2.5 border-b border-[var(--color-grid)]">
          <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--color-mute)] mb-2">
            recent delegations
          </div>
          <ul className="flex flex-col gap-2 text-[11px]">
            {lastDelegations.map((d, i) => {
              const live = agentStatus.get(d.agent) === "working";
              return (
                <li key={i} className="flex items-start gap-2">
                  <span
                    className={`mt-1 h-1.5 w-1.5 shrink-0 ${
                      live
                        ? "bg-[var(--color-signal)] signal-blink"
                        : "bg-[var(--color-ok)]"
                    }`}
                    style={{ transform: "rotate(45deg)" }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="text-[var(--color-ink)] truncate">
                      {d.agent}
                    </div>
                    <div className="text-[var(--color-mute)] line-clamp-2 leading-snug">
                      {d.detail}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Footer actions. */}
      <div className="mt-auto p-2 border-t border-[var(--color-grid)] flex flex-col gap-1.5">
        <button
          onClick={resetSession}
          className="w-full flex items-center justify-between"
          style={{ padding: "6px 10px" }}
        >
          <span className="uppercase tracking-wider">new session</span>
          <span className="text-[var(--color-mute)]">↻</span>
        </button>
      </div>
    </aside>
  );
}

function AgentRow({
  name,
  detail,
  status,
  meta,
  healthError,
  latencyMs,
  maxLatencyMs,
  lastSeenAt,
}: {
  name: string;
  detail: string;
  status: "ok" | "working" | "idle" | "warn" | "err";
  meta?: string;
  healthError?: string;
  latencyMs?: number;
  maxLatencyMs?: number;
  lastSeenAt?: number;
}) {
  const dotClass =
    status === "working"
      ? "bg-[var(--color-signal)] signal-blink"
      : status === "err"
        ? "bg-[var(--color-err)]"
        : status === "warn"
          ? "bg-[var(--color-warn)]"
          : "bg-[var(--color-ok)]";

  const seen =
    lastSeenAt && Date.now() - lastSeenAt < 30_000
      ? "now"
      : lastSeenAt
        ? `${Math.round((Date.now() - lastSeenAt) / 1000)}s`
        : null;

  const meterPct =
    latencyMs != null && maxLatencyMs
      ? Math.max(6, Math.min(100, (latencyMs / maxLatencyMs) * 100))
      : null;

  return (
    <div className="px-2 py-1.5 hover:bg-[var(--color-panel-2)] group">
      <div className="flex items-center gap-2">
        <span
          className={`h-1.5 w-1.5 shrink-0 ${dotClass}`}
          style={{ transform: "rotate(45deg)" }}
          title={healthError ?? (status === "working" ? "busy" : "ok")}
        />
        <div className="text-[12px] font-medium text-[var(--color-ink)] truncate flex-1">
          {name}
        </div>
        {status === "working" && (
          <span
            className="text-[9px] font-mono uppercase tracking-[0.12em] text-[var(--color-signal)]"
            style={{ letterSpacing: "0.12em" }}
          >
            busy
          </span>
        )}
        {status === "err" && (
          <span
            className="text-[9px] font-mono uppercase tracking-[0.12em] text-[var(--color-err)]"
            title={healthError}
          >
            down
          </span>
        )}
        {meta && (
          <span className="text-[10px] text-[var(--color-mute)] truncate">
            {meta}
          </span>
        )}
      </div>
      {detail && (
        <div className="mt-0.5 ml-3.5 text-[10.5px] text-[var(--color-mute)] line-clamp-2 leading-snug">
          {detail}
          {healthError && (
            <span className="text-[var(--color-err)]"> · {healthError}</span>
          )}
        </div>
      )}
      {meterPct != null && (
        <div
          className="mt-1 ml-3.5 h-px bg-[var(--color-grid-2)] relative"
          title={`latency ${latencyMs}ms`}
        >
          <div
            className="absolute left-0 top-0 h-px bg-[var(--color-ink-2)]"
            style={{ width: `${meterPct}%` }}
          />
        </div>
      )}
      {seen && (
        <div className="mt-0.5 ml-3.5 text-[9.5px] text-[var(--color-mute-2)] uppercase tracking-wider">
          seen {seen}
        </div>
      )}
    </div>
  );
}

function formatAge(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m${s % 60 ? `${s % 60}s` : ""}`;
  const h = Math.floor(m / 60);
  return `${h}h${m % 60 ? `${m % 60}m` : ""}`;
}

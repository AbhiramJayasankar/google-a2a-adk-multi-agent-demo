import { useEffect, useState } from "react";
import { useChat } from "../store";

/**
 * Persistent operations status line.
 *
 * Replaces the original TopBar + SessionStrip with a single hairline
 * row that reads like an oscilloscope / network-tap header. This is the
 * "signature" element of the redesign: a single live indicator, dense
 * monospaced metrics, and a thin animated trace behind the row when
 * something is in flight.
 */
export function StatusBar({
  onToggleInspector,
  inspectorOpen,
}: {
  onToggleInspector: () => void;
  inspectorOpen: boolean;
}) {
  const {
    sessionId,
    sending,
    streamingStartedAt,
    totalChunks,
    totalToolCalls,
    activeModel,
    messages,
    sessionInfo,
  } = useChat();
  const [elapsed, setElapsed] = useState(0);
  const [copied, setCopied] = useState(false);
  const [clock, setClock] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!streamingStartedAt) {
      setElapsed(0);
      return;
    }
    const start = streamingStartedAt;
    const id = setInterval(() => {
      setElapsed(Date.now() - start);
    }, 100);
    return () => clearInterval(id);
  }, [streamingStartedAt]);

  const last = messages[messages.length - 1];
  const inFlightId =
    sending && last?.role === "agent" ? last.id.slice(0, 8) : null;
  const lastAgent = [...messages].reverse().find((m) => m.role === "agent");
  const lastAgentDone = lastAgent && lastAgent.state === "done" ? lastAgent : null;

  const time = formatClock(new Date(clock));

  return (
    <header
      className="relative h-9 shrink-0 border-b border-[var(--color-grid)] bg-[var(--color-panel)] flex items-stretch text-[11px] font-mono"
      style={{ letterSpacing: "0.02em" }}
    >
      {sending && (
        <div
          aria-hidden
          className="absolute left-0 right-0 bottom-0 overflow-hidden"
          style={{ height: 1 }}
        >
          <div className="trace-sweep" />
        </div>
      )}

      <div className="flex items-center gap-2 px-3 border-r border-[var(--color-grid)] bg-[var(--color-panel-2)]">
        <span
          className={`inline-block h-2 w-2 ${sending ? "bg-[var(--color-signal)] signal-blink" : "bg-[var(--color-ok)]"}`}
          style={{ transform: "rotate(45deg)" }}
        />
        <span className="text-[var(--color-ink)] font-semibold tracking-[0.18em]">
          TRIAGENT
        </span>
        <span className="text-[var(--color-mute)]">//</span>
        <span className="text-[var(--color-mute)] uppercase">ops</span>
      </div>

      <div className="flex items-center gap-2 px-3 border-r border-[var(--color-grid)] min-w-0">
        <span className="text-[var(--color-mute)] uppercase">state</span>
        <span
          className={`uppercase font-semibold ${
            sending ? "text-[var(--color-signal)]" : "text-[var(--color-ok)]"
          }`}
        >
          {sending ? "streaming" : "idle"}
        </span>
        {sending && (
          <span className="text-[var(--color-ink-2)] tabular-nums">
            {formatMs(elapsed)}
          </span>
        )}
      </div>

      <button
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(sessionId);
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          } catch {
            /* ignore */
          }
        }}
        className="flex items-center gap-2 px-3 border-r border-[var(--color-grid)] hover:bg-[var(--color-panel-2)]"
        style={{ border: "none", borderRight: "1px solid var(--color-grid)" }}
        title="Click to copy session id"
      >
        <span className="text-[var(--color-mute)] uppercase">session</span>
        <span className="text-[var(--color-ink)] tabular-nums">
          {copied ? "copied" : `${sessionId.slice(0, 8)}…`}
        </span>
      </button>

      <div className="flex items-center gap-3 px-3 border-r border-[var(--color-grid)] tabular-nums">
        {inFlightId && (
          <span className="flex items-center gap-1.5">
            <span className="text-[var(--color-mute)] uppercase">run</span>
            <span className="text-[var(--color-ink-2)]">{inFlightId}</span>
          </span>
        )}
        <span className="flex items-center gap-1.5">
          <span className="text-[var(--color-mute)] uppercase">chunks</span>
          <span className="text-[var(--color-ink-2)]">{totalChunks}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-[var(--color-mute)] uppercase">tools</span>
          <span className="text-[var(--color-ink-2)]">{totalToolCalls}</span>
        </span>
      </div>

      {activeModel && (
        <div className="flex items-center gap-2 px-3 border-r border-[var(--color-grid)] min-w-0">
          <span className="text-[var(--color-mute)] uppercase">model</span>
          <span
            className="text-[var(--color-signal-2)] truncate"
            title={activeModel}
            style={{ maxWidth: 220 }}
          >
            {activeModel}
          </span>
        </div>
      )}

      {lastAgentDone && (
        <div
          className="flex items-center gap-2 px-3 border-r border-[var(--color-grid)] tabular-nums"
          title={`ttfb ${lastAgentDone.ttfbMs ?? "?"}ms · finish ${lastAgentDone.finishReason ?? "?"}`}
        >
          <span className="text-[var(--color-mute)] uppercase">last</span>
          <span className="text-[var(--color-ink-2)]">
            {lastAgentDone.totalMs ?? "?"}ms
          </span>
          <span className="text-[var(--color-mute-2)]">·</span>
          <span className="text-[var(--color-ink-2)]">
            ~{lastAgentDone.tokenEstimate ?? 0}tok
          </span>
        </div>
      )}

      {sessionInfo && sessionInfo.exists && (
        <div
          className="flex items-center gap-2 px-3 border-r border-[var(--color-grid)] tabular-nums"
          title={`ADK session events: ${sessionInfo.events_count ?? 0}`}
        >
          <span className="text-[var(--color-mute)] uppercase">adk</span>
          <span className="text-[var(--color-ink-2)]">
            {sessionInfo.events_count ?? 0}ev
          </span>
        </div>
      )}

      <div className="flex-1" />

      <div className="flex items-center gap-2 px-3 border-l border-[var(--color-grid)] tabular-nums">
        <span className="text-[var(--color-mute)] uppercase">utc</span>
        <span className="text-[var(--color-ink-2)]">{time}</span>
      </div>

      <button
        onClick={onToggleInspector}
        className="flex items-center gap-2 px-3 border-l border-[var(--color-grid)] hover:bg-[var(--color-panel-2)]"
        style={{ border: "none", borderLeft: "1px solid var(--color-grid)" }}
        title="Toggle event inspector"
      >
        <span
          className="inline-block h-1.5 w-1.5"
          style={{
            background: inspectorOpen
              ? "var(--color-signal)"
              : "var(--color-mute)",
            transform: "rotate(45deg)",
          }}
        />
        <span
          className={`uppercase ${inspectorOpen ? "text-[var(--color-signal)]" : "text-[var(--color-ink-2)]"}`}
        >
          {inspectorOpen ? "inspect" : "events"}
        </span>
      </button>
    </header>
  );
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  const rem = ms % 1000;
  return `${s}.${rem.toString().padStart(3, "0")}s`;
}

function formatClock(d: Date): string {
  const h = d.getUTCHours().toString().padStart(2, "0");
  const m = d.getUTCMinutes().toString().padStart(2, "0");
  const s = d.getUTCSeconds().toString().padStart(2, "0");
  return `${h}:${m}:${s}`;
}

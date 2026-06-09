import { useEffect, useMemo, useRef, useState } from "react";
import { useChat } from "../store";
import type { EventKind, LogEvent } from "../types";

/**
 * Right-side event inspector.
 *
 * Re-skinned to read as a raw network-tap view: a filter strip on top,
 * an event list with hairline rows on the left, and a JSON payload pane
 * on the right. No boxes, no rounded corners, no decorative icons —
 * the data is the decoration.
 */
export function Inspector({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { events, totalChunks, clearInspector } = useChat();
  const [filter, setFilter] = useState<EventKind | "all">("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const filtered = useMemo(
    () =>
      filter === "all" ? events : events.filter((e) => e.kind === filter),
    [events, filter],
  );

  const selected = useMemo(
    () => filtered.find((e) => e.id === selectedId) ?? null,
    [filtered, selectedId],
  );

  useEffect(() => {
    if (autoScroll) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [filtered.length, autoScroll]);

  const onScroll = () => {
    const el = listRef.current;
    if (!el) return;
    const distanceFromBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight;
    setAutoScroll(distanceFromBottom < 60);
  };

  if (!open) return null;

  return (
    <aside
      className="w-[720px] shrink-0 border-l border-[var(--color-grid)] bg-[var(--color-panel)] flex flex-col"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      <div className="px-3 py-2 border-b border-[var(--color-grid)] flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--color-mute)]">
            inspector
          </div>
          <div className="text-[11px] text-[var(--color-ink-2)] mt-0.5 tabular-nums">
            {events.length} events · {totalChunks} chunks
          </div>
        </div>
        <div className="flex gap-1.5">
          <button onClick={clearInspector} title="Clear log">
            clear
          </button>
          <button onClick={onClose} title="Hide inspector">
            close
          </button>
        </div>
      </div>

      <div className="px-2 py-1.5 border-b border-[var(--color-grid)] flex flex-wrap gap-1 text-[10px]">
        {(
          [
            "all",
            "session",
            "turn_meta",
            "update",
            "delegation",
            "tool_call",
            "tool_result",
            "chunk",
            "complete",
            "error",
          ] as const
        ).map((k) => (
          <button
            key={k}
            onClick={() => {
              setFilter(k);
              setSelectedId(null);
            }}
            className={`px-1.5 py-0.5 ${
              filter === k
                ? "text-[var(--color-paper)]"
                : "text-[var(--color-ink-2)]"
            }`}
            style={{
              background:
                filter === k ? "var(--color-signal)" : "transparent",
              borderColor:
                filter === k ? "var(--color-signal)" : "var(--color-grid)",
            }}
          >
            {k}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 flex">
        <div
          ref={listRef}
          onScroll={onScroll}
          className="flex-1 overflow-y-auto border-r border-[var(--color-grid)]"
        >
          {filtered.length === 0 ? (
            <div className="text-[11px] text-[var(--color-mute)] px-4 py-6 text-center">
              no events yet · send a message to see the SSE stream
            </div>
          ) : (
            <ul className="divide-y divide-[var(--color-grid)]">
              {filtered.map((e) => (
                <Row
                  key={e.id}
                  event={e}
                  selected={e.id === selectedId}
                  onSelect={() => setSelectedId(e.id)}
                />
              ))}
              <div ref={endRef} />
            </ul>
          )}
        </div>
        <DetailPanel event={selected} onClose={() => setSelectedId(null)} />
      </div>

      <div className="px-3 py-1.5 border-t border-[var(--color-grid)] text-[10px] uppercase tracking-[0.14em] text-[var(--color-mute)] flex items-center justify-between">
        <span>{autoScroll ? "following" : "paused · scroll to bottom"}</span>
        <button
          onClick={() => {
            setAutoScroll(true);
            endRef.current?.scrollIntoView({ behavior: "smooth" });
          }}
        >
          jump to latest
        </button>
      </div>
    </aside>
  );
}

function Row({
  event,
  selected,
  onSelect,
}: {
  event: LogEvent;
  selected: boolean;
  onSelect: () => void;
}) {
  const t = new Date(event.at);
  const time = `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}.${pad3(t.getMilliseconds())}`;
  return (
    <li
      onClick={onSelect}
      className={`px-3 py-1.5 text-[11px] cursor-pointer flex items-start gap-2 ${
        selected
          ? "bg-[var(--color-panel-2)]"
          : "hover:bg-[var(--color-panel-2)]"
      }`}
    >
      <span className="text-[var(--color-mute-2)] tabular-nums shrink-0">
        {time}
      </span>
      <KindChip kind={event.kind} />
      {event.agent && (
        <span className="text-[var(--color-signal-2)] shrink-0">
          {event.agent}
        </span>
      )}
      {event.eventId != null && (
        <span
          className="text-[var(--color-mute-2)] shrink-0 text-[9.5px] tabular-nums"
          title="ADK event id"
        >
          #{event.eventId}
        </span>
      )}
      <span className="text-[var(--color-ink-2)] break-words min-w-0 flex-1">
        {event.detail}
      </span>
      {event.latencyMs != null && (
        <span
          className="text-[var(--color-mute)] shrink-0 text-[9.5px] tabular-nums"
          title="Latency from run start"
        >
          +{event.latencyMs}ms
        </span>
      )}
    </li>
  );
}

function DetailPanel({
  event,
  onClose,
}: {
  event: LogEvent | null;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);
  if (!event) {
    return (
      <div className="w-[300px] shrink-0 flex items-center justify-center text-[11px] text-[var(--color-mute)] p-4 text-center">
        click an event to inspect its payload
      </div>
    );
  }
  const t = new Date(event.at);
  const iso = t.toISOString();
  const json =
    event.raw !== undefined ? JSON.stringify(event.raw, null, 2) : "";
  return (
    <div className="w-[300px] shrink-0 flex flex-col">
      <div className="px-3 py-1.5 border-b border-[var(--color-grid)] flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.14em] text-[var(--color-mute)]">
          event
        </div>
        <button onClick={onClose} title="Close detail">
          ×
        </button>
      </div>
      <div className="px-3 py-2 text-[11px] space-y-1 border-b border-[var(--color-grid)]">
        <Row2 k="kind" v={event.kind} />
        <Row2 k="time" v={iso} />
        <Row2 k="msg id" v={event.messageId.slice(0, 12) + "…"} />
        {event.eventId != null && (
          <Row2 k="event id" v={`#${event.eventId}`} />
        )}
        {event.author && <Row2 k="author" v={event.author} />}
        {event.model && <Row2 k="model" v={event.model} />}
        {event.agent && <Row2 k="agent" v={event.agent} />}
        {event.toolName && <Row2 k="tool" v={event.toolName} />}
        {event.toolCallId != null && (
          <Row2 k="tool id" v={`#${event.toolCallId}`} />
        )}
        {event.latencyMs != null && (
          <Row2 k="latency" v={`+${event.latencyMs}ms`} />
        )}
        {event.finishReason && <Row2 k="finish" v={event.finishReason} />}
        {event.textLen != null && (
          <Row2 k="text len" v={`${event.textLen} chars`} />
        )}
        <Row2 k="detail" v={event.detail} />
        {event.toolResultSummary && (
          <Row2 k="result" v={event.toolResultSummary.slice(0, 200)} />
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-auto p-2 space-y-2">
        {event.toolArgs && Object.keys(event.toolArgs).length > 0 && (
          <div>
            <div className="text-[9.5px] uppercase tracking-[0.14em] text-[var(--color-mute)] mb-1">
              tool args
            </div>
            <pre className="text-[10.5px] leading-snug p-2 bg-[var(--color-paper)] border border-[var(--color-grid)] overflow-x-auto whitespace-pre-wrap break-words">
              {JSON.stringify(event.toolArgs, null, 2)}
            </pre>
          </div>
        )}
        {json ? (
          <pre className="text-[10.5px] leading-snug p-2 bg-[var(--color-paper)] border border-[var(--color-grid)] overflow-x-auto whitespace-pre-wrap break-words">
            {json}
          </pre>
        ) : (
          <div className="text-[10.5px] text-[var(--color-mute)] p-2 text-center">
            no raw payload
          </div>
        )}
      </div>
      <div className="px-2 py-1.5 border-t border-[var(--color-grid)] flex items-center justify-between">
        <button
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(
                json || JSON.stringify(event, null, 2),
              );
              setCopied(true);
              setTimeout(() => setCopied(false), 1200);
            } catch {
              /* ignore */
            }
          }}
        >
          {copied ? "copied!" : "copy json"}
        </button>
        <button
          onClick={() => {
            const el = document.querySelector(
              `[data-msg-id="${event.messageId}"]`,
            );
            if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
          }}
          title="Scroll the message bubble into view"
        >
          jump to message
        </button>
      </div>
    </div>
  );
}

function Row2({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-[var(--color-mute)] shrink-0 w-14 uppercase tracking-wider text-[9.5px] pt-px">
        {k}
      </span>
      <span className="text-[var(--color-ink-2)] break-words min-w-0 flex-1">
        {v}
      </span>
    </div>
  );
}

function KindChip({ kind }: { kind: EventKind }) {
  const color =
    kind === "error"
      ? "var(--color-err)"
      : kind === "delegation"
        ? "var(--color-signal)"
        : kind === "complete"
          ? "var(--color-ok)"
          : kind === "chunk"
            ? "var(--color-ink-2)"
            : "var(--color-mute)";
  return (
    <span
      className="px-1 py-px text-[9px] uppercase tracking-[0.14em] shrink-0"
      style={{ color, border: `1px solid ${color}` }}
    >
      {kind}
    </span>
  );
}

function pad(n: number) {
  return n.toString().padStart(2, "0");
}
function pad3(n: number) {
  return n.toString().padStart(3, "0");
}

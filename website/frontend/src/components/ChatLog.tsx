import { useEffect, useMemo, useRef, useState } from "react";
import { useChat } from "../store";
import type { AgentMessage, MessageState } from "../types";

/**
 * Conversation log — logbook format.
 *
 * Each message reads like a lab-notebook entry: a left gutter with
 * monospaced metadata (turn index, role tag, timing, model, agent
 * state, live token count), and a right column for the actual content.
 * Delegations render as an inline signal-trace row that animates while
 * the sub-agent is in flight, then settles to a finished "trace" once
 * the tool result returns.
 */
export function ChatLog() {
  const { messages, sending, send, sessionId } = useChat();
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const exportTranscript = () => {
    const lines: string[] = [];
    lines.push(`# TriAgent session ${sessionId}`);
    lines.push("");
    lines.push(`Exported ${new Date().toISOString()}`);
    lines.push("");
    for (const m of messages) {
      const t = new Date(m.createdAt).toISOString();
      const who = m.role === "user" ? "User" : "Host Agent";
      lines.push(`## ${who}  (${t})`);
      if (m.role === "agent") {
        if (m.chunks) lines.push(`*${m.chunks} chunks, state=${m.state}*`);
        if (m.delegation && m.delegation.length) {
          lines.push("");
          lines.push("**Delegations:**");
          for (const d of m.delegation) {
            lines.push(`- ${d.agent}: ${d.detail}`);
          }
        }
        if (m.updates.length) {
          lines.push("");
          lines.push("**Updates:**");
          for (const u of m.updates) lines.push(`- ${u}`);
        }
      }
      lines.push("");
      lines.push(m.content || "_(empty)_");
      lines.push("");
      lines.push("---");
      lines.push("");
    }
    const blob = new Blob([lines.join("\n")], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `triagent-${sessionId.slice(0, 8)}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center px-6 text-center">
        <div className="max-w-md">
          <div
            className="text-[10px] uppercase tracking-[0.3em] text-[var(--color-signal)] mb-3"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            // standby
          </div>
          <div
            className="text-2xl mb-2 text-[var(--color-ink)]"
            style={{ fontFamily: "var(--font-display)", letterSpacing: "-0.02em" }}
          >
            Console is listening.
          </div>
          <div className="text-[13px] text-[var(--color-ink-2)]">
            Send a query. The host will route to Gmail, Calendar, or Tasks
            sub-agents and stream the result back. Every event, delegation,
            and tool call is recorded for inspection.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto px-6 py-6">
        <div className="flex items-center justify-end mb-3">
          <button onClick={exportTranscript} title="Download the whole conversation as markdown">
            export transcript.md
          </button>
        </div>
        <ol className="flex flex-col gap-0">
          {messages.map((m, i) => (
            <Entry
              key={m.id}
              message={m}
              index={i}
              onResend={m.role === "user" ? send : undefined}
            />
          ))}
        </ol>
        <div ref={endRef} />
      </div>
    </div>
  );
}

function Entry({
  message,
  index,
  onResend,
}: {
  message: AgentMessage;
  index: number;
  onResend?: (q: string) => Promise<void>;
}) {
  return (
    <li
      data-msg-id={message.id}
      className="group border-b border-[var(--color-grid)]"
    >
      <div className="grid grid-cols-[88px_1fr] gap-4 py-4">
        <EntryGutter message={message} index={index} />
        <div className="min-w-0">
          <EntryHeader message={message} />
          <EntryBody message={message} onResend={onResend} />
        </div>
      </div>
    </li>
  );
}

function EntryGutter({
  message,
  index,
}: {
  message: AgentMessage;
  index: number;
}) {
  const turn = (index + 1).toString().padStart(3, "0");
  const ts = new Date(message.createdAt);
  const stamp = `${pad(ts.getHours())}:${pad(ts.getMinutes())}:${pad(ts.getSeconds())}`;
  const isUser = message.role === "user";
  return (
    <div
      className="text-[10px] uppercase tracking-[0.14em] text-[var(--color-mute)] select-none"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      <div className="text-[var(--color-ink-2)] tabular-nums">TURN {turn}</div>
      <div
        className={`mt-1 inline-block px-1 py-px ${
          isUser ? "text-[var(--color-ink)]" : "text-[var(--color-signal)]"
        }`}
        style={{
          borderTop: `1px solid ${isUser ? "var(--color-grid-2)" : "var(--color-signal)"}`,
        }}
      >
        {isUser ? "user" : "host"}
      </div>
      <div className="mt-1 tabular-nums text-[var(--color-mute-2)]">{stamp}</div>
    </div>
  );
}

function EntryHeader({ message }: { message: AgentMessage }) {
  if (message.role === "user") return null;
  const toolCount = message.toolCalls?.length ?? 0;
  const distinctAgents = Array.from(
    new Set(
      (message.toolCalls ?? []).map((t) => t.agent).filter(Boolean) as string[],
    ),
  );
  return (
    <div
      className="mb-2 flex items-center gap-2 flex-wrap text-[10.5px] uppercase tracking-[0.08em]"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      <span className="text-[var(--color-ink)] font-semibold">
        {message.agentName ?? "Host_Agent"}
      </span>
      <StateChip state={message.state} />
      {message.model && (
        <span
          className="text-[var(--color-signal-2)] normal-case tracking-normal"
          title="Host LLM model"
        >
          {message.model}
        </span>
      )}
      {message.chunks > 0 && (
        <span className="text-[var(--color-ink-2)] tabular-nums">
          {message.chunks}ch
        </span>
      )}
      {toolCount > 0 && (
        <span
          className="text-[var(--color-signal-2)] tabular-nums"
          title={`${toolCount} tool call${toolCount === 1 ? "" : "s"}`}
        >
          {toolCount}tool
        </span>
      )}
      {message.ttfbMs != null && message.state === "done" && (
        <span
          className="text-[var(--color-ink-2)] tabular-nums"
          title="Time to first content chunk"
        >
          ttfb {message.ttfbMs}ms
        </span>
      )}
      {message.firstChunkAt && message.completedAt && message.state === "done" && (
        <span className="text-[var(--color-ink-2)] tabular-nums">
          {(message.completedAt - message.firstChunkAt)}ms stream
        </span>
      )}
      {message.streaming && message.firstChunkAt && (
        <span className="text-[var(--color-signal)] tabular-nums">
          {Date.now() - message.firstChunkAt}ms live
        </span>
      )}
      {message.state === "done" && message.tokenEstimate != undefined && (
        <span
          className="text-[var(--color-ink-2)] tabular-nums"
          title="Approx token estimate (chars / 4)"
        >
          ~{message.tokenEstimate}tok
        </span>
      )}
      {message.finishReason && (
        <span
          className="text-[var(--color-ok)] tabular-nums"
          title="Gemini finish reason"
        >
          finish:{message.finishReason}
        </span>
      )}
      {distinctAgents.length > 0 && (
        <span
          className="text-[var(--color-mute)] normal-case tracking-normal"
          title="Sub-agents used this turn"
        >
          via:{distinctAgents.join(",")}
        </span>
      )}
    </div>
  );
}

function EntryBody({
  message,
  onResend,
}: {
  message: AgentMessage;
  onResend?: (q: string) => Promise<void>;
}) {
  const isUser = message.role === "user";
  const showTimeline =
    !isUser &&
    (message.updates.length > 0 ||
      (message.delegation?.length ?? 0) > 0 ||
      (message.toolCalls?.length ?? 0) > 0);
  const empty = !message.content && message.streaming;

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);
  useEffect(() => {
    if (!editing) setDraft(message.content);
  }, [message.content, editing]);

  const onSaveEdit = async () => {
    const v = draft.trim();
    setEditing(false);
    if (!v || !onResend) return;
    if (v === message.content) return;
    await onResend(v);
  };

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="min-w-0">
      {showTimeline && <TracePane message={message} />}
      {isUser ? (
        editing ? (
          <div className="flex flex-col gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={Math.max(2, Math.min(8, draft.split("\n").length))}
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => {
                  setEditing(false);
                  setDraft(message.content);
                }}
              >
                cancel
              </button>
              <button
                onClick={onSaveEdit}
                disabled={!draft.trim() || draft === message.content}
              >
                save &amp; resend
              </button>
            </div>
          </div>
        ) : (
          <div
            className="text-[14px] text-[var(--color-ink)] leading-relaxed whitespace-pre-wrap"
            style={{ fontFamily: "var(--font-body)" }}
          >
            {message.content}
          </div>
        )
      ) : (
        <MarkdownContent
          text={message.content}
          streaming={message.streaming}
          empty={empty}
        />
      )}
      <BubbleActions
        isUser={isUser}
        hasContent={!!message.content}
        onCopy={onCopy}
        onEdit={isUser && onResend ? () => setEditing(true) : undefined}
      />
    </div>
  );
}

function BubbleActions({
  isUser: _isUser,
  hasContent,
  onCopy,
  onEdit,
}: {
  isUser: boolean;
  hasContent: boolean;
  onCopy: () => void;
  onEdit?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <div
      className="mt-2 flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {hasContent && (
        <button
          onClick={() => {
            void onCopy();
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          }}
          title="Copy reply"
        >
          {copied ? "copied" : "copy"}
        </button>
      )}
      {onEdit && (
        <button onClick={onEdit} title="Edit this message and resend">
          edit
        </button>
      )}
    </div>
  );
}

function StateChip({ state }: { state: MessageState }) {
  const map: Record<MessageState, { label: string; color: string }> = {
    working: { label: "working", color: "var(--color-mute)" },
    delegating: { label: "delegating", color: "var(--color-signal)" },
    streaming: { label: "streaming", color: "var(--color-warn)" },
    done: { label: "done", color: "var(--color-ok)" },
    error: { label: "error", color: "var(--color-err)" },
  };
  const { label, color } = map[state];
  return (
    <span
      className="font-mono uppercase"
      style={{
        color,
        border: `1px solid ${color}`,
        padding: "1px 5px",
        fontSize: 9,
        letterSpacing: "0.14em",
      }}
    >
      {label}
    </span>
  );
}

/**
 * The signal-trace pane.
 *
 * Renders every observable step of a turn as a row in a vertical trace:
 * a left-edge timestamp gutter, a node marker, an agent tag, and the
 * detail line. While a delegation is in flight, the row gets an
 * animated hairline drawn under it (the "signal trace") that
 * disappears when the matching tool result comes back.
 */
function TracePane({ message }: { message: AgentMessage }) {
  const start = message.createdAt;
  const liveMs = message.streaming
    ? Math.max(0, Date.now() - start)
    : Math.max(0, (message.completedAt ?? Date.now()) - start);
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!message.streaming) return;
    const id = setInterval(() => setTick((t) => t + 1), 250);
    return () => clearInterval(id);
  }, [message.streaming]);

  type Item = {
    id: string;
    at: number;
    kind: "update" | "delegation" | "tool" | "tool_result" | "stream";
    agent?: string;
    detail: string;
    durationMs?: number;
    inFlight?: boolean;
  };
  const items: Item[] = [];

  let u = 0;
  let d = 0;
  const delegations = message.delegation ?? [];
  while (u < message.updates.length || d < delegations.length) {
    const nextU = message.updates[u]
      ? start + u * 1
      : Number.POSITIVE_INFINITY;
    const nextD = delegations[d] ? delegations[d].at : Number.POSITIVE_INFINITY;
    if (nextU <= nextD) {
      items.push({
        id: `u-${u}`,
        at: start + u,
        kind: "update",
        detail: message.updates[u],
      });
      u++;
    } else {
      items.push({
        id: `d-${d}`,
        at: delegations[d].at,
        kind: "delegation",
        agent: delegations[d].agent,
        detail: delegations[d].detail,
        inFlight: message.streaming,
      });
      d++;
    }
  }
  const tools = message.toolCalls ?? [];
  for (const t of tools) {
    const finished = t.finishedAt != null;
    items.push({
      id: `t-${t.id}`,
      at: t.startedAt,
      kind: "tool",
      agent: t.agent,
      detail: `${t.name}(${Object.keys(t.args).join(", ")})`,
      durationMs: t.durationMs,
      inFlight: !finished && message.streaming,
    });
    if (t.resultSummary) {
      items.push({
        id: `r-${t.id}`,
        at: t.finishedAt ?? t.startedAt,
        kind: "tool_result",
        agent: t.agent,
        detail: `${t.name} → ${t.resultSummary.slice(0, 160)}`,
        durationMs: t.durationMs,
      });
    }
  }
  if (message.chunks > 0) {
    items.push({
      id: "stream",
      at: message.firstChunkAt ?? start,
      kind: "stream",
      detail: `${message.chunks} content chunks`,
    });
  }

  return (
    <div
      className="mb-2.5 border-l border-[var(--color-grid-2)] pl-3"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      <button
        type="button"
        className="w-full flex items-center gap-3 text-[10px] uppercase tracking-[0.14em] text-[var(--color-mute)] py-1"
        onClick={(e) => {
          const details = (e.currentTarget.parentElement?.querySelector(
            "ul",
          ) ?? null) as HTMLUListElement | null;
          if (!details) return;
          details.classList.toggle("hidden");
        }}
      >
        <span className="text-[var(--color-ink-2)]">trace</span>
        <span className="text-[var(--color-mute-2)]">·</span>
        <span className="text-[var(--color-ink-2)] tabular-nums">{liveMs}ms</span>
        <span className="text-[var(--color-mute-2)]">·</span>
        <span className="text-[var(--color-ink-2)] tabular-nums">
          {items.length} step{items.length === 1 ? "" : "s"}
        </span>
      </button>
      <ul className="flex flex-col gap-1 py-1">
        {items.map((it) => (
          <TraceRow key={it.id} item={it} start={start} />
        ))}
      </ul>
    </div>
  );
}

function TraceRow({
  item,
  start,
}: {
  item: {
    at: number;
    kind: "update" | "delegation" | "tool" | "tool_result" | "stream";
    agent?: string;
    detail: string;
    durationMs?: number;
    inFlight?: boolean;
  };
  start: number;
}) {
  const offset = Math.max(0, item.at - start);
  const color =
    item.kind === "delegation" || item.kind === "tool"
      ? "var(--color-signal)"
      : item.kind === "tool_result"
        ? "var(--color-ok)"
        : item.kind === "stream"
          ? "var(--color-warn)"
          : "var(--color-mute)";

  return (
    <li className="relative pl-3">
      <span
        className="absolute left-[-5px] top-1.5 h-1.5 w-1.5"
        style={{
          background: color,
          transform: "rotate(45deg)",
        }}
      />
      <div className="flex items-center gap-2 text-[10.5px] leading-snug">
        <span className="tabular-nums text-[var(--color-mute-2)] w-12 shrink-0">
          {offset}ms
        </span>
        <span
          className="font-mono uppercase"
          style={{
            color,
            border: `1px solid ${color}`,
            fontSize: 9,
            letterSpacing: "0.12em",
            padding: "0 4px",
          }}
        >
          {item.kind.replace("_", " ")}
        </span>
        {item.agent && (
          <span className="text-[var(--color-signal-2)] shrink-0">
            {item.agent}
          </span>
        )}
        <span className="text-[var(--color-ink-2)] min-w-0 flex-1 break-words">
          {item.detail}
        </span>
        {item.durationMs != null && (
          <span
            className="text-[var(--color-mute)] tabular-nums shrink-0"
            title="Tool call duration"
          >
            {item.durationMs}ms
          </span>
        )}
      </div>
      {item.inFlight && (
        <div className="mt-1 h-px relative overflow-hidden">
          <div className="trace-sweep" style={{ width: "40%" }} />
        </div>
      )}
    </li>
  );
}

function MarkdownContent({
  text,
  streaming,
  empty,
}: {
  text: string;
  streaming: boolean;
  empty: boolean;
}) {
  if (empty) {
    return (
      <span
        className="text-[var(--color-mute)] text-sm inline-flex items-center"
        style={{ fontFamily: "var(--font-mono)" }}
      >
        awaiting first byte
        <span className="caret" />
      </span>
    );
  }
  return (
    <div className="markdown text-[13.5px] leading-[1.65]">
      <SafeMarkdown source={text} />
      {streaming && <span className="caret" />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Custom markdown renderer — safe on partial streaming input         */
/* ------------------------------------------------------------------ */

interface Block {
  kind: "h1" | "h2" | "h3" | "p" | "ul" | "ol" | "code" | "table" | "hr";
  text?: string;
  items?: string[];
  lang?: string;
  headers?: string[];
  rows?: string[][];
}

function parseMarkdown(src: string): { blocks: Block[] } {
  const lines = src.split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        body.push(lines[i]);
        i++;
      }
      blocks.push({ kind: "code", text: body.join("\n"), lang });
      if (i < lines.length && lines[i].startsWith("```")) i++;
      continue;
    }

    if (/^\s*---+\s*$/.test(line)) {
      blocks.push({ kind: "hr" });
      i++;
      continue;
    }

    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length as 1 | 2 | 3;
      blocks.push({
        kind: level === 1 ? "h1" : level === 2 ? "h2" : "h3",
        text: h[2],
      });
      i++;
      continue;
    }

    if (
      line.includes("|") &&
      i + 1 < lines.length &&
      /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1])
    ) {
      const headerCells = splitRow(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") {
        rows.push(splitRow(lines[i]));
        i++;
      }
      blocks.push({ kind: "table", headers: headerCells, rows });
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s+/, ""));
        i++;
      }
      blocks.push({ kind: "ul", items });
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i++;
      }
      blocks.push({ kind: "ol", items });
      continue;
    }

    if (line.trim() === "") {
      i++;
      continue;
    }

    const para: string[] = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].startsWith("```") &&
      !/^#{1,3}\s+/.test(lines[i]) &&
      !/^\s*[-*+]\s+/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i]) &&
      !/^\s*---+\s*$/.test(lines[i])
    ) {
      para.push(lines[i]);
      i++;
    }
    blocks.push({ kind: "p", text: para.join("\n") });
  }

  return { blocks };
}

function splitRow(line: string): string[] {
  const trimmed = line.replace(/^\s*\|?/, "").replace(/\|\s*$/, "");
  return trimmed.split("|").map((c) => c.trim());
}

function Inline({ text }: { text: string }) {
  const parts: Array<{
    kind: "text" | "b" | "i" | "code" | "link";
    value: string;
    href?: string;
  }> = [];
  let rest = text;
  const pattern =
    /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(\[[^\]]+\]\([^)]+\))/;
  while (rest.length) {
    const m = pattern.exec(rest);
    if (!m) {
      parts.push({ kind: "text", value: rest });
      break;
    }
    if (m.index > 0) parts.push({ kind: "text", value: rest.slice(0, m.index) });
    const tok = m[0];
    if (tok.startsWith("`")) {
      parts.push({ kind: "code", value: tok.slice(1, -1) });
    } else if (tok.startsWith("**")) {
      parts.push({ kind: "b", value: tok.slice(2, -2) });
    } else if (tok.startsWith("*")) {
      parts.push({ kind: "i", value: tok.slice(1, -1) });
    } else if (tok.startsWith("[")) {
      const lm = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok);
      if (lm) parts.push({ kind: "link", value: lm[1], href: lm[2] });
    }
    rest = rest.slice(m.index + tok.length);
  }
  return (
    <>
      {parts.map((p, i) => {
        if (p.kind === "b") return <strong key={i}>{p.value}</strong>;
        if (p.kind === "i") return <em key={i}>{p.value}</em>;
        if (p.kind === "code") return <code key={i}>{p.value}</code>;
        if (p.kind === "link")
          return (
            <a key={i} href={p.href} target="_blank" rel="noreferrer">
              {p.value}
            </a>
          );
        return <span key={i}>{p.value}</span>;
      })}
    </>
  );
}

function SafeMarkdown({ source }: { source: string }) {
  const { blocks } = useMemo(() => parseMarkdown(source), [source]);
  return (
    <>
      {blocks.map((b, i) => {
        if (b.kind === "h1")
          return (
            <h1 key={i}>
              <Inline text={b.text ?? ""} />
            </h1>
          );
        if (b.kind === "h2")
          return (
            <h2 key={i}>
              <Inline text={b.text ?? ""} />
            </h2>
          );
        if (b.kind === "h3")
          return (
            <h3 key={i}>
              <Inline text={b.text ?? ""} />
            </h3>
          );
        if (b.kind === "p")
          return (
            <p key={i}>
              <Inline text={b.text ?? ""} />
            </p>
          );
        if (b.kind === "ul")
          return (
            <ul key={i}>
              {b.items!.map((it, j) => (
                <li key={j}>
                  <Inline text={it} />
                </li>
              ))}
            </ul>
          );
        if (b.kind === "ol")
          return (
            <ol key={i}>
              {b.items!.map((it, j) => (
                <li key={j}>
                  <Inline text={it} />
                </li>
              ))}
            </ol>
          );
        if (b.kind === "code")
          return (
            <pre key={i}>
              <code>{b.text}</code>
            </pre>
          );
        if (b.kind === "hr") return <hr key={i} />;
        if (b.kind === "table") {
          return (
            <table key={i}>
              <thead>
                <tr>
                  {b.headers!.map((h, j) => (
                    <th key={j}>
                      <Inline text={h} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {b.rows!.map((r, j) => (
                  <tr key={j}>
                    {r.map((c, k) => (
                      <td key={k}>
                        <Inline text={c} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          );
        }
        return null;
      })}
    </>
  );
}

function pad(n: number) {
  return n.toString().padStart(2, "0");
}

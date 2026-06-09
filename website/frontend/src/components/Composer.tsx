import { useRef, useState, type KeyboardEvent } from "react";
import { useChat } from "../store";

/**
 * Composer — terminal-style input row.
 *
 * Reads as a command prompt at the bottom of the console: a `>` glyph
 * on the left, the input in monospace, and a small submit button. The
 * caret turns into the live signal color while a stream is in flight,
 * which mirrors the trace sweep on the status bar.
 */
export function Composer() {
  const { send, sending } = useChat();
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement | null>(null);

  const onSubmit = () => {
    if (!value.trim() || sending) return;
    const v = value;
    setValue("");
    void send(v);
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div
      className="border-t border-[var(--color-grid)] bg-[var(--color-panel)]"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      <div className="max-w-3xl mx-auto px-6 py-3 flex items-end gap-3">
        <div className="flex-1 flex items-end gap-2 border border-[var(--color-grid)] bg-[var(--color-panel-2)] focus-within:border-[var(--color-signal)]">
          <span
            aria-hidden
            className={`pl-3 pb-2 text-[14px] select-none ${
              sending ? "text-[var(--color-signal)]" : "text-[var(--color-mute)]"
            }`}
          >
            &gt;
          </span>
          <textarea
            ref={ref}
            rows={1}
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = Math.min(el.scrollHeight, 160) + "px";
            }}
            onKeyDown={onKey}
            placeholder={
              sending ? "transmitting…" : "ask the host · enter to send · shift+enter newline"
            }
            className="flex-1 resize-none border-0 bg-transparent px-0 py-2 text-[13px]"
            style={{ border: "none", outline: "none" }}
            disabled={sending}
          />
        </div>
        <button
          onClick={onSubmit}
          disabled={sending || !value.trim()}
          className="px-3 py-2"
          style={{
            background: sending ? "transparent" : "var(--color-signal)",
            borderColor: sending ? "var(--color-signal)" : "var(--color-signal)",
            color: sending ? "var(--color-signal)" : "var(--color-paper)",
            minWidth: 88,
            fontWeight: 600,
            letterSpacing: "0.08em",
          }}
        >
          {sending ? "sending" : "transmit"}
        </button>
      </div>
    </div>
  );
}

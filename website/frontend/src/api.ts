import type { SessionInfo, SubAgent, StreamChunk } from "./types";

const API_BASE = "";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API_BASE + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function fetchAgents(): Promise<SubAgent[]> {
  return jsonFetch<SubAgent[]>("/api/agents");
}

export async function fetchHealth(): Promise<{ bff: boolean; sub_agents: SubAgentHealthLite[] }> {
  return jsonFetch<{ bff: boolean; sub_agents: SubAgentHealthLite[] }>("/api/health");
}

export interface SubAgentHealthLite {
  url: string;
  ok: boolean;
  status?: number;
  error?: string;
  latency_ms?: number;
}

export async function fetchSessionInfo(sessionId: string): Promise<SessionInfo> {
  return jsonFetch<SessionInfo>(`/api/session/${encodeURIComponent(sessionId)}`);
}

/**
 * Consume the SSE stream from /api/chat/stream. POST so the query can be in
 * the body. Uses fetch + ReadableStream since the browser's native EventSource
 * is GET-only and cannot post a body.
 */
export async function streamChat(
  query: string,
  sessionId: string,
  onChunk: (chunk: StreamChunk) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ query, session_id: sessionId }),
    signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`Stream failed: ${res.status} ${res.statusText}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sepIndex: number;
    while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);
      const dataLine = rawEvent
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trim())
        .join("\n");
      if (!dataLine) continue;
      try {
        const parsed = JSON.parse(dataLine) as StreamChunk;
        onChunk(parsed);
      } catch {
        // ignore malformed lines
      }
    }
  }
}

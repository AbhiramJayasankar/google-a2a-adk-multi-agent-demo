export type Role = "user" | "agent" | "system";

/** Kinds of structured event the BFF can emit. */
export type EventKind =
  | "session"      // session start / reset
  | "turn_meta"    // per-turn host metadata (model, agent, session id)
  | "update"       // free-form progress note
  | "delegation"   // host called a sub-agent
  | "tool_call"    // host invoked a function/tool (raw args, agent, name)
  | "tool_result"  // function response from a tool (name + summary)
  | "chunk"        // a content delta
  | "complete"     // is_task_complete received (carries latencies, finish_reason, tool_calls)
  | "error";       // stream error

export interface LogEvent {
  id: string;
  /** Owning message id (the agent bubble this event belongs to). */
  messageId: string;
  kind: EventKind;
  /** Sub-agent name for delegation events, else the actor name. */
  agent?: string;
  /** Short summary line for the timeline. */
  detail: string;
  /** Optional raw payload for the inspector drawer. */
  raw?: unknown;
  /** Milliseconds since epoch. */
  at: number;
  /** Stable event id from the BFF (event_seq). Lets the user cross-reference. */
  eventId?: number;
  /** Author of the event as reported by ADK (e.g. "Host_Agent"). */
  author?: string;
  /** Wall-clock latency from run start in ms. */
  latencyMs?: number;
  /** Gemini / LLM finish reason on the final event (e.g. "STOP"). */
  finishReason?: string;
  /** Length of the accumulated reply text at the time of the event. */
  textLen?: number;
  /** Tool call args for tool_call events. */
  toolArgs?: Record<string, unknown>;
  /** Tool name (e.g. "send_message") for tool_call / tool_result events. */
  toolName?: string;
  /** Tool result summary for tool_result events. */
  toolResultSummary?: string;
  /** Tool call id matching tool_call -> tool_result. */
  toolCallId?: number;
  /** Per-turn model name. */
  model?: string;
}

export interface AgentMessage {
  id: string;
  role: Role;
  content: string;
  updates: string[];
  /** True when the streaming response is still in flight. */
  streaming: boolean;
  createdAt: number;
  /** Optional structured delegation summary for the "transparency" pane. */
  delegation?: DelegationEvent[];
  /** Per-message state machine: working | delegating | streaming | done | error. */
  state: MessageState;
  /** Number of content chunks received so far. */
  chunks: number;
  /** First content-chunk timestamp (for "first byte" latency). */
  firstChunkAt?: number;
  /** Final completion timestamp. */
  completedAt?: number;
  /** Host model name (e.g. "gemini-3.1-flash-lite"). */
  model?: string;
  /** Host agent name (e.g. "Host_Agent"). */
  agentName?: string;
  /** Wall-clock latency to first content chunk in ms. */
  ttfbMs?: number;
  /** Total wall-clock latency from open to complete in ms. */
  totalMs?: number;
  /** Gemini finish reason on completion (e.g. "STOP"). */
  finishReason?: string;
  /** Approx token count derived from text length / 4 (rough estimate). */
  tokenEstimate?: number;
  /** Tool calls observed for this turn (from the final completion chunk). */
  toolCalls?: ToolCallRecord[];
}

export interface ToolCallRecord {
  id: number;
  name: string;
  agent?: string;
  task?: string;
  args: Record<string, unknown>;
  startedAt: number;
  finishedAt?: number;
  durationMs?: number;
  resultSummary?: string;
}

export type MessageState =
  | "working"      // stream just opened, no chunks yet
  | "delegating"   // delegation events have arrived
  | "streaming"    // content chunks are flowing
  | "done"         // is_task_complete received
  | "error";       // stream errored out

export interface DelegationEvent {
  agent: string;
  detail: string;
  at: number;
}

export interface SubAgent {
  name: string;
  description: string;
  url?: string;
  version?: string;
  provider?: string;
  skills?: Array<{ id: string; name: string; description: string }>;
  capabilities?: {
    streaming?: boolean;
    push_notifications?: boolean;
    state_transition_history?: boolean;
  };
  defaultInputModes?: string[];
  defaultOutputModes?: string[];
}

export interface StreamChunk {
  is_task_complete: boolean;
  content?: string;
  updates?: string;
  delegation?: DelegationEvent;
  /** Per-turn host metadata (first chunk of every turn). */
  turn_meta?: TurnMeta;
  /** Tool call detail. */
  tool_call?: ToolCallInfo;
  /** Tool result summary. */
  tool_result?: ToolResultInfo;
  /** Stable event id from the host. */
  event_id?: number;
  author?: string;
  ts?: number;
  latency_ms?: number;
  text_len?: number;
  finish_reason?: string;
  tool_calls?: ToolCallRecord[];
}

export interface TurnMeta {
  model: string;
  session_id: string;
  agent: string;
  started_at: number;
}

export interface ToolCallInfo {
  id: number;
  name: string;
  agent?: string;
  args: Record<string, unknown>;
  at: number;
}

export interface ToolResultInfo {
  name: string;
  summary: string;
  at: number;
}

export interface SubAgentHealth {
  url: string;
  ok: boolean;
  status?: number;
  error?: string;
  latencyMs?: number;
  /** Set client-side when this snapshot was taken. */
  seenAt?: number;
}

export interface SessionInfo {
  exists: boolean;
  session_id: string;
  app_name?: string;
  user_id?: string;
  last_update_time?: number;
  events_count?: number;
  state_keys?: string[];
}

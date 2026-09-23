/**
 * RuntimeEvent —— 镜像后端 runtime/events/protocol.py 的判别联合。
 * SSE 线上每条 data 帧都是 { type, ... }，按 type 判别。
 */

export type RiskLevel = "low" | "medium" | "high" | "critical";

export interface Finding {
  /** 维度：logs / machine / security 等 */
  dimension?: string;
  node_name?: string;
  risk_level?: RiskLevel;
  summary?: string;
  /** 关键证据/要点 */
  details?: string[];
  evidence?: Record<string, unknown> | unknown;
  [key: string]: unknown;
}

export interface StatusEvent {
  type: "status";
  node: string;
  message: string;
}

export interface ToolCallEvent {
  type: "tool_call";
  node: string;
  tool_name: string;
  tool_input: unknown;
}

export interface ToolResultEvent {
  type: "tool_result";
  node: string;
  tool_name: string;
  output: unknown;
}

export interface ArtifactEvent {
  type: "artifact";
  artifact_type: string;
  data: unknown;
}

/** 镜像 runtime/artifacts/investigation.py 的 InvestigationArtifact */
export interface InvestigationArtifact {
  artifact_type: "investigation";
  session_id: string;
  target: string;
  findings: Record<string, unknown>;
  asset_findings: Record<string, unknown>;
  report: Record<string, unknown>;
  risk_level: RiskLevel;
  summary: string;
  recommendations: string[];
  created_at: string;
}

export interface FinalEvent {
  type: "final";
  findings: Finding[];
  artifacts: InvestigationArtifact[];
}

export interface ErrorEvent {
  type: "error";
  message: string;
  node: string | null;
}

export interface ApprovalRequestEvent {
  type: "approval_request";
  session_id: string;
  findings: Finding[];
}

export interface ApprovalDecisionEvent {
  type: "approval_decision";
  session_id: string;
  approved: boolean;
  approver: string;
}

export interface DoneEvent {
  type: "done";
}

export type RuntimeEvent =
  | StatusEvent
  | ToolCallEvent
  | ToolResultEvent
  | ArtifactEvent
  | FinalEvent
  | ErrorEvent
  | ApprovalRequestEvent
  | ApprovalDecisionEvent
  | DoneEvent;

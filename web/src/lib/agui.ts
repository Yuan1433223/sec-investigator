/**
 * AG-UI adapter layer — maps SSE RuntimeEvent frames to AG-UI semantic events.
 *
 * This is a frontend-only mapping; backend SSE contract is unchanged.
 * Minimal usable mapping: RUN_STARTED / STEP_STARTED / TOOL_CALL_START·END /
 * STATE_SNAPSHOT.
 */
import type { ApprovalRequestEvent, FinalEvent, FindingsMap, RuntimeEvent } from "../types";

export type AGUIEvent =
  | { type: "RUN_STARTED"; runId: string }
  | { type: "STEP_STARTED"; stepId: string; message: string }
  | { type: "TOOL_CALL_START"; stepId: string; callId?: string; toolName: string; input: Record<string, unknown> | undefined }
  | { type: "TOOL_CALL_END"; stepId: string; callId?: string; toolName: string; output: unknown }
  | { type: "APPROVAL_DECISION"; approved: boolean }
  | { type: "RUN_FINISHED" }
  | { type: "STATE_SNAPSHOT"; findings: FindingsMap; finalReport?: FinalEvent; approvalReq?: ApprovalRequestEvent }
  | { type: "ERROR"; message: string };

export function mapToAGUI(ev: RuntimeEvent, _runId: string): AGUIEvent | null {
  switch (ev.type) {
    case "status":
      return { type: "STEP_STARTED", stepId: ev.node, message: ev.message };
    case "tool_call":
      return { type: "TOOL_CALL_START", stepId: ev.node, callId: ev.call_id ?? undefined, toolName: ev.tool_name, input: ev.tool_input };
    case "tool_result":
      return { type: "TOOL_CALL_END", stepId: ev.node, callId: ev.call_id ?? undefined, toolName: ev.tool_name, output: ev.output };
    case "approval_decision":
      return { type: "APPROVAL_DECISION", approved: ev.approved };
    case "done":
      return { type: "RUN_FINISHED" };
    case "final":
      return { type: "STATE_SNAPSHOT", findings: ev.findings, finalReport: ev };
    case "approval_request":
      return { type: "STATE_SNAPSHOT", findings: ev.findings, approvalReq: ev };
    case "error":
      return { type: "ERROR", message: ev.message };
    default:
      return null;
  }
}

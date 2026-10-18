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
  | { type: "TOOL_CALL_START"; stepId: string; toolName: string; input: Record<string, unknown> | undefined }
  | { type: "TOOL_CALL_END"; toolName: string; output: unknown }
  | { type: "STATE_SNAPSHOT"; findings: FindingsMap; finalReport?: FinalEvent; approvalReq?: ApprovalRequestEvent }
  | { type: "ERROR"; message: string };

export function mapToAGUI(ev: RuntimeEvent, _runId: string): AGUIEvent | null {
  switch (ev.type) {
    case "status":
      return { type: "STEP_STARTED", stepId: ev.node, message: ev.message };
    case "tool_call":
      return { type: "TOOL_CALL_START", stepId: ev.node, toolName: ev.tool_name, input: ev.tool_input };
    case "tool_result":
      return { type: "TOOL_CALL_END", toolName: ev.tool_name, output: ev.output };
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

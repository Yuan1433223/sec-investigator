import { useCallback, useRef, useState } from "react";
import { newSessionId, resumeInvestigation, startInvestigation } from "../api";
import type {
  ApprovalRequestEvent,
  FindingsMap,
  FinalEvent,
  RuntimeEvent,
} from "../types";

export type Phase = "idle" | "running" | "waiting_approval" | "done" | "error";

export interface LogEntry {
  id: number;
  kind: "status" | "tool" | "error";
  node: string;
  message: string;
  tool?: string;
}

export function useInvestigation() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [sessionId, setSessionId] = useState("");
  const [target, setTarget] = useState("");
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [approvalReq, setApprovalReq] = useState<ApprovalRequestEvent | null>(
    null,
  );
  const [findings, setFindings] = useState<FindingsMap>({});
  const [finalReport, setFinalReport] = useState<FinalEvent | null>(null);
  const [error, setError] = useState<string | null>(null);

  const seq = useRef(0);
  const waitingRef = useRef(false);
  const decidingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  const addEntry = useCallback(
    (e: Omit<LogEntry, "id">) => {
      seq.current += 1;
      setEntries((prev) => [...prev, { ...e, id: seq.current }]);
    },
    [],
  );

  const handleEvent = useCallback(
    (ev: RuntimeEvent) => {
      switch (ev.type) {
        case "status":
          setActiveNode(ev.node);
          addEntry({ kind: "status", node: ev.node, message: ev.message });
          break;
        case "tool_call":
          addEntry({
            kind: "tool",
            node: ev.node,
            tool: ev.tool_name,
            message: "调用工具",
          });
          break;
        case "final":
          setFinalReport(ev);
          setFindings(ev.findings);
          setActiveNode(null);
          if (!waitingRef.current) setPhase("done");
          break;
        case "approval_request":
          setApprovalReq(ev);
          setFindings(ev.findings);
          waitingRef.current = true;
          setPhase("waiting_approval");
          break;
        case "error":
          setError(ev.message);
          setPhase("error");
          break;
        case "done":
          if (!waitingRef.current && phase !== "error") {
            setActiveNode(null);
            setPhase((p) => (p === "running" ? "done" : p));
          }
          break;
        default:
          break;
      }
    },
    [addEntry, phase],
  );

  const start = useCallback(
    async (t: string) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      const sid = newSessionId();
      setSessionId(sid);
      setTarget(t);
      setEntries([]);
      setApprovalReq(null);
      setFindings({});
      setFinalReport(null);
      setError(null);
      waitingRef.current = false;
      setActiveNode("asset_resolution");
      setPhase("running");
      try {
        await startInvestigation(
          { target: t, session_id: sid },
          handleEvent,
          ctrl.signal,
        );
      } catch (err) {
        if ((err as Error).name === "AbortError") return;
        setError((err as Error).message);
        setPhase("error");
      }
    },
    [handleEvent],
  );

  const decide = useCallback(
    async (approved: boolean) => {
      if (!approvalReq || decidingRef.current) return;
      decidingRef.current = true;
      const decision = approved ? "审批通过，继续生成报告" : "审批拒绝，终止调查";
      addEntry({ kind: "status", node: "approval_gate", message: decision });
      // 立即关闭审批弹窗，进入"调查中"；resume 流随后驱动剩余事件
      setApprovalReq(null);
      waitingRef.current = false;
      setPhase("running");
      try {
        await resumeInvestigation(
          { session_id: sessionId, approved, approver: "值班人员" },
          handleEvent,
        );
      } catch (err) {
        setError((err as Error).message);
        setPhase("error");
      } finally {
        decidingRef.current = false;
      }
    },
    [addEntry, approvalReq, handleEvent, sessionId],
  );

  return {
    phase,
    sessionId,
    target,
    entries,
    activeNode,
    approvalReq,
    findings,
    finalReport,
    error,
    start,
    decide,
  };
}

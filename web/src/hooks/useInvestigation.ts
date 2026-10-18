import { useCallback, useRef, useState } from "react";
import { newSessionId, resumeInvestigation, startInvestigation } from "../api";
import { mapToAGUI } from "../lib/agui";
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
  /** tool input summary for tool cards */
  toolInput?: Record<string, unknown>;
  /** extracted asset label (IP / hostname / domain) */
  asset?: string;
  /** tool call completed */
  done?: boolean;
  /** short summary of tool output */
  outputSummary?: string;
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

  /** Extract a short asset label from tool_input (instance / ips / query_by / value). */
  const extractAsset = (input: Record<string, unknown> | undefined): string | undefined => {
    if (!input) return undefined;
    const ipv4Re = /(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})/;
    const inst = input.instance;
    if (typeof inst === "string" && inst) {
      const m = inst.match(ipv4Re);
      if (m) return m[1];
      const segs = inst.split(":");
      return segs[segs.length - 1] || inst;
    }
    const ips = input.ips;
    if (Array.isArray(ips) && ips.length > 0) return String(ips[0]);
    const qb = input.query_by ?? input.value;
    if (typeof qb === "string" && qb) return qb;
    return undefined;
  };

  /** Find the most recent matching tool_call entry to mark done. */
  const markToolDone = (_node: string, toolName: string, output: unknown) => {
    setEntries((prev) => {
      // Find last matching tool entry that isn't done yet
      for (let i = prev.length - 1; i >= 0; i--) {
        const e = prev[i];
        if (e.kind === "tool" && e.tool === toolName && !e.done) {
          const updated = [...prev];
          updated[i] = { ...e, done: true, outputSummary: summarizeOutput(output) };
          return updated;
        }
      }
      return prev;
    });
  };

  const summarizeOutput = (out: unknown): string => {
    if (out == null) return "";
    try {
      const s = typeof out === "string" ? out : JSON.stringify(out);
      return s.length > 120 ? s.slice(0, 120) + "…" : s;
    } catch {
      return "";
    }
  };

  const handleEvent = useCallback(
    (ev: RuntimeEvent) => {
      // AG-UI adapter layer: all event dispatch goes through mapped AG-UI types
      const ag = mapToAGUI(ev, sessionId || "run");
      if (!ag) return;
      // eslint-disable-next-line no-console
      console.debug("[AG-UI]", ag.type);

      switch (ag.type) {
        case "STEP_STARTED":
          setActiveNode(ag.stepId ?? null);
          addEntry({ kind: "status", node: ag.stepId ?? "unknown", message: ag.message ?? "" });
          break;
        case "TOOL_CALL_START":
          addEntry({
            kind: "tool",
            node: ag.stepId ?? "unknown",
            tool: ag.toolName ?? "unknown",
            message: "调用工具",
            toolInput: ag.input as Record<string, unknown> | undefined,
            asset: extractAsset(ag.input as Record<string, unknown> | undefined),
            done: false,
          });
          break;
        case "TOOL_CALL_END":
          markToolDone("", ag.toolName ?? "", ag.output);
          break;
        case "STATE_SNAPSHOT":
          if (ag.findings) setFindings(ag.findings);
          if (ag.finalReport) {
            setFinalReport(ag.finalReport);
            setActiveNode(null);
            if (!waitingRef.current) setPhase("done");
          }
          if (ag.approvalReq) {
            setApprovalReq(ag.approvalReq);
            waitingRef.current = true;
            setPhase("waiting_approval");
          }
          break;
        case "ERROR":
          setError(ag.message ?? "未知错误");
          setPhase("error");
          break;
        default:
          break;
      }
    },
    [addEntry, sessionId],
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

import { useCallback, useEffect, useRef, useState } from "react";
import { newSessionId, resumeInvestigation, startInvestigation } from "../api";
import { mapToAGUI } from "../lib/agui";
import { completeToolEntry } from "../lib/tool-results";
import type { ApprovalRequestEvent, FindingsMap, FinalEvent, RuntimeEvent } from "../types";

export type Phase = "idle" | "running" | "waiting_approval" | "done" | "rejected" | "error";

export interface LogEntry {
  id: number;
  kind: "status" | "tool" | "error";
  node: string;
  message: string;
  tool?: string;
  toolCallId?: string;
  toolInput?: Record<string, unknown>;
  asset?: string;
  done?: boolean;
  output?: unknown;
}

function extractAsset(input: Record<string, unknown> | undefined): string | undefined {
  if (!input) return undefined;
  if (typeof input.instance === "string" && input.instance) {
    return input.instance.match(/(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})/)?.[1] ?? input.instance;
  }
  if (Array.isArray(input.ips) && input.ips.length) return String(input.ips[0]);
  const value = input.value ?? input.domain ?? input.ip;
  return typeof value === "string" ? value : undefined;
}

export function useInvestigation() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [sessionId, setSessionId] = useState("");
  const [target, setTarget] = useState("");
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [approvalReq, setApprovalReq] = useState<ApprovalRequestEvent | null>(null);
  const [findings, setFindings] = useState<FindingsMap>({});
  const [finalReport, setFinalReport] = useState<FinalEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const activeSessionRef = useRef("");
  const streamGenerationRef = useRef(0);
  const waitingRef = useRef(false);
  const terminalRef = useRef<"done" | "rejected" | "error" | null>(null);
  const decidingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const addEntry = useCallback((entry: Omit<LogEntry, "id">) => {
    const id = ++seq.current;
    setEntries((previous) => [...previous, { ...entry, id }]);
  }, []);

  const fail = useCallback((message: string) => {
    terminalRef.current = "error";
    waitingRef.current = false;
    setApprovalReq(null);
    setError(message);
    setActiveNode(null);
    setPhase("error");
  }, []);

  const handleEvent = useCallback((event: RuntimeEvent) => {
    const mapped = mapToAGUI(event, activeSessionRef.current);
    if (!mapped) return;
    switch (mapped.type) {
      case "STEP_STARTED":
        if (!terminalRef.current) setActiveNode(mapped.stepId);
        addEntry({ kind: "status", node: mapped.stepId, message: mapped.message });
        break;
      case "TOOL_CALL_START":
        addEntry({
          kind: "tool", node: mapped.stepId, tool: mapped.toolName,
          toolCallId: mapped.callId, message: "调用工具", toolInput: mapped.input,
          asset: extractAsset(mapped.input), done: false,
        });
        break;
      case "TOOL_CALL_END":
        setEntries((previous) => completeToolEntry(
          previous, mapped.stepId, mapped.toolName, mapped.output, mapped.callId,
        ));
        break;
      case "STATE_SNAPSHOT":
        setFindings(mapped.findings);
        if (mapped.finalReport) {
          terminalRef.current = "done";
          waitingRef.current = false;
          setFinalReport(mapped.finalReport);
          setActiveNode(null);
          setPhase("done");
        }
        if (mapped.approvalReq) {
          waitingRef.current = true;
          setApprovalReq(mapped.approvalReq);
          setActiveNode("approval_gate");
          setPhase("waiting_approval");
        }
        break;
      case "APPROVAL_DECISION":
        if (!mapped.approved) {
          terminalRef.current = "rejected";
          waitingRef.current = false;
          setApprovalReq(null);
          setActiveNode(null);
          setPhase("rejected");
        }
        break;
      case "RUN_FINISHED":
        if (!waitingRef.current && !terminalRef.current) {
          fail("调查流已结束，但未收到报告或审批结果，请重新开始调查。");
        }
        break;
      case "ERROR":
        fail(mapped.message);
        break;
    }
  }, [addEntry, fail]);

  const start = useCallback(async (value: string) => {
    abortRef.current?.abort();
    const generation = ++streamGenerationRef.current;
    const controller = new AbortController();
    abortRef.current = controller;
    const sid = newSessionId();
    activeSessionRef.current = sid;
    setSessionId(sid);
    setTarget(value);
    setEntries([]);
    setApprovalReq(null);
    setFindings({});
    setFinalReport(null);
    setError(null);
    waitingRef.current = false;
    terminalRef.current = null;
    decidingRef.current = false;
    setActiveNode("asset_resolution");
    setPhase("running");
    try {
      await startInvestigation({ target: value, session_id: sid }, (event) => {
        if (activeSessionRef.current === sid && streamGenerationRef.current === generation) handleEvent(event);
      }, controller.signal);
      if (activeSessionRef.current === sid && streamGenerationRef.current === generation) handleEvent({ type: "done" });
    } catch (cause) {
      if ((cause as Error).name !== "AbortError" && activeSessionRef.current === sid && streamGenerationRef.current === generation) {
        fail((cause as Error).message);
      }
    }
  }, [fail, handleEvent]);

  const decide = useCallback(async (approved: boolean) => {
    if (!approvalReq || decidingRef.current) return;
    const sid = approvalReq.session_id;
    decidingRef.current = true;
    const generation = ++streamGenerationRef.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    addEntry({ kind: "status", node: "approval_gate", message: approved
      ? "审批通过，继续生成报告" : "审批拒绝，终止调查" });
    setApprovalReq(null);
    waitingRef.current = false;
    setPhase("running");
    try {
      await resumeInvestigation({ session_id: sid, approved, approver: "值班人员" }, (event) => {
        if (activeSessionRef.current === sid && streamGenerationRef.current === generation) handleEvent(event);
      }, controller.signal);
      if (activeSessionRef.current === sid && streamGenerationRef.current === generation) handleEvent({ type: "done" });
    } catch (cause) {
      if ((cause as Error).name !== "AbortError" && activeSessionRef.current === sid && streamGenerationRef.current === generation) {
        fail((cause as Error).message);
      }
    } finally {
      if (activeSessionRef.current === sid) decidingRef.current = false;
    }
  }, [addEntry, approvalReq, fail, handleEvent]);

  return { phase, sessionId, target, entries, activeNode, approvalReq,
    findings, finalReport, error, start, decide };
}

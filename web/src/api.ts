import type { RuntimeEvent } from "./types";

export interface StartPayload {
  target: string;
  session_id: string;
  question?: string;
}

export interface ResumePayload {
  session_id: string;
  approved: boolean;
  approver: string;
}

/**
 * 以 POST 方式消费 SSE 流（后端 /investigation/stream 是 POST，原生 EventSource 只支持 GET，
 * 故用 fetch + ReadableStream 手动解析 data: 帧）。
 */
export async function streamInvestigation(
  path: "/investigation/stream" | "/investigation/resume",
  body: StartPayload | ResumePayload,
  onEvent: (ev: RuntimeEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`调查请求失败（HTTP ${resp.status}）`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const dataLine = raw.split("\n").find((l) => l.startsWith("data:"));
        if (!dataLine) continue;
        const payload = dataLine.replace(/^data:\s?/, "").trim();
        if (!payload) continue;
        try {
          onEvent(JSON.parse(payload) as RuntimeEvent);
        } catch {
          /* 忽略无法解析的帧 */
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export function startInvestigation(
  payload: StartPayload,
  onEvent: (ev: RuntimeEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamInvestigation("/investigation/stream", payload, onEvent, signal);
}

export function resumeInvestigation(
  payload: ResumePayload,
  onEvent: (ev: RuntimeEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return streamInvestigation("/investigation/resume", payload, onEvent, signal);
}

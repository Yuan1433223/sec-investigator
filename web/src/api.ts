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
 * 生成会话 id。crypto.randomUUID 仅在安全上下文（HTTPS / localhost）可用，
 * 经局域网 IP（http://192.168.x.x）访问时为非安全上下文会抛错，故改用
 * 非安全上下文亦可用的 crypto.getRandomValues，兜底 Math.random。
 */
export function newSessionId(): string {
  try {
    if (
      typeof crypto !== "undefined" &&
      typeof crypto.getRandomValues === "function"
    ) {
      const b = new Uint8Array(16);
      crypto.getRandomValues(b);
      b[6] = (b[6] & 0x0f) | 0x40; // version 4
      b[8] = (b[8] & 0x3f) | 0x80; // variant
      const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
      return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(
        16,
        20,
      )}-${h.slice(20)}`;
    }
  } catch {
    /* fall through */
  }
  return "sid-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
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

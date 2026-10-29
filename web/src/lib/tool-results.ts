import type { LogEntry } from "../hooks/useInvestigation";

/** Correlate concurrent results by ID; ambiguous legacy events stay unpaired. */
export function completeToolEntry(
  entries: LogEntry[], node: string, toolName: string, output: unknown, callId?: string,
): LogEntry[] {
  const candidates = entries.flatMap((entry, index) => {
    const matches = entry.kind === "tool" && !entry.done && (
      callId ? entry.toolCallId === callId
        : !entry.toolCallId && entry.node === node && entry.tool === toolName
    );
    return matches ? [index] : [];
  });
  if (candidates.length !== 1) return entries;
  const result = [...entries];
  result[candidates[0]] = { ...result[candidates[0]], done: true, output };
  return result;
}

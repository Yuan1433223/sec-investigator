import { useEffect, useRef } from "react";
import type { LogEntry } from "../hooks/useInvestigation";

interface Props {
  entries: LogEntry[];
  running: boolean;
}

export function EventLog({ entries, running }: Props) {
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries.length]);

  if (entries.length === 0) {
    return (
      <div className="log">
        <div className="log-empty">
          {running ? "调查进行中，等待事件…" : "选择目标并开始调查，这里会逐步展示代理的每一步动作。"}
        </div>
      </div>
    );
  }

  return (
    <div className="log" ref={boxRef}>
      {entries.map((e) => (
        <div key={e.id} className={"log-entry kind-" + e.kind}>
          <span className="mark" />
          <span className="node">{e.node}</span>
          {e.kind === "tool" ? (
            <span className="tool-name">{e.message} → {e.tool}</span>
          ) : (
            <span className="msg">{e.message}</span>
          )}
        </div>
      ))}
    </div>
  );
}

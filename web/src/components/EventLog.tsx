import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, ChevronDown } from "lucide-react";
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from "@/components/ui/collapsible";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { LogEntry } from "../hooks/useInvestigation";

interface Props {
  entries: LogEntry[];
  running: boolean;
}

const LANE_MAP: Record<string, { title: string; icon: string; subTrack: boolean }> = {
  log_detective: { title: "日志侦探", icon: "📋", subTrack: false },
  machine_check: { title: "机器检查", icon: "🖥️", subTrack: true },
  security_guard: { title: "安全防护", icon: "🛡️", subTrack: true },
  approval_gate: { title: "审批·报告", icon: "✅", subTrack: false },
  reporter: { title: "审批·报告", icon: "✅", subTrack: false },
  supervisor: { title: "审批·报告", icon: "✅", subTrack: false },
  asset_resolution: { title: "资产解析", icon: "🔍", subTrack: false },
};

const DEFAULT_LANE = { title: "其他", icon: "📎", subTrack: false };

function laneFor(node: string) {
  return LANE_MAP[node] ?? DEFAULT_LANE;
}

/** Tool card as a Collapsible span: collapsed = name only, expanded = JSON details. */
function ToolCard({ e }: { e: LogEntry }) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <div className={`tool-card ${e.done ? "done" : "running"} cursor-pointer`}>
          <span className={`tool-dot ${e.done ? "done" : "running"}`} />
          <span className="tool-name">{e.tool}</span>
          {e.asset && <span className="tool-asset">{e.asset}</span>}
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="tool-details">
          {e.toolInput && (
            <div className="tool-detail-row">
              <span className="tool-detail-label">入参</span>
              <ScrollArea className="h-16">
                <pre className="tool-detail-json">{JSON.stringify(e.toolInput, null, 2)}</pre>
              </ScrollArea>
            </div>
          )}
          {e.output !== undefined && (
            <div className="tool-detail-row">
              <span className="tool-detail-label">输出</span>
              <pre className="tool-detail-json" style={{ maxHeight: 256, overflow: "auto" }}>{typeof e.output === "string" ? e.output : JSON.stringify(e.output, null, 2)}</pre>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function StatusItem({ e }: { e: LogEntry }) {
  return (
    <div className="status-item">
      <span className="status-dot" />
      <span className="status-msg">{e.message}</span>
    </div>
  );
}

export function EventLog({ entries, running }: Props) {
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries.length]);

  const lanes = useMemo(() => {
    const map = new Map<string, { info: typeof DEFAULT_LANE; subTracks: Map<string, LogEntry[]> }>();
    for (const e of entries) {
      const info = laneFor(e.node);
      const key = info.title;
      if (!map.has(key)) map.set(key, { info, subTracks: new Map() });
      const lane = map.get(key)!;
      if (info.subTrack) {
        const assetKey = e.asset || "default";
        if (!lane.subTracks.has(assetKey)) lane.subTracks.set(assetKey, []);
        lane.subTracks.get(assetKey)!.push(e);
      } else {
        if (!lane.subTracks.has("main")) lane.subTracks.set("main", []);
        lane.subTracks.get("main")!.push(e);
      }
    }
    return map;
  }, [entries]);

  if (entries.length === 0) {
    return (
      <div className="lanes">
        <div className="log-empty">
          {running ? "调查进行中，等待事件…" : "选择目标并开始调查，这里会逐步展示代理的每一步动作。"}
        </div>
      </div>
    );
  }

  return (
    <div className="lanes" ref={boxRef}>
      {Array.from(lanes.entries()).map(([laneTitle, lane]) => {
        const subTrackEntries = Array.from(lane.subTracks.entries());
        const toolCount = entries.filter((e) => e.kind === "tool" && laneFor(e.node).title === laneTitle).length;
        const hasRunning = entries.some((e) => e.kind === "tool" && !e.done && laneFor(e.node).title === laneTitle);
        return (
          <Collapsible key={laneTitle} defaultOpen={true}>
            <div className="lane">
              <CollapsibleTrigger asChild>
                <div className="lane-header cursor-pointer">
                  <span className="lane-icon">{lane.info.icon}</span>
                  <span className="lane-title">{laneTitle}</span>
                  <span className="lane-count">
                    {toolCount} 工具{hasRunning ? " · 进行中" : " · 完成"}
                  </span>
                </div>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="lane-body">
                  {lane.info.subTrack && subTrackEntries.length > 1 ? (
                    <div className="asset-tracks">
                      {subTrackEntries.map(([assetKey, trackEntries]) => (
                        <div key={assetKey} className="asset-track">
                          <div className="asset-track-header">
                            <span className="asset-label">{assetKey === "default" ? "通用" : assetKey}</span>
                          </div>
                          <div className="asset-track-body">
                            {trackEntries.map((e) => (
                              <div key={e.id} className={`lane-item kind-${e.kind}`}>
                                {e.kind === "tool" ? <ToolCard e={e} /> : <StatusItem e={e} />}
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    subTrackEntries[0]?.[1].map((e) => (
                      <div key={e.id} className={`lane-item kind-${e.kind}`}>
                        {e.kind === "tool" ? <ToolCard e={e} /> : <StatusItem e={e} />}
                      </div>
                    ))
                  )}
                </div>
              </CollapsibleContent>
            </div>
          </Collapsible>
        );
      })}
    </div>
  );
}

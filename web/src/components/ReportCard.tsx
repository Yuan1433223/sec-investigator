import { Badge } from "@/components/ui/badge";
import type { FinalEvent, RiskLevel } from "../types";

const RISK_LABEL: Record<RiskLevel, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};

const RISK_VARIANT: Record<string, "low" | "medium" | "high" | "critical"> = {
  low: "low",
  medium: "medium",
  high: "high",
  critical: "critical",
};

interface Props {
  report: FinalEvent | null;
}

export function ReportCard({ report }: Props) {
  if (!report || report.artifacts.length === 0) {
    return <div className="p-4 text-xs text-zinc-500">报告将在调查结束后生成。</div>;
  }

  const art = report.artifacts[0];
  const nested = art.report ?? {};
  const summary = (nested.summary as string) ?? art.summary ?? "";
  const rootCause = (nested.root_cause as string) ?? "";
  const recommendations = art.recommendations ?? [];
  const risk = art.risk_level ?? "medium";
  const alertStatus = (nested.alert_status as string) ?? "";

  return (
    <div className="p-4">
      <div className="flex items-center gap-2.5 mb-3">
        <Badge variant={RISK_VARIANT[risk] ?? "default"}>{RISK_LABEL[risk as RiskLevel] ?? risk}风险</Badge>
        <span className="text-sm font-bold text-zinc-100">调查结论</span>
        <span className="font-mono text-[11px] text-zinc-500">{art.target}</span>
      </div>

      {summary ? (
        <div className="mb-3">
          <div className="text-[10px] tracking-wider text-zinc-500 uppercase font-mono mb-1">摘要</div>
          <div className="text-[12.5px] text-zinc-100">{summary}</div>
        </div>
      ) : null}

      {alertStatus ? (
        <div className="mb-3">
          <div className="text-[10px] tracking-wider text-zinc-500 uppercase font-mono mb-1">告警状态</div>
          <div className="text-[12.5px] text-zinc-100">{alertStatus}</div>
        </div>
      ) : null}

      {rootCause ? (
        <div className="mb-3">
          <div className="text-[10px] tracking-wider text-zinc-500 uppercase font-mono mb-1">根因</div>
          <div className="text-[12.5px] text-zinc-100">{rootCause}</div>
        </div>
      ) : null}

      {recommendations.length > 0 ? (
        <div className="mb-3">
          <div className="text-[10px] tracking-wider text-zinc-500 uppercase font-mono mb-1">建议</div>
          <ul className="pl-[18px] text-xs text-zinc-400 space-y-1">
            {recommendations.map((r, i) => (<li key={i}>{r}</li>))}
          </ul>
        </div>
      ) : null}

      <div className="mt-2 font-mono text-[11px] text-zinc-500">session: {art.session_id}</div>
    </div>
  );
}

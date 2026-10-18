import { Badge } from "@/components/ui/badge";
import type { Finding, FindingsMap, RiskLevel } from "../types";

const DIM_LABEL: Record<string, string> = {
  logs: "日志检测",
  machine: "机器检查",
  security: "安全防护",
};

const RISK_LABEL: Record<RiskLevel, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};

const RISK_VARIANT: Record<RiskLevel, "low" | "medium" | "high" | "critical"> = {
  low: "low",
  medium: "medium",
  high: "high",
  critical: "critical",
};

const DETAIL_LABEL: Array<[string, string]> = [
  ["qps_info", "QPS"],
  ["error_rate", "错误率"],
  ["top_errors", "Top 错误"],
  ["trend_comparison", "趋势对比"],
  ["cc_status", "CC 防护"],
  ["ddos_status", "DDoS 清洗"],
  ["protection_status", "防护状态"],
  ["operational_issue_detail", "运维问题"],
  ["system_metrics", "系统指标"],
  ["tcp_status", "TCP 状态"],
  ["health_status", "健康状态"],
  ["connectivity", "连通性"],
];

function detailBullets(f: Finding): string[] {
  const out: string[] = [];
  for (const [k, label] of DETAIL_LABEL) {
    const v = f[k];
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) out.push(`${label}：${v.join("、")}`);
    else if (typeof v === "object") out.push(`${label}：${JSON.stringify(v)}`);
    else out.push(`${label}：${String(v)}`);
  }
  return out;
}

interface Props {
  findings: FindingsMap;
}

export function FindingsPanel({ findings }: Props) {
  const entries = Object.entries(findings);
  if (entries.length === 0) {
    return <div className="p-4 text-xs text-zinc-500">暂无发现，等待调查结果。</div>;
  }

  return (
    <div className="space-y-2.5 p-4">
      {entries.map(([dim, f], i) => {
        const risk = (f.risk_level ?? "low") as RiskLevel;
        const details = detailBullets(f);
        return (
          <div key={i} className="rounded-lg border border-white/10 bg-[#16161a] overflow-hidden">
            <div className="flex items-center justify-between px-3 py-2 bg-[#101013] border-b border-white/10">
              <span className="text-xs font-semibold text-zinc-100">
                {DIM_LABEL[dim] ?? dim}
                {f.node_name && <span className="ml-2 font-mono text-[10px] font-normal text-zinc-500">{f.node_name}</span>}
              </span>
              <Badge variant={RISK_VARIANT[risk]}>{RISK_LABEL[risk] ?? risk}</Badge>
            </div>
            {f.summary ? <div className="text-xs text-zinc-100 px-3 py-2">{f.summary}</div> : null}
            {details.length > 0 ? (
              <ul className="px-3 py-2 pl-6 text-[11.5px] text-zinc-400 space-y-0.5">
                {details.map((d, j) => (<li key={j}>{d}</li>))}
              </ul>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

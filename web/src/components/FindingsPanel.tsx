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

/** 各维度专属字段 → 展示标签（按顺序排布） */
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
    return <div className="card-body"><div className="report-empty">暂无发现，等待调查结果。</div></div>;
  }

  return (
    <div className="card-body">
      {entries.map(([dim, f], i) => {
        const risk = (f.risk_level ?? "low") as RiskLevel;
        const details = detailBullets(f);
        return (
          <div className="finding" key={i}>
            <div className="finding-head">
              <span className="finding-dim">
                <span className="cn">{DIM_LABEL[dim] ?? dim}</span>
                <span className="en">{f.node_name ?? ""}</span>
              </span>
              <span className={`risk-badge risk-${risk}`}>{RISK_LABEL[risk] ?? risk}</span>
            </div>
            {f.summary ? <div className="finding-summary">{f.summary}</div> : null}
            {details.length > 0 ? (
              <ul className="finding-details">
                {details.map((d, j) => (
                  <li key={j}>{d}</li>
                ))}
              </ul>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

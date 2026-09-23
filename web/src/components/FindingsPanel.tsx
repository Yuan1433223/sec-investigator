import type { Finding, RiskLevel } from "../types";

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

interface Props {
  findings: Finding[];
}

export function FindingsPanel({ findings }: Props) {
  if (findings.length === 0) {
    return <div className="card-body"><div className="report-empty">暂无发现，等待调查结果。</div></div>;
  }

  return (
    <div className="card-body">
      {findings.map((f, i) => {
        const risk = (f.risk_level ?? "low") as RiskLevel;
        const dim = f.dimension ?? f.node_name ?? "";
        const details = Array.isArray(f.details) ? (f.details as string[]) : [];
        return (
          <div className="finding" key={i}>
            <div className="finding-head">
              <span className="finding-dim">
                <span className="cn">{DIM_LABEL[dim] ?? dim}</span>
                <span className="en">{f.node_name ?? ""}</span>
              </span>
              <span className={"risk-badge risk-" + risk}>
                {RISK_LABEL[risk] ?? risk}
              </span>
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

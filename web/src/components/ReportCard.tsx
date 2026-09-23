import type { FinalEvent, RiskLevel } from "../types";

const RISK_LABEL: Record<RiskLevel, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};

interface Props {
  report: FinalEvent | null;
}

export function ReportCard({ report }: Props) {
  if (!report || report.artifacts.length === 0) {
    return <div className="card-body"><div className="report-empty">报告将在调查结束后生成。</div></div>;
  }

  const art = report.artifacts[0];
  const nested = art.report ?? {};
  const summary = (nested.summary as string) ?? art.summary ?? "";
  const rootCause = (nested.root_cause as string) ?? "";
  const recommendations = art.recommendations ?? [];
  const risk = art.risk_level ?? "medium";
  const alertStatus = (nested.alert_status as string) ?? "";

  return (
    <div className="card-body">
      <div className="report-headline">
        <span className={`risk-badge risk-${risk}`}>{RISK_LABEL[risk] ?? risk}风险</span>
        <span className="report-title">调查结论</span>
        <span className="report-target">{art.target}</span>
      </div>

      {summary ? (
        <div className="report-section">
          <div className="lbl">摘要</div>
          <div className="val">{summary}</div>
        </div>
      ) : null}

      {alertStatus ? (
        <div className="report-section">
          <div className="lbl">告警状态</div>
          <div className="val">{alertStatus}</div>
        </div>
      ) : null}

      {rootCause ? (
        <div className="report-section">
          <div className="lbl">根因</div>
          <div className="val">{rootCause}</div>
        </div>
      ) : null}

      {recommendations.length > 0 ? (
        <div className="report-section">
          <div className="lbl">建议</div>
          <ul className="report-rec">
            {recommendations.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="runtime-note">session: {art.session_id}</div>
    </div>
  );
}

import type { ApprovalRequestEvent } from "../types";

interface Props {
  request: ApprovalRequestEvent;
  onDecide: (approved: boolean) => void;
}

export function ApprovalDialog({ request, onDecide }: Props) {
  const highRisk = request.findings.some(
    (f) => f.risk_level === "critical" || f.risk_level === "high",
  );

  return (
    <div className="modal-mask">
      <div className="modal" role="dialog" aria-modal="true">
        <div className="modal-head">
          <h3>人工审批</h3>
          <span className="tag">{highRisk ? "高危事件" : "需确认"}</span>
        </div>
        <div className="modal-body">
          <p className="pending">
            调查发现疑似高危事件，已暂停在审批门。请确认是否继续生成最终报告。
          </p>
          <div className="modal-summary">
            {request.findings.map((f, i) => (
              <div key={i} style={{ marginBottom: i < request.findings.length - 1 ? 6 : 0 }}>
                <strong>{f.dimension ?? f.node_name ?? "发现"}</strong>
                {" · 风险 "}
                <em>{f.risk_level ?? "low"}</em>
                {f.summary ? ` — ${f.summary}` : ""}
              </div>
            ))}
          </div>
        </div>
        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={() => onDecide(false)}>
            拒绝
          </button>
          <button type="button" className="btn" onClick={() => onDecide(true)}>
            批准并继续
          </button>
        </div>
      </div>
    </div>
  );
}

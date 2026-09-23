import { useInvestigation, type Phase } from "./hooks/useInvestigation";
import { TargetPicker } from "./components/TargetPicker";
import { PipelineRail } from "./components/PipelineRail";
import { EventLog } from "./components/EventLog";
import { FindingsPanel } from "./components/FindingsPanel";
import { ReportCard } from "./components/ReportCard";
import { ApprovalDialog } from "./components/ApprovalDialog";

const STATUS: Record<Phase, { text: string; cls: string }> = {
  idle: { text: "待开始", cls: "" },
  running: { text: "调查中", cls: "running" },
  waiting_approval: { text: "待审批", cls: "waiting" },
  done: { text: "已完成", cls: "done" },
  error: { text: "出错", cls: "error" },
};

export default function App() {
  const {
    phase,
    target,
    entries,
    activeNode,
    approvalReq,
    findings,
    finalReport,
    error,
    start,
    decide,
  } = useInvestigation();

  const running = phase === "running" || phase === "waiting_approval";
  const st = STATUS[phase];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>安全事件调查代理</h1>
          <span className="sub">sec-investigator · 约束自治调查运行时</span>
        </div>
        <span className={"status-pill " + st.cls}>{st.text}</span>
      </header>

      <div className="card">
        <div className="card-body">
          <TargetPicker onStart={start} disabled={running} />
          {target ? (
            <div className="runtime-note" style={{ marginTop: 12, marginBottom: 0 }}>
              当前目标：{target}
            </div>
          ) : null}
        </div>
      </div>

      <PipelineRail activeNode={activeNode} phase={phase} />

      <div className="main-grid">
        <div className="card">
          <div className="card-head">
            <h2>执行时间线</h2>
            <span className="hint">代理逐步动作</span>
          </div>
          <EventLog entries={entries} running={running} />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
          <div className="card">
            <div className="card-head">
              <h2>分项发现</h2>
              <span className="hint">各维度风险评估</span>
            </div>
            <FindingsPanel findings={findings} />
          </div>

          <div className="card">
            <div className="card-head">
              <h2>最终报告</h2>
              <span className="hint">调查结论与建议</span>
            </div>
            <ReportCard report={finalReport} />
          </div>
        </div>
      </div>

      {error ? (
        <div className="card">
          <div className="card-body">
            <div style={{ color: "var(--risk-high)", fontSize: 13 }}>调查出错：{error}</div>
          </div>
        </div>
      ) : null}

      {approvalReq ? (
        <ApprovalDialog request={approvalReq} onDecide={decide} />
      ) : null}
    </div>
  );
}

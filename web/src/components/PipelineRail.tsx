import type { Phase } from "../hooks/useInvestigation";

const PHASES = [
  { key: "asset", label: "资产解析" },
  { key: "log", label: "日志检测" },
  { key: "machine", label: "机器检查" },
  { key: "security", label: "安全防护" },
  { key: "approval", label: "人工审批" },
  { key: "report", label: "生成报告" },
];

/** 节点名 → 阶段 key */
function nodeToPhase(node: string | null): string {
  if (!node) return "";
  if (node === "asset_resolution") return "asset";
  if (node === "log_detective") return "log";
  if (node.startsWith("machine") || node.includes("machine")) return "machine";
  if (node.includes("security") || node.includes("security_guard")) {
    return "security";
  }
  if (node.includes("approval")) return "approval";
  if (node === "reporter") return "report";
  return "";
}

interface Props {
  activeNode: string | null;
  phase: Phase;
}

export function PipelineRail({ activeNode, phase }: Props) {
  const current = nodeToPhase(activeNode);
  const doneUpTo = phase === "done" ? PHASES.length - 1 : PHASES.findIndex((p) => p.key === current);

  return (
    <div className="card">
      <div className="rail">
        {PHASES.map((p, i) => {
          const idx = PHASES.findIndex((x) => x.key === p.key);
          const isActive = phase !== "done" && p.key === current;
          const isDone = phase === "done" || (doneUpTo >= idx && doneUpTo !== -1);
          const state = isActive ? "active" : isDone && phase !== "done" ? "done" : "";
          return (
            <div key={p.key} style={{ display: "contents" }}>
              {i > 0 && <span className="rail-arrow" />}
              <span className={"rail-step " + state}>
                <span className="dot">{isDone ? "✓" : i + 1}</span>
                {p.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

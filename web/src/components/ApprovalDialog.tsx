import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { ApprovalRequestEvent } from "../types";

interface Props {
  request: ApprovalRequestEvent;
  onDecide: (approved: boolean) => void;
}

export function ApprovalDialog({ request, onDecide }: Props) {
  const findings = Object.values(request.findings);
  const highRisk = findings.some(
    (f) => f.risk_level === "critical" || f.risk_level === "high",
  );

  return (
    <Dialog open={true}>
      <DialogContent className="[&>button]:hidden" onEscapeKeyDown={(event) => event.preventDefault()} onInteractOutside={(event) => event.preventDefault()}>
        <DialogHeader>
          <DialogTitle>人工审批</DialogTitle>
          <DialogDescription>请确认继续生成报告，或拒绝并结束本次调查。</DialogDescription>
          {highRisk && <Badge variant="critical">高危事件</Badge>}
        </DialogHeader>
        <div className="text-sm text-zinc-400 space-y-2">
          <p>调查发现疑似高危事件，已暂停在审批门。请确认是否继续生成最终报告。</p>
          <div className="rounded-lg border border-white/10 bg-[#16161a] p-3 text-xs space-y-2">
            {findings.map((f, i) => (
              <div key={i}>
                <strong className="text-zinc-200">{f.dimension ?? f.node_name ?? "发现"}</strong>
                {" · 风险 "}
                <em>{f.risk_level ?? "low"}</em>
                {f.summary ? ` — ${f.summary}` : ""}
              </div>
            ))}
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onDecide(false)}>拒绝</Button>
          <Button onClick={() => onDecide(true)}>批准并继续</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import test from "node:test";
import ts from "typescript";

async function loadSource(path) {
  const source = await readFile(new URL(path, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  });
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);
}
const { completeToolEntry } = await loadSource("../src/lib/tool-results.ts");
const { mapToAGUI } = await loadSource("../src/lib/agui.ts");
const { streamInvestigation } = await loadSource("../src/api.ts");

test("parallel same-name calls keep their own asset results, in either completion order", () => {
  for (const order of [["A", "B"], ["B", "A"]]) {
    let entries = ["A", "B"].map((id) => ({
      kind: "tool", node: "machine_check", tool: "query_instance_status",
      toolCallId: id, asset: id, done: false,
    }));
    for (const id of order) {
      entries = completeToolEntry(entries, "machine_check", "query_instance_status", { asset: id }, id);
    }
    assert.deepEqual(entries.map((entry) => entry.output.asset), ["A", "B"]);
    assert.ok(entries.every((entry) => entry.done));
  }
});

test("unknown IDs and ambiguous legacy results never attach to an unrelated card", () => {
  const entries = Array.from({ length: 2 }, () => ({
    kind: "tool", node: "worker", tool: "same", done: false,
  }));
  assert.equal(completeToolEntry(entries, "worker", "same", 123), entries);
  assert.equal(completeToolEntry(entries, "worker", "same", 123, "missing"), entries);
});

test("expanded evidence retains the complete output", () => {
  const output = "evidence ".repeat(1000);
  const entries = [{ kind: "tool", node: "w", tool: "t", toolCallId: "id", done: false }];
  assert.equal(completeToolEntry(entries, "w", "t", output, "id")[0].output, output);
});

test("approval decisions and stream termination are distinct from final reports", () => {
  assert.deepEqual(mapToAGUI({ type: "approval_decision", approved: false }, "s"),
    { type: "APPROVAL_DECISION", approved: false });
  assert.deepEqual(mapToAGUI({ type: "done" }, "s"), { type: "RUN_FINISHED" });
});

test("SSE handles fragmented UTF-8 and preserves paired call IDs", async () => {
  const events = [
    { type: "tool_call", node: "w", tool_name: "t", call_id: "one", tool_input: {} },
    { type: "tool_result", node: "w", tool_name: "t", call_id: "one", output: "中文观测" },
    { type: "done" },
  ];
  const bytes = new TextEncoder().encode(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(""));
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(controller) {
      for (let i = 0; i < bytes.length; i += 7) controller.enqueue(bytes.slice(i, i + 7));
      controller.close();
    },
  }));
  try {
    const received = [];
    await streamInvestigation("/investigation/stream", {}, (event) => received.push(event));
    assert.deepEqual(received, events);
  } finally { globalThis.fetch = original; }
});

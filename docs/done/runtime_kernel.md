Plan: kks-next Phase 1 — Runtime Kernel
Context
Phase 0 delivered a clean project scaffold. Phase 1 wires the core of kks_runtime: the state schema, event protocol, artifact contracts, LLM profile factory, checkpoint factory, and the first LangGraph investigation graph. No domain logic is implemented yet — this phase establishes the contracts every future phase depends on.

Key decisions informed by donor repo and LangGraph 1.1.9 API exploration:

LangGraph 1.1.9 supports input_schema/output_schema separate from internal state — use this for clean I/O boundaries.
interrupt(value) + Command(resume=value) is the correct HITL pattern in 1.1.9.
Retry policy is a first-class add_node() parameter (retry_policy=RetryPolicy(...)).
Checkpointers are async context managers (AsyncSqliteSaver.from_conn_string()).
Stream mode "custom" allows nodes to push typed events via get_stream_writer().
Files to create
src/kks_runtime/state/session.py
Internal state (SessionState), external input (InvestigationInput), external output (InvestigationOutput) as TypedDicts. Key reducer design:

messages — Annotated[list[AnyMessage], add_messages] (LangGraph built-in)
findings — Annotated[dict[str, Any], _merge_dict] (custom deep merge — same pattern as donor's merge_dict reducer)
artifacts — Annotated[list[dict], operator.add] (append-only)
Fields:

SessionState:
  messages, findings, artifacts  ← reducers above
  target: str           ← domain/IP under investigation
  session_id: str
  next_node: str        ← routing signal from supervisor
  agent_task: str       ← instruction text for chosen worker
  status: Literal["running","completed","failed","waiting_approval"]
  error: str | None

InvestigationInput:
  messages: list[AnyMessage]
  target: str
  session_id: str

InvestigationOutput:
  messages: list[AnyMessage]
  findings: dict[str, Any]
  artifacts: list[dict]
  status: str
src/kks_runtime/events/protocol.py
Six Pydantic event models + RuntimeEvent union. Used by surface layer to translate LangGraph "custom" stream parts into wire-format SSE.

StatusEvent      type="status"      node, message
ToolCallEvent    type="tool_call"   node, tool_name, tool_input
ToolResultEvent  type="tool_result" node, tool_name, output
ArtifactEvent    type="artifact"    artifact_type, data
FinalEvent       type="final"       findings, artifacts
ErrorEvent       type="error"       message, node=None

RuntimeEvent = Annotated[Union[...all six...], Field(discriminator="type")]
All models extend BaseModel. Use model_json_schema() for wire doc.

src/kks_runtime/artifacts/investigation.py
Two Pydantic artifact models that will be placed into SessionState.artifacts:

InvestigationArtifact:
  artifact_type: Literal["investigation"]
  session_id, target
  findings: dict[str, Any]
  risk_level: Literal["low","medium","high","critical"]
  summary: str
  recommendations: list[str]
  created_at: datetime

ReportArtifact:
  artifact_type: Literal["report"]
  session_id, target
  content: str   ← markdown body
  created_at: datetime
src/kks_runtime/checkpoint/factory.py
Async context manager factory. Reads Settings.env to choose backend:

@asynccontextmanager
async def get_checkpointer(settings: Settings | None = None):
    s = settings or get_settings()
    if s.env == "dev":
        async with AsyncSqliteSaver.from_conn_string(s.sqlite_path) as saver:
            yield saver
    else:
        async with AsyncPostgresSaver.from_conn_string(s.postgres_dsn) as saver:
            await saver.setup()
            yield saver
No module-level singleton. Caller owns the lifecycle.

src/kks_runtime/llm/profiles.py
ModelProfile StrEnum + get_model(profile) factory:

ModelProfile:
  FAST_CLASSIFIER     → "gpt-4o-mini"
  TOOL_REASONER       → "gpt-4o"
  STRUCTURED_EXTRACTOR→ "gpt-4o"
  REPORT_WRITER       → "gpt-4o"
  LONG_CONTEXT_ANALYST→ "gpt-4o"
  LOCAL_OFFLINE_MODEL → "local"

get_model(profile) → ChatOpenAI(model=..., api_key=..., base_url=...)
Uses get_settings() per call — no cached model clients at import time (hard rule 4).

src/kks_runtime/graph/nodes/supervisor.py
Phase 1 stub. Always routes to "reporter". Sets up the pattern for Phase 3 routing:

Returns {"next_node": "reporter", "agent_task": "...", "status": "running"}
No LLM call yet — placeholder for the structured routing logic
src/kks_runtime/graph/nodes/reporter.py
Phase 1 stub. Assembles a minimal InvestigationArtifact from state and appends it:

Reads state["findings"], state["target"], state["session_id"]
Creates InvestigationArtifact(risk_level="low", summary="stub", ...)
Returns {"artifacts": [artifact.model_dump()], "status": "completed"}
Emits ArtifactEvent via get_stream_writer() (demonstrates custom stream path)
src/kks_runtime/graph/investigation.py
build_investigation_graph(checkpointer=None) factory. Returns CompiledStateGraph.

START → supervisor →(conditional)→ reporter → END
                   ↑______loop______↑  (when next_node == "supervisor")
Supervisor node gets retry_policy=RetryPolicy(max_attempts=3) to demonstrate the pattern.

src/kks_runtime/approvals/gate.py
approval_gate(state) node function using interrupt():

async def approval_gate(state: SessionState) -> dict:
    decision = interrupt({
        "type": "approval_request",
        "session_id": state["session_id"],
        "findings": state.get("findings", {}),
    })
    if not decision.get("approved", False):
        return {"status": "failed", "error": "rejected by approver"}
    return {"status": "running"}
Not wired into the main graph yet — exported as a reusable node for Phase 3+ to insert between supervisor and reporter when high-risk findings are detected.

Tests to add
tests/unit/test_state.py

Verify _merge_dict reducer: nested merge, overwrite, empty cases
Verify add_messages behavior via SessionState construction
tests/unit/test_events.py

Round-trip serialize/deserialize each event type
Verify discriminator routing on RuntimeEvent
tests/unit/test_artifacts.py

Construct InvestigationArtifact and ReportArtifact, verify model_dump() shape
tests/unit/test_graph.py

Build graph with MemorySaver (not the factory — avoids I/O in unit tests)
ainvoke a minimal input and assert status == "completed" and artifacts is non-empty
Assert graph nodes exist: supervisor, reporter
Critical files
File	Status
src/kks_runtime/state/session.py	Create
src/kks_runtime/events/protocol.py	Create
src/kks_runtime/artifacts/investigation.py	Create
src/kks_runtime/checkpoint/factory.py	Create
src/kks_runtime/llm/profiles.py	Create
src/kks_runtime/graph/nodes/supervisor.py	Create
src/kks_runtime/graph/nodes/reporter.py	Create
src/kks_runtime/graph/nodes/__init__.py	Create
src/kks_runtime/graph/investigation.py	Create
src/kks_runtime/approvals/gate.py	Create
tests/unit/test_state.py	Create
tests/unit/test_events.py	Create
tests/unit/test_artifacts.py	Create
tests/unit/test_graph.py	Create
What is NOT in scope
No actual LLM calls in supervisor (comes with Phase 3 routing logic)
No worker nodes (log_detective, security_guard, machine_check — Phase 3)
No ES/Prometheus/WAF adapters (Phase 3)
No FastAPI surface (Phase 5)
No Feishu delivery (Phase 5)
Verification
cd d:/Agent20260422/kks-next

# All existing + new tests pass
uv run pytest tests/ -q

# Lint clean
uv run ruff check src/

# Graph smoke-run (no API key needed — supervisor is a stub)
uv run python -c "
import asyncio
from langgraph.checkpoint.memory import MemorySaver
from kks_runtime.graph.investigation import build_investigation_graph
from langchain_core.messages import HumanMessage

async def main():
    graph = build_investigation_graph(checkpointer=MemorySaver())
    result = await graph.ainvoke(
        {'messages': [HumanMessage(content='test')], 'target': '1.2.3.4', 'session_id': 'test-01'},
        config={'configurable': {'thread_id': 'test-01'}}
    )
    print('status:', result['status'])
    print('artifacts:', len(result['artifacts']))

asyncio.run(main())
"
Expected output:

status: completed
artifacts: 1
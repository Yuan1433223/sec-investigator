# sec-investigator Reference

Engineering map. Every entry is verified against the current codebase.

---

## Package map

### `src/runtime/` — LangGraph integration, session lifecycle, model abstraction

| Path | Responsibility | Key symbols |
|------|---------------|-------------|
| `config/settings.py` | Pydantic settings from `.env` | `Settings`, `get_settings()` |
| `state/session.py` | TypedDict state schema + reducers | `SessionState`, `InvestigationInput`, `InvestigationOutput` |
| `events/protocol.py` | SSE event discriminator union | `StatusEvent`, `ToolCallEvent`, `ToolResultEvent`, `FinalEvent`, `ErrorEvent`, `ApprovalRequestEvent`, `ApprovalDecisionEvent` |
| `events/sse.py` | RuntimeEvent → SSE frame serializer | `runtime_event_to_sse` |
| `graph/investigation.py` | Main StateGraph builder | `build_investigation_graph(checkpointer)` |
| `graph/nodes/` | Graph node implementations | `asset_resolution`, `supervisor`, `log_detective`, `dispatch_machine_checks`, `machine_check`, `machine_rollup`, `dispatch_security_checks`, `security_guard`, `security_rollup`, `approval_gate`, `reporter` |
| `graph/nodes/_tool_tracing.py` | Tool wrapper: event emission + loop protection | `make_traced_tools(tools, node, evidence_sink=None, max_repeated=4)` |
| `llm/profiles.py` | Model profile abstraction | `ModelProfile`, `build_model(profile)` |
| `approvals/gate.py` | HITL interrupt gate | `approval_gate_node` |

### `src/security/` — Security domain: adapters, tools, policies, schemas, RAG

| Path | Responsibility | Key symbols |
|------|---------------|-------------|
| `adapters/es.py` | Elasticsearch async client adapter | `ESAdapter` |
| `adapters/prometheus.py` | Prometheus HTTP adapter | `PrometheusAdapter` |
| `adapters/security_api.py` | CC/DDoS API adapter | `SecurityAPIAdapter` |
| `fake/client.py` | MockTransport injector for fake mode | `build_async_client()` |
| `fake/fixtures.py` | Synthetic incident data | `FIXTURES` |
| `tools/es_tools.py` | ES query tools factory | `_make_es_tools(adapter=None) → list[Tool]` |
| `tools/prom_tools.py` | Prometheus metric tools factory | `_make_prom_tools(adapter=None) → list[Tool]` |
| `tools/security_tools.py` | CC/DDoS protection tools factory | `_make_security_tools(adapter=None) → list[Tool]` |
| `tools/public_tools.py` | Public helper tools (table structure, connectivity) | `PUBLIC_TOOLS`, `get_gf_log_table_structure`, `get_waf_log_table_structure`, `check_connection_status` |
| `rag/rag_tools.py` | RAG knowledge search tools factory | `_make_rag_tools() → list[Tool]` |
| `policies/evidence.py` | Deterministic risk classifiers | `default_policy()`, `EvidencePolicy.classify_logs/classify_machine/classify_security` |
| `policies/extraction.py` | Deterministic evidence collector from tool outputs | `EvidenceCollector`, `extract_log_evidence`, `extract_machine_evidence`, `extract_security_evidence` |
| `schemas/findings.py` | Pydantic finding models | `LogFindings`, `MachineFindings`, `SecurityFindings` |
| `schemas/report.py` | Pydantic report model | `InvestigationReport` |
| `playbooks/catalog.py` | Playbook definitions (prompt + budget) | `PlaybookKind`, `get_playbook(kind)` |

### `src/surfaces/` — Thin HTTP surface (FastAPI)

| Path | Responsibility |
|------|---------------|
| `api/investigation.py` | SSE stream endpoints: start / resume, `subgraphs=True` event bubbling |
| `api/assets.py` | Asset resolution endpoint |
| `web/dist/` | Built React SPA (hosted by FastAPI) |

---

## Configuration keys (`.env` ↔ `Settings` fields)

| Env var | Settings field | Type | Default | Meaning |
|---------|---------------|------|---------|---------|
| `DATA_SOURCE` | `data_source` | str | `fake` | `fake` = offline fixtures; `real` = live endpoints |
| `LLM_PROVIDER` | `llm_provider` | str | `openai` | Provider switch |
| `OPENAI_API_KEY` | `openai_api_key` | str | `""` | API key |
| `OPENAI_BASE_URL` | `openai_base_url` | str | `https://api.openai.com/v1` | Base URL (Dashscope / vLLM / Ollama compatible) |
| `PLUS_MODEL_NAME` | `plus_model_name` | str | `gpt-4o` | Reasoning model |
| `FLASH_MODEL_NAME` | `flash_model_name` | str | `gpt-4o-mini` | Fast classifier model |
| `ES_URL` | `es_url` | str | `http://localhost:9200` | Elasticsearch endpoint |
| `PROMETHEUS_URL` | `prometheus_url` | str | `http://localhost:9090` | Prometheus endpoint |
| `CC_API_URL` | `cc_api_url` | str | `""` | CC protection API |
| `DDOS_API_URL` | `ddos_api_url` | str | `""` | DDoS protection API |
| `CC_ATTACK_PPS_THRESHOLD` | `cc_attack_pps_threshold` | int | `2000` | Code-level CC threshold |
| `DDOS_ATTACK_KBPS_THRESHOLD` | `ddos_attack_kbps_threshold` | int | `1000000` | Code-level DDoS threshold |

---

## Runtime state (`SessionState` fields)

| Field | Type | Reducer | Meaning |
|-------|------|---------|---------|
| `messages` | `list[AnyMessage]` | `add_messages` | LangChain message history |
| `findings` | `dict[str, Any]` | `_merge_dict` | Top-level rolled-up findings by dimension |
| `asset_findings` | `dict[str, dict]` | `_merge_nested_dict` | Per-asset evidence (keyed by asset ID) |
| `artifacts` | `list[dict]` | `operator.add` | Emitted report artifacts |
| `target` | `str` | — | Raw input target |
| `session_id` | `str` | — | Checkpointer thread ID |
| `next_node` | `str` | — | Supervisor routing decision |
| `agent_task` | `str` | — | Task description passed to workers |
| `status` | `Literal[...]` | — | `running` / `completed` / `failed` / `waiting_approval` |
| `active_asset` | `dict` | — | Current asset slice (fan-out) |
| `inspection_scope` | `list[dict]` | — | Resolved assets for fan-out |

---

## SSE event types (8 discriminated unions)

| Type | Payload | Direction |
|------|---------|-----------|
| `status` | `{node, message}` | Worker → client |
| `tool_call` | `{node, tool_name, tool_input}` | Subgraph tool → client (via `subgraphs=True`) |
| `tool_result` | `{node, tool_name, output}` | Subgraph tool → client |
| `artifact` | `{artifact_type, data}` | Reporter → client |
| `final` | `{findings, artifacts}` | Reporter → client |
| `error` | `{message, node?}` | Any node → client |
| `approval_request` | `{session_id, findings}` | Approval gate → client (interrupt) |
| `approval_decision` | `{session_id, approved, approver}` | Client → gate (resume) |

### AG-UI adapter mapping (`web/src/lib/agui.ts`)

SSE frame → AG-UI semantic event (frontend-only, no backend change):

| SSE event | AG-UI type |
|-----------|-----------|
| `status` | `STEP_STARTED` |
| `tool_call` | `TOOL_CALL_START` |
| `tool_result` | `TOOL_CALL_END` |
| `final` | `STATE_SNAPSHOT` (with `finalReport`) |
| `approval_request` | `STATE_SNAPSHOT` (with `approvalReq`) |
| `error` | `ERROR` |

---

## Tool inventory

### `_make_es_tools()` → 10 tools (bound to `log_detective`)

`query_es_raw_logs`, `query_es_unique_count`, `query_es_top_n`, `query_es_qps_trend`,
`query_es_status_code_trend`, `query_es_top_n_trend`, `query_request_count`,
`query_status_code_distribution`, `query_es_trend_comparison`, `query_customer_business_desc`

### `_make_prom_tools()` → 8 tools (bound to `machine_check`)

`query_instance_uname`, `query_instance_cpu`, `query_instance_memory`, `query_instance_tcp`,
`query_instance_bandwidth`, `query_instance_status`, `query_instance_disk`, `query_instance_socket`

### `_make_security_tools()` → 6 tools (bound to `security_guard`)

`check_cc_status`, `check_ddos_status`, `check_host_status`,
`query_nodes_ip_by_ip`, `query_nodes_ip_by_domain`, `query_domain_protection_policy`

### `_make_rag_tools()` → 1 tool (bound to `log_detective`)

`search_knowledge`

### Public helper tools

`get_gf_log_table_structure`, `get_waf_log_table_structure` (log_detective),
`check_connection_status` (security_guard)

---

## Key mechanisms (A0 / A1 / A2)

| Mechanism | Location | Purpose |
|-----------|----------|---------|
| Deterministic evidence extraction | `policies/extraction.py` | Tool-output → raw numeric fields override LLM-recalled values |
| Loop protection | `_tool_tracing.py` `max_repeated=4` | Same tool called N consecutive times → sentinel stop |
| Empty-result early stop | `_tool_tracing.py` `max_empty=3` | Zero-record results → early-stop sentinel |
| Reporter 3-tier fallback | `reporter.py` | L1 function_calling → L2 json_mode → L3 regex-JSON → deterministic report |
| Subgraph event bubbling | `api/investigation.py` `subgraphs=True` | Tool events from ReAct subgraphs reach top-level SSE stream |
| Collapsible trace tree | `web/src/components/EventLog.tsx` | Lane = trace root, tool card = span node (Radix Collapsible) |
| current_time exclusion | `log_detective.py` / `security_guard.py` | Fake historical window conflicts with real now → removed to prevent LLM drift |

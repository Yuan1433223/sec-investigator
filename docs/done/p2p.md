# What was built(p1):
File	Purpose
state/session.py	SessionState with add_messages/_merge_dict/operator.add reducers; InvestigationInput/InvestigationOutput for clean I/O boundary
events/protocol.py	6 event types + RuntimeEvent discriminated union (surface layer uses this for SSE)
artifacts/investigation.py	InvestigationArtifact + ReportArtifact Pydantic models
checkpoint/factory.py	get_checkpointer() async ctx manager — SQLite dev / Postgres prod, no singleton
llm/profiles.py	ModelProfile enum + get_model(profile) factory
graph/investigation.py	build_investigation_graph() — START → supervisor → reporter → END, with RetryPolicy(max_attempts=3) on supervisor
approvals/gate.py	approval_gate HITL node using interrupt() — ready to be inserted Phase 3+
## Phase 2 (model runtime abstraction)

# What was built(p2):
File	Purpose
llm/profiles.py	ModelConfig dataclass (frozen, per-profile temperature/max_tokens) + _REGISTRY + build_model(profile, **overrides) returning BaseChatModel — no vendor SDK leaks to callers
llm/router.py	profile_for(task_type) — maps task strings to profiles, falls back to TOOL_REASONER
config/settings.py	Added local_model_base, local_model_name, local_model_api_key for OpenAI-compatible local endpoints
graph/nodes/supervisor.py	Real LLM routing via SupervisorDecision structured output using FAST_CLASSIFIER profile
tests/unit/test_llm.py	10 tests: registry completeness, model overrides, local endpoint, router, mocked supervisor, mocked full graph
## Phase 3 (donor migration) — complete

# What was built (p3):
File	Purpose
kks_security/adapters/cc.py	CCAdapter async httpx client — get_host_point(), get_batch_host_status(); PointStatus Pydantic model
kks_security/adapters/ddos.py	DDoSAdapter async httpx client — get_ddos_list() with time-range + Bearer token auth
kks_security/collectors/gf_collector.py	GFCollector — domain→node resolution across YXD/CDN/DDOS product lines with wildcard fallback; WAF rule summary formatter
kks_security/collectors/waf_collector.py	WAFCollector — domain→WAF node resolution via security-assistant API
kks_security/collectors/node_resolver.py	NodeResolver — IP→product type (WAF/GF) resolution, probes WAF first then GF endpoints
kks_security/tools/security_tools.py	_make_security_tools() factory — 6 tools: check_cc_status, check_ddos_status, check_host_status, query_nodes_ip_by_ip, query_nodes_ip_by_domain, query_domain_protection_policy; code-level attack thresholds (_is_cc_attack, _is_ddos_attack)
kks_security/rag/engine.py	RAGEngine — lazy-connecting Milvus+MongoDB FastGPT search engine; injected Settings, no import-time I/O
kks_security/rag/rag_tools.py	_make_rag_tools() factory — search_knowledge tool with adaptive multi-round threshold strategy
graph/nodes/log_detective.py	log_detective_node — ReAct agent with ES+Prometheus tools → LogFindings structured extraction
graph/nodes/machine_check.py	machine_check_node — ReAct agent with Prometheus tools → MachineFindings structured extraction
graph/nodes/security_guard.py	security_guard_node — ReAct agent with 6 security tools → SecurityFindings structured extraction
graph/nodes/supervisor.py	Updated routing: 3 workers (log_detective, machine_check, security_guard) + completion detection
graph/investigation.py	Full Phase 3 graph: supervisor → {log_detective, machine_check, security_guard} → supervisor loop → reporter → END
config/settings.py	Added GFSettings, WAFSettings, RAGSettings; Settings inherits all 8 setting classes
tests/unit/test_security.py	18 tests: CC/DDoS threshold helpers, all 6 security tools, 3 RAG tool scenarios — all mock-injected

# What was built(p3a):
File	Purpose
kks_security/schemas/findings.py	LogFindings, SecurityFindings, MachineFindings — structured worker output contracts
kks_security/adapters/es_dsl.py	ESDSLBuilder — pure DSL factory: raw docs, unique count, top-N, time-series (4 templates)
kks_security/adapters/es.py	ESAdapter — async ES client wrapper; GF/WAF index routing; injectable for tests
kks_security/tools/es_tools.py	6 LangChain @tool functions: raw logs, unique count, top-N, QPS trend, status-code trend, top-N trend; adapter-injectable
graph/nodes/log_detective.py	First real worker node — ReAct agent with ES tools → LogFindings structured output
graph/investigation.py	Graph now: START → supervisor → {log_detective → supervisor loop, reporter → END}
graph/nodes/supervisor.py	Routing table expanded: log_detective added with explicit dispatch rule
config/settings.py	ESSettings added: url, username, password, gf/waf index patterns, timeout
tests/unit/test_es_dsl.py	9 DSL builder tests (pure, no I/O)
tests/unit/test_findings_schemas.py	5 findings schema tests
## Phase 3b next: Prometheus adapter + machine_check worker, then security tools + security_guard worker.

# What was built(p3b):
File	Purpose
config/settings.py	PrometheusSettings added: url, timeout, node_port
kks_security/adapters/prometheus.py	PrometheusAdapter — async httpx client; instant + range queries; _calc_step / _peak_value pure helpers
kks_security/tools/prom_tools.py	6 LangChain tools: uname, cpu, memory, tcp, bandwidth, composite status; adapter-injectable
graph/nodes/machine_check.py	Second real worker node — ReAct agent with Prom tools → MachineFindings structured output
graph/nodes/supervisor.py	Routing table expanded to log_detective → machine_check → reporter priority order
graph/investigation.py	Graph: supervisor → {log_detective, machine_check} → supervisor loop → reporter → END
tests/unit/test_prometheus.py	12 tests: pure helpers, adapter.instance(), all 4 tool scenarios with mock adapter
## Phase 3c next: security_guard worker (CC/DDoS protection checks) — the final worker before Phase 4 playbooks.


# What was built(p3c):
File	Purpose
config/settings.py	SecurityAPISettings: cc/ddos urls, keys, token, timeouts, attack thresholds
kks_security/adapters/cc.py	CCAdapter - async httpx; get_host_point (real-time PPS) + get_batch_host_status
kks_security/adapters/ddos.py	DDoSAdapter - async httpx; get_ddos_list with time-range + sort
kks_security/tools/security_tools.py	3 tools: check_cc_status, check_ddos_status, check_host_status; thresholds in _is_cc_attack/_is_ddos_attack
graph/nodes/security_guard.py	Third real worker - ReAct agent with security tools -> SecurityFindings
graph/nodes/supervisor.py	Routing: log_detective -> machine_check -> security_guard -> reporter
graph/investigation.py	Graph: supervisor -> {log_detective, machine_check, security_guard} -> supervisor loop -> reporter -> END
tests/unit/test_security.py	11 tests: threshold helpers + all 3 tool scenarios with mock adapters
## Phase 4 next: explicit playbooks, policy code for evidence thresholds.

# What was built(p4):
New files:
src/kks_security/policies/evidence.py — EvidencePolicy dataclass with all numeric thresholds (CC PPS, DDoS kbps, CPU/memory/TCP/error-rate) in one authoritative place. default_policy() reads from Settings. Satisfies CLAUDE.md hard rule 3.
src/kks_security/playbooks/base.py — PlaybookKind (StrEnum) and Playbook (frozen dataclass). The five kinds — LOG_ANALYSIS, INFRA_DIAGNOSIS, ATTACK_ANALYSIS, ALERT_TRIAGE, REPORT_GENERATION — replace the legacy Guard/ReAct/Plan naming.
src/kks_security/playbooks/catalog.py — canonical system prompts extracted from node files into a single catalog. Nodes import get_playbook(kind) instead of hardcoding _SYSTEM_PROMPT.
src/kks_security/schemas/report.py — InvestigationReport schema migrated from the donor's FeishuCardData, cleaned to English with Feishu surface logic removed (hard rule 5).
tests/unit/test_playbooks.py — 18 tests covering all catalog entries.
tests/unit/test_evidence_policy.py — 8 tests covering policy creation, threshold correctness, and consistency with tool implementations.
Updated files:
All four worker nodes (log_detective, machine_check, security_guard, reporter) now import their playbook from the catalog instead of embedding _SYSTEM_PROMPT inline.
reporter_node promoted from stub to a real LLM-powered report writer using InvestigationReport.
test_graph.py and test_llm.py updated to mock the reporter LLM alongside the supervisor.
100/100 tests pass, lint clean.

# What was built(p5):
15 files created/updated across kks_surfaces:
File	What it does
webhook/schemas.py	GrafanaAlert + GrafanaWebhook Pydantic models, clean port from donor
webhook/entity.py	extract_entity, detect_entity_type, build_investigation_question
webhook/router.py	POST /webhooks/grafana — parses alert, fires background investigation, returns 200 immediately
web/sse.py	SSEFrame, runtime_event_to_sse, sse_frame_to_wire — drives SSE from RuntimeEvent objects, never from node names
api/investigation.py	POST /investigation (blocking) + POST /investigation/stream (SSE)
feishu/delivery.py	report_to_feishu_payload, send_report_to_feishu — markdown card, no template IDs
api/app.py	create_app() factory registering both routers
4x __init__.py	Exports for each surface package
4x test files	53 new tests covering all surface modules
Results: 153/153 tests passing, lint clean, create_app() smoke test shows all 3 routes present.


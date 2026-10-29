# 实现与接口索引

更新：2026-10-29。当前实现以源码为准；本文件不将设计目标或历史接口当作已实现能力。架构和模型边界见 [设计说明](architecture/agent_runtime_position.md)。

## 包与入口

| 路径 | 当前职责 / 主要符号 |
|---|---|
| `src/runtime/config/settings.py` | `Settings`、`get_settings()`；从 `.env` 读取配置 |
| `src/runtime/state/session.py` | `SessionState`、`InvestigationInput`、`InvestigationOutput`、reducer |
| `src/runtime/graph/investigation.py` | `build_investigation_graph(checkpointer)` |
| `src/runtime/graph/nodes/` | 资产解析、supervisor、三个 worker、fanout、rollups、reporter |
| `src/runtime/graph/nodes/_tool_tracing.py` | `make_traced_tools()`、`ainvoke_react_agent()` |
| `src/runtime/approvals/gate.py` | `approval_gate_node()`；interrupt / resume |
| `src/runtime/checkpoint/factory.py` | `get_checkpointer()`；dev SQLite，其他环境 PostgreSQL |
| `src/runtime/llm/profiles.py` | `ModelProfile`、`build_model()` |
| `src/runtime/llm/router.py` | `profile_for()`；任务到 profile 的辅助映射 |
| `src/runtime/events/protocol.py` | 8 种 RuntimeEvent 的 Pydantic discriminator union |
| `src/runtime/artifacts/investigation.py` | `InvestigationArtifact` |
| `src/security/assets/capabilities.py` | 资产能力与检查范围 |
| `src/security/collectors/` | `GFCollector`、`WAFCollector`、`NodeResolver` |
| `src/security/adapters/` | ES、Prometheus、CC、DDoS；`lifecycle.py` 的 `ToolBundle` 管理独立工厂作用域 |
| `src/security/tools/` | ES / Prometheus / 防护工具工厂及静态辅助工具 |
| `src/security/policies/extraction.py` | `EvidenceCollector`、确定性字段提取 |
| `src/security/policies/evidence.py` | `EvidencePolicy`、`default_policy()`、分项风险与审核条件 |
| `src/security/schemas/` | finding、资产与报告 schema |
| `src/security/playbooks/` | prompt、模型 profile、required findings、预算配置 |
| `src/security/rag/` | `RAGEngine`、知识检索工具；real 使用 Milvus / MongoDB / embedding |
| `src/security/fake/client.py` | `build_async_client()` 注入 MockTransport |
| `src/security/fake/transport.py` | `FakeTransportHandler` 路由模拟 HTTP 返回 |
| `src/security/fake/fixtures.py` | `IncidentProfile`、`get_profile()`、`all_profiles()`、`search_kb()` |
| `src/surfaces/api/app.py` | `create_app()`、命令行启动、托管仓库根目录 `web/dist` |
| `src/surfaces/api/investigation.py` | 开始调查 / SSE / resume 请求与图调用 |
| `src/surfaces/web/sse.py` | `runtime_event_to_sse()`、`sse_frame_to_wire()`、`DONE_FRAME` |
| `src/surfaces/webhook/` | Grafana schema、实体提取、去重、后台调查 |
| `src/surfaces/feishu/delivery.py` | 报告转卡片、`send_report_to_feishu()` |
| `web/src/api.ts` | POST fetch 流解析与 API 调用 |
| `web/src/lib/agui.ts` | 内部语义映射；不是完整 AG-UI wire protocol |
| `web/src/hooks/useInvestigation.ts` | 调查、审批和页面状态 |

## HTTP 接口

| 方法与路径 | 请求 | 返回 / 行为 |
|---|---|---|
| `POST /investigation` | `{target, session_id, question?}` | 图输出 JSON；critical 可能中断，不代表已完成报告 |
| `POST /investigation/stream` | 同上 | `text/event-stream`，包含子图工具事件 |
| `POST /investigation/resume` | `{session_id, approved, approver}` | 在同一 checkpoint thread 上恢复，继续 SSE |
| `POST /webhooks/grafana` | Grafana webhook schema | 快速响应 accepted/reason，后台调查；可选飞书投递 |
| `GET /{full_path:path}` | SPA 路径 | 仅存在 `web/dist/index.html` 时注册 |

资产解析属于图节点，没有独立 `/assets` HTTP 路由。默认监听端口为 18230。Webhook 完整审核运营流程未验证。

## 配置

以下是关键配置入口；完整字段和默认值见 `src/runtime/config/settings.py`。Settings 代码默认值可被 `.env` 覆盖，不能把模板值当作代码默认值。

| 配置组 | 变量 | 说明 |
|---|---|---|
| 应用 | `ENV`、`DEBUG`、`LOG_LEVEL` | dev 使用 SQLite checkpoint |
| 数据 | `DATA_SOURCE` | 默认 fake；real 访问实际业务系统 |
| 模型选择 | `LLM_PROVIDER` | Settings 默认 openai，`.env.example` 当前为 anthropic |
| OpenAI 兼容 | `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`PLUS_MODEL_NAME`、`FLASH_MODEL_NAME` | 聊天模型端点与名称 |
| Anthropic | `ANTHROPIC_API_KEY`、`ANTHROPIC_BASE_URL`、`CLAUDE_MODEL_NAME`、`CLAUDE_FLASH_MODEL_NAME` | 另一聊天模型后端 |
| 本地模型 | `LOCAL_MODEL_BASE`、`LOCAL_MODEL_NAME`、`LOCAL_MODEL_API_KEY` | `LOCAL_OFFLINE_MODEL` profile 使用，普通 worker 不自动切换到它 |
| 追踪 | `LANGSMITH_TRACING`、`LANGSMITH_ENDPOINT`、`LANGSMITH_API_KEY`、`LANGSMITH_PROJECT` | 可选配置，不代表已部署追踪平台 |
| 存储 | `SQLITE_PATH`、`POSTGRES_DSN`、`REDIS_URL` | SQLite/PostgreSQL checkpoint；REDIS_URL 字段存在不代表所有去重已接 Redis |
| ES | `ES_URL`、`ES_USERNAME`、`ES_PASSWORD`、`ES_WAF_INDEX`、`ES_GF_INDEX`、`ES_ALARM_INDEX`、`ES_REQUEST_TIMEOUT` | 日志查询 |
| Prometheus | `PROMETHEUS_URL`、`PROMETHEUS_REQUEST_TIMEOUT`、`PROMETHEUS_NODE_PORT` | 主机指标 |
| CC / DDoS | `CC_API_URL`、`CC_API_KEY`、`CC_REQUEST_TIMEOUT`、`DDOS_API_URL`、`DDOS_API_KEY`、`DDOS_TOKEN`、`DDOS_REQUEST_TIMEOUT` | 防护查询 |
| 阈值 | `CC_ATTACK_PPS_THRESHOLD`、`CC_ATTACK_DELTA_THRESHOLD`、`DDOS_ATTACK_KBPS_THRESHOLD` | 设置默认分别为 2000、1000、1000000 |
| WAF / GF | `WAF_API_URL`、`WAF_API_TOKEN`、`WAF_REQUEST_TIMEOUT`、`GF_YXD_API_URL`、`GF_YXD_API_XTOKEN`、`GF_CDN_API_URL`、`GF_CDN_API_XTOKEN`、`GF_DDOS_API_URL`、`GF_DDOS_API_XTOKEN`、`GF_REQUEST_TIMEOUT` | 产品节点与域名查询 |
| 飞书 | `FEISHU_ALERT_WEBHOOK_URL` | 配置后才尝试发送 |
| RAG | `MILVUS_*`、`MONGODB_*`、`RAG_EMBEDDING_MODEL`、`RAG_EMBEDDING_DIMENSIONS`、`RAG_SCORE_THRESHOLD`、`RAG_TOP_K`、`RAG_DEFAULT_TEAM_ID`、`RAG_DEFAULT_DATASET_ID` | fake 走内置 KB，real 连接向量库/文档库与 embedding |

`DATA_SOURCE=fake` 替换业务 HTTP 数据与 RAG 知识样例；连通性检查返回未检测，不执行真实 ICMP。它不 Mock 聊天模型，也不拦截配置后主动发送的飞书消息。

## 图输入、状态与输出

直接调用图的输入为 `messages`、`target`、`session_id`，可选预置 `findings`。HTTP 请求不直接暴露预置 findings。

| 状态字段 | 合并方式 / 用途 |
|---|---|
| `messages` | `add_messages` |
| `findings` | 浅合并；会话级 logs / machine / security |
| `asset_findings` | 按 asset_id 合并内部字段，保留不同 worker 结果 |
| `artifacts` | 列表追加 |
| `target`、`session_id` | 原始目标、checkpoint thread ID |
| `next_node`、`agent_task` | 代码选路、模型任务描述 |
| `status`、`error` | running / completed / failed / waiting_approval；错误信息 |
| `target_type`、`resolved_target`、`source_type`、`resolution_reason` | 解析结果 |
| `node_ips`、`product_ips` | 按能力拆分的地址 |
| `capability_scope`、`inspection_scope` | 检查准入与解析资产 |
| `active_asset` | `Send()` 的当前资产分片 |
| `analysis_window` | 已知 fake 样例的预置时间窗；传播给 worker 与报告 |

图输出包括 `messages`、`findings`、可选 `asset_findings`、`artifacts`、`status`。报告 artifact 包含 target、session、分项发现、资产发现、嵌套 report、risk、summary、recommendations。

## 事件与前端映射

SSE 帧格式为 `data: {"type": ..., ...payload}\n\n`。`done` 是 surface 的流结束标记，不属于 8 种 RuntimeEvent。

| RuntimeEvent type | payload | 当前前端处理 |
|---|---|---|
| `status` | `{node, message}` | `STEP_STARTED` |
| `tool_call` | `{node, tool_name, tool_input, call_id}` | `TOOL_CALL_START` |
| `tool_result` | `{node, tool_name, output, call_id}` | `TOOL_CALL_END` |
| `artifact` | `{artifact_type, data}` | 映射层忽略，最终用 final |
| `final` | `{findings, artifacts}` | `STATE_SNAPSHOT` |
| `error` | `{message, node?}` | `ERROR` |
| `approval_request` | `{session_id, findings}` | `STATE_SNAPSHOT` + 弹窗 |
| `approval_decision` | `{session_id, approved, approver}` | `APPROVAL_DECISION`；拒绝时前端标记已终止 |

客户端通过 `/resume` 提交审核决定；`approval_decision` 是 gate 在恢复后发出的确认事件。`call_id` 用于关联工具调用和结果；事件没有完整 tracing schema 或持久化审计能力。

## 工具清单

### ES：`get_es_tools()` / `_make_es_tools(adapter=None)`

`query_es_raw_logs`、`query_es_unique_count`、`query_es_top_n`、`query_es_qps_trend`、`query_es_status_code_trend`、`query_es_top_n_trend`、`query_request_count`、`query_status_code_distribution`、`query_es_trend_comparison`、`query_customer_business_desc`。

### Prometheus：`get_prom_tools()` / `_make_prom_tools(adapter=None)`

`query_instance_uname`、`query_instance_cpu`、`query_instance_memory`、`query_instance_tcp`、`query_instance_bandwidth`、`query_instance_status`、`query_instance_disk`、`query_instance_socket`。

### 防护：`get_security_tools()` / `_make_security_tools(...)`

`check_cc_status`、`check_ddos_status`、`check_host_status`、`query_nodes_ip_by_ip`、`query_nodes_ip_by_domain`、`query_domain_protection_policy`。分别依赖 CC/DDoS adapter、GF/WAF collector 和 NodeResolver，不存在统一 `SecurityAPIAdapter`。

### RAG 与辅助工具

`get_rag_tools()` / `_make_rag_tools(engine=None)` 返回 `search_knowledge`。`PUBLIC_TOOLS` 导出 `current_time`、`check_connection_status`、`get_gf_log_table_structure`、`get_waf_log_table_structure`；worker 实际分别绑定字段说明和连通性工具，未把 `current_time` 接入当前调查路径。

## 已知实现缺口

聊天模型抽象不覆盖 RAG embedding SDK；前端仍部分识别节点名；报告正文不保证和全部原始指标一致。重复/空结果机制返回停止提示，真正运行上限来自递归限制。详见 [实现边界](architecture/agent_runtime_position.md#约束与实际保证范围)。

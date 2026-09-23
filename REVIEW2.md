当前图

  ┌──────────────────────────── surfaces ────────────────────────────┐
  │ API / webhook / SSE / Feishu                                        │
  │ 负责入口、回包、后台触发、消息投递                                   │
  └───────────────────────────────┬──────────────────────────────────────┘
                                  │ invoke graph
  ┌──────────────────────────── runtime ─────────────────────────────┐
  │ State / Events / Checkpoint / LLM Profiles / LangGraph              │
  │                                                                     │
  │ START                                                               │
  │   ↓                                                                 │
  │ asset_resolution                                                    │
  │   ↓                                                                 │
  │ supervisor                                                          │
  │   ├─→ log_detective ─┐                                              │
  │   ├─→ machine_check ─┼─→ supervisor loop                            │
  │   ├─→ security_guard ┘                                              │
  │   ├─→ approval_gate                                                 │
  │   └─→ reporter → END                                                │
  │                                                                     │
  │ 特征：                                                              │
  │ - 已有 typed state / checkpoint / HITL / SSE                        │
  │ - 仍是串行 worker 轮转                                              │
  │ - supervisor 主要按 target_type 路由                                │
  └───────────────────────────────┬──────────────────────────────────────┘
                                  │ call tools / policies
  ┌──────────────────────────── security ────────────────────────────┐
  │ playbooks / schemas / policies / collectors / tools / adapters      │
  │                                                                     │
  │ ES tools      Prom tools      Security tools                        │
  │ GF/WAF/Node   EvidencePolicy  Findings/Report schemas               │
  │ Resolver                                                         │
  └──────────────────────────────────────────────────────────────────────┘

  三层内收敛后的目标图

  ┌──────────────────────────── surfaces ────────────────────────────┐
  │ API / webhook / SSE / Feishu                                        │
  │ 只做入口适配、事件订阅、结果投递                                     │
  └───────────────────────────────┬──────────────────────────────────────┘
                                  │
  ┌──────────────────────────── runtime ─────────────────────────────┐
  │ LangGraph 真正按“资产图”驱动                                         │
  │                                                                     │
  │ START                                                               │
  │   ↓                                                                 │
  │ asset_resolution                                                    │
  │   ↓ produces inspection_scope[]                                     │
  │ dispatch/fan-out                                                    │
  │   ├─→ log_detective(target/domain or asset) ─┐                      │
  │   ├─→ machine_check(per node) ───────────────┼─→ fan-in / reduce    │
  │   └─→ security_guard(per product ip) ────────┘                      │
  │                        ↓                                            │
  │                  policy decision                                    │
  │                  ├─→ approval_gate                                  │
  │                  └─→ reporter → END                                 │
  │                                                                     │
  │ 特征：                                                              │
  │ - supervisor 不再只做串行排班                                        │
  │ - inspection_scope 成为真正调度输入                                  │
  │ - runtime 负责 fan-out / fan-in / state reduce                      │
  └───────────────────────────────┬──────────────────────────────────────┘
                                  │
  ┌──────────────────────────── security ────────────────────────────┐
  │ 业务核心继续沉在这一层                                               │
  │                                                                     │
  │ 资产解析模型：NodeMachine / source_type / node_type                 │
  │ 证据分类：EvidencePolicy.classify_*()                               │
  │ 数据接入：ES / Prom / CC / DDoS / GF / WAF                          │
  │ 结构输出：Findings / Report                                         │
  └──────────────────────────────────────────────────────────────────────┘

  成品时的企业开源级系统架构图

                                     +----------------------+
                                     |   Users / Systems    |
                                     | UI / API / Webhook   |
                                     +----------+-----------+
                                                |
                         +----------------------+----------------------+
                         |                                             |
                         v                                             v
              +---------------------+                     +----------------------+
              |  Surface Gateway    |                     |  Async Ingress       |
              |---------------------|                     |----------------------|
              | REST / SSE / Auth   |                     | Webhook / Queue /    |
              | Rate limit / RBAC   |                     | Scheduled Trigger    |
              | Tenant context      |                     | Dead-letter / Retry  |
              +----------+----------+                     +----------+-----------+
                         |                                             |
                         +----------------------+----------------------+
                                                |
                                                v
  +----------------------------------------------------------------------------------+
  |                            Investigation Runtime Kernel                           |
  |----------------------------------------------------------------------------------|
  | Session API / Run Manager / Checkpoint / Event Bus / Audit / Policy Engine       |
  |                                                                                  |
  | Typed State Model                                                                 |
  |   tenant_id / session_id / target / target_profile / findings / artifacts /      |
  |   approvals / evidence / execution_budget / trace                                |
  |                                                                                  |
  | Graph Orchestrator                                                                |
  |   START                                                                           |
  |     -> asset_resolution                                                           |
  |     -> supervisor                                                                 |
  |         -> log_detective                                                          |
  |         -> machine_check                                                          |
  |         -> security_guard                                                         |
  |         -> knowledge_assistant                                                    |
  |         -> policy_evaluator                                                       |
  |         -> approval_gate                                                          |
  |         -> reporter                                                               |
  |     -> END                                                                        |
  |                                                                                  |
  | Cross-cutting runtime capabilities                                                |
  |   tool budget / timeout / retry / cancellation / HITL / replay / evaluation      |
  +-----------------------------------+----------------------------------------------+
                                      |
                                      v
  +----------------------------------------------------------------------------------+
  |                                Security Domain                                    |
  |----------------------------------------------------------------------------------|
  | Domain Models                                                                     |
  |   Asset / ProductLine(WAF, GF) / Node / ProductIP / Evidence / Finding / Report |
  |                                                                                  |
  | Playbooks & Policies                                                              |
  |   routing policy / evidence policy / escalation policy / tenant policy           |
  |                                                                                  |
  | Domain Services                                                                   |
  |   asset-resolution service                                                        |
  |   report service                                                                  |
  |                                                                                  |
  | Tool Facades                                                                      |
  |   ES facade / Prom facade / Security facade / RAG facade / Business facade       |
  +-----------------------------------+----------------------------------------------+
                                      |
                                      v
  +----------------------------------------------------------------------------------+
  |                           Adapters / Integrations                                 |
  |----------------------------------------------------------------------------------|
  | WAF API | GF API | Elasticsearch | Prometheus | CC API | DDoS API | RAG | Feishu |
  | Grafana | Object Storage | Postgres | Redis | Kafka/NATS | LangSmith / OTEL      |
  +-----------------------------------+----------------------------------------------+
                                      |
                                      v
  +----------------------------------------------------------------------------------+
  |                       Observability / Governance / Ops                            |
  |----------------------------------------------------------------------------------|
  | Structured events | tracing | metrics | audit log | replay store | eval harness  |
  | secret management | config profiles | deployment manifests | migration tooling   |
  +----------------------------------------------------------------------------------+

  两者差距

  - 当前版已经有 surface / runtime / security 三层，这是对的。
  - 成品版需要再补 6 个企业级边界：
  - asset_resolution 成为一等 graph 节点，而不是散在 tools/collectors。
  - policy engine 独立出来，不只是一份 evidence threshold。
  - tenant / auth / RBAC / rate limit 进入系统边界。
  - event bus / audit / replay / eval 进入 runtime 标配。
  - async ingress 独立，webhook 不直接绑本地内存流程。
  - domain service 明确化，避免 runtime 直接拼 surface 交付逻辑。

  一句话判断
  sec-investigator 现在已经像“正确方向的调查内核”，
  成品时要升级成“带治理、审计、租户、回放、异步入口的企业级安全调查平台”。


现在的 sec-investigator 三层骨架是对的：

  - src/surfaces/：入口与交付层，见 /D:/Agent20260422/sec-investigator/src/surfaces/api/app.py
  - src/runtime/：运行时内核，见 /D:/Agent20260422/sec-investigator/src/runtime/graph/investigation.py
  - src/security/：安全业务域，见 /D:/Agent20260422/sec-investigator/src/security/playbooks/catalog.py

  如果要走到“企业开源级成品架构”，我建议重组为：

  src/
  ├─ kks_app/           # 应用装配层
  ├─ surfaces/      # 对外交互层
  ├─ runtime/       # 图运行时与会话内核
  ├─ kks_domain/        # 纯业务域模型与领域服务
  ├─ kks_integrations/  # 外部系统适配器
  ├─ kks_platform/      # 平台能力：鉴权、租户、审计、配置、观测
  └─ kks_eval/          # 回放、评测、基准

  当前目录怎么落位

  - surfaces 基本保留。
  - runtime 基本保留，但只保留运行时语义：state、graph、events、checkpoint、approval、artifacts、llm profile。
  - security 需要拆成两半：
      - 纯业务语义放进 kks_domain
      - 外部接口接入放进 kks_integrations

  更具体地说：

  - src/security/playbooks/ -> src/kks_domain/investigation/playbooks/
  - src/security/policies/ -> src/kks_domain/investigation/policies/
  - src/security/schemas/findings.py -> src/kks_domain/investigation/models/findings.py
  - src/security/schemas/report.py -> src/kks_domain/investigation/models/report.py
  - src/security/tools/ -> 拆分
      - 面向 graph 的 tool facade 留在 src/kks_domain/investigation/tools/
      - 真正访问外部系统的逻辑下沉到 src/kks_integrations/...
  - src/security/adapters/ -> src/kks_integrations/observability/ 和 src/kks_integrations/security_products/
  - src/security/collectors/ -> src/kks_domain/assets/services/ 或 src/kks_integrations/security_products/
    collectors/
  - src/surfaces/feishu/ 最终应只做交付，不该被 runtime 直接 import，当前 /D:/Agent20260422/sec-investigator/src/
    runtime/graph/nodes/reporter.py 这层依赖后面要切掉。

  建议新增目录

  这是成品阶段最值得补的目录：

  src/
  ├─ kks_app/
  │  ├─ bootstrap.py
  │  └─ container.py
  │
  ├─ kks_domain/
  │  ├─ assets/
  │  │  ├─ models.py              # Asset / ProductLine / Node / ProductIP
  │  │  ├─ services.py            # asset resolution
  │  │  └─ policies.py            # WAF/GF互斥、节点 eligibility
  │  └─ investigation/
  │     ├─ models/
  │     ├─ playbooks/
  │     ├─ policies/
  │     ├─ services/
  │     └─ tools/
  │
  ├─ kks_integrations/
  │  ├─ elasticsearch/
  │  ├─ prometheus/
  │  ├─ cc_ddos/
  │  ├─ waf_gf/
  │  ├─ feishu/
  │  ├─ grafana/
  │  └─ rag/
  │
  ├─ kks_platform/
  │  ├─ auth/
  │  ├─ tenancy/
  │  ├─ audit/
  │  ├─ observability/
  │  ├─ config/
  │  └─ queue/
  │
  └─ kks_eval/
     ├─ replay/
     ├─ benchmark/
     └─ datasets/

  最关键的重组点

  不是简单挪目录，而是这 4 个边界要落实：

  - asset_resolution 从 collector/tool 升级为一等领域服务，最终再接成 graph 节点。
  - runtime 不再直接依赖 feishu、webhook 这类 surface 逻辑。
  - integrations 只负责“连外部系统”，不持有调查语义。
  - domain 只负责“这家安全公司的业务语义”，例如：
      - 域名属于 WAF 还是 GF
      - 哪些目标能进 machine_check
      - status 和 upstream_status 怎么解释
      - CC/DDoS 证据和 ES 证据如何拼成结论

  我建议的落地顺序

  1. 先拆 security。
  2. 再引入 kks_domain/assets/，把资产解析单独立起来。
  3. 然后切断 runtime -> surfaces 反向依赖。
  4. 最后补 kks_platform/auth|audit|tenancy 和 kks_eval/。
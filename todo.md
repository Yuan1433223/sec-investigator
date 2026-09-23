# sec-investigator TODO

> 定位更新（2026-09-23）：从"企业内网安全系统"改为**个人可展示作品**——
> 目标：独立可运行、公开安全（无企内凭据/标识）、工程整洁、有版本演进叙事。

---

## 里程碑：作品集化改造（做完即可展示）

### M1 命名清理：去掉 `kks_` 前缀
- [x] `git init`（已建版本库，改名作为一次干净 commit）
- [x] 目录改名：`kks_runtime → runtime` / `kks_security → security` / `kks_surfaces → surfaces`（拍板裸名）
- [x] 更新引用：~317 处 py（82 文件）+ ~185 处 toml/md/env（15 文件）
- [x] pyproject：project name / console script `sec-investigator` / wheel packages
- [x] settings.sqlite_path + db 文件 `sec_investigator.db` + LangSmith project 名
- [x] 品牌清洗：代码/.env/文档已移除公司标识（保留对捐赠 legacy 的 `KKS` 指代）
- [x] 验证：全量测试通过（495 passed / ~6s）

### M2 空目录处置（仅 `__init__.py` 的包）
- [x] 删除：`executor`、`sessions`（职责已被现有代码覆盖）
- [x] `resources` 删除；M4 的 fixture 将放 `tests/fixtures/`
- [x] `reports`：已删除（报告逻辑在 reporter 节点）
- [x] 核对无其他死引用

### M3 文档瘦身 + 根架构图
- [x] 合并 `AGENTS.md` + `CLAUDE.md` → 单一 AGENTS.md
- [x] 合并 `REVIEW.md` + `REVIEW2.md` → 单一 REVIEW.md
- [x] `WHY_I_DO.md` 内容已并入架构文档（agent_runtime_position.md）
- [x] `context.md` → 提取 3 条真实事故为 `docs/incidents.md`，删除 Q&A 噪声
- [x] `docs/done/*` 已删除
- [x] `docs/origin_data/*` 保留为参考，已脱敏企内主机/标识
- [x] 新增根 `README.md` + `docs/architecture.svg` 系统架构图
- [x] 清理杂项（pytest_cache 已 ignore；空目录已删）

### M4 数据源 fake 化（接上一轮讨论）
- [x] `DATA_SOURCE=fake/real` 源选择；`security/fake/client.build_async_client` 单一 seam（httpx.MockTransport），7 个 adapter/collector 全接线
- [x] `security/fake/` 从 `docs/incidents.md` 3 条真实事故造 fixture（ES/Prom/CC/DDoS/WAF/GF/RAG）
- [x] 测试：新增 `tests/unit/test_fake_source.py`（10 用例锁 fixture→工具契约）；全套件 495 秒级、全离线
- [x] `.env`/`.env.example`：`DATA_SOURCE=fake`、占位 base URL、脱敏
- [x] 离线 demo：`examples/run_demo.py`（三条事故目标可选）
- [x] replay 测试更新：域名解析成功→预注入 machine 金标准（节点健康/过载）

### M5 LLM 兼容修复（智谱 GLM 接入）
- [x] `.env` 接智谱 OpenAI 兼容端点 `https://open.bigmodel.cn/api/paas/v4`，模型 `glm-4.5-air`
- [x] 修复 `with_structured_output`：显式 `method="function_calling"`（supervisor / log_detective /
      reporter / machine_check / security_guard 共 5 处）——智谱等 OpenAI 兼容中继不识别 strict
      json_schema，默认会返回纯文本导致结构化解析失败
- [x] 验证：495 全绿；`examples/run_demo.py` 用智谱跑通整条链（含审批自动批准）

### M6 Web 前端（demo 可视化，Vite + React + TS）
- [x] `web/` 单页前端：阶段轨 + SSE 执行时间线 + 分项发现 + 最终报告 + 人工审批弹窗
      （纸墨风去 AI 味 / 中文 / 无 emoji）
- [x] 后端新增 `POST /investigation/resume`（`Command(resume=...)` 恢复被 interrupt 的审批会话）
- [x] FastAPI 静态托管 `web/dist`（SPA 回退）；dev 用 Vite proxy
- [x] 构建通过 + 静态服务 / stream / approval_request 实链验证（final 渲染待模型恢复后复核）


---

## Current status（2026-04-30，保留）

三层架构已稳定：`runtime` / `security` / `surfaces`；
`asset_resolution` 为图入口；supervisor 能力驱动路由；machine/security worker 经 `Send` 资产级扇出 + rollup；`reporter` 产出含 findings / asset_findings / 结构化 report 的 artifact；HITL 门在主路径。

```text
START → asset_resolution → supervisor
   ├─→ log_detective
   ├─→ dispatch_machine_checks → Send(machine_check per asset) → machine_rollup
   ├─→ dispatch_security_checks → Send(security_guard per asset) → security_rollup
   ├─→ approval_gate
   └─→ reporter → END
```

## Tool asset inventory

| Factory / module | Tools | Bound to worker |
|---|---|---|
| `es_tools._make_es_tools()` | `query_es_raw_logs`, `query_es_unique_count`, `query_es_top_n`, `query_es_qps_trend`, `query_es_status_code_trend`, `query_es_top_n_trend`, `query_request_count`, `query_status_code_distribution`, `query_es_trend_comparison`, `query_customer_business_desc` (10) | `log_detective` |
| `prom_tools._make_prom_tools()` | `query_instance_uname`, `query_instance_cpu`, `query_instance_memory`, `query_instance_tcp`, `query_instance_bandwidth`, `query_instance_status`, `query_instance_disk`, `query_instance_socket` (8) | `machine_check` |
| `security_tools._make_security_tools()` | `check_cc_status`, `check_ddos_status`, `check_host_status`, `query_nodes_ip_by_ip`, `query_nodes_ip_by_domain`, `query_domain_protection_policy` (6) | `security_guard` |
| `public_tools` | `current_time`, `check_connection_status`, `get_gf_log_table_structure`, `get_waf_log_table_structure` (4) | `log_detective` + `security_guard` |
| `rag_tools._make_rag_tools()` | `search_knowledge` (1) | `log_detective` |

## Remaining work after demo closure

### A. Log model decision
- [ ] `log_detective` 保持 target/service scoped，还是设计 asset/log 绑定模型

### B. Error normalization
- [ ] `ErrorEvent` 作为通用失败契约，包装 worker/reporter 归一化错误发射
- [ ] 单 worker 失败时保留降级报告生成

### C. Sync RAG isolation
- [ ] `rag/engine.py` 的 Milvus 查询包进 `anyio.to_thread.run_sync`

### D. In-session tool-call cache
- [ ] ES tool factory 加 per-investigation 缓存，减少重复查询

### E. Alert time-window alignment
- [ ] alert end offset 可配置，ES 对比窗口与之一致

### Phase 5 hardening
- [ ] Auth 扩展点（FastAPI 中间件钩子）
- [ ] Rate-limiting 中间件钩子
- [ ] 租户隔离：session_id 按 tenant namespaced

### Phase 6 evals
- [ ] 对真实 ES + Prometheus 的集成 smoke test
- [ ] 用真实 report writer 模型对录制的告警做 report quality eval
- [ ] 跨模型 eval：fast_classifier / tool_reasoner / structured_extractor / report_writer

### Phase 7 switchover
- [ ] 解决告警时间窗策略
- [ ] 旧 KKS 旁跑一条 live shadow stream
- [ ] 真实告警上对比 findings/report 输出
- [ ] 将一个生产面迁到 sec-investigator
- [ ] parity 证明后退役旧 KKS

### P2 deferred
- [ ] Feishu 富卡片模板
- [ ] Feishu 多维表格持久化
- [ ] Grafana 图表渲染 + Feishu 图片上传
- [ ] 强化 `InvestigationArtifact.report` 为稳定 surface/UI 契约
- [ ] 仅在事故证据证明需要时增加延迟 ES 工具

## 短指令

保持运行时图全局且显式。
业务增长应新增资产类型、证据模型、工具、worker 子图，而不触发又一次架构重构。

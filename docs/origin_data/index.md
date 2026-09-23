# 上游数据接口索引

本目录记录工程中所有请求上游的接口文档，包括每个接口的说明描述和请求示例。

## 上游服务汇总

| 上游服务 | 文档 | 接口数量 | 说明 |
|----------|------|----------|------|
| [Elasticsearch](./elasticsearch.md) | elasticsearch.md | 8 | 日志查询和聚合分析 |
| [Prometheus](./prometheus.md) | prometheus.md | 7 | 服务器性能监控数据 |
| [CC/DDoS 防护 API](./security_api.md) | security_api.md | 2 | 安全防护数据查询 |
| [飞书 API](./feishu.md) | feishu.md | 4 | 问答日志记录 |
| [WAF/高防产品 API](./product_api.md) | product_api.md | 4 | 域名关联节点查询 |
| [通义千问 LLM API](./llm_api.md) | llm_api.md | 10 | AI 分析和报告生成 |

---

## 接口穷举清单

### 一、Elasticsearch (8 个接口)

| 序号 | 接口名称 | 方法 | 说明 |
|------|----------|------|------|
| 1 | check_ip_source | POST | 检测 IP 属于哪个产品（WAF/GF） |
| 2 | query_request_count | POST | 查询指定时间范围内的请求总数 |
| 3 | query_ua_top10 | POST | 查询 Top 10 User-Agent |
| 4 | query_ip_top10 | POST | 查询 Top 10 客户端 IP |
| 5 | query_status_code_analysis | POST | 查询 HTTP 响应码分布 |
| 6 | query_nodes_requested_count | POST | 查询多节点请求统计 |
| 7 | query_latest100_log_records | POST | 查询最近 100 条日志 |
| 8 | es_log_query | POST | 自然语言查询（LLM 生成 DSL） |

### 二、Prometheus (7 个接口)

| 序号 | 接口名称 | 方法 | 说明 |
|------|----------|------|------|
| 1 | query_node_uname_info | GET | 查询节点系统信息 |
| 2 | query_cpu_usage | GET | 查询 CPU 使用率 |
| 3 | query_memory_usage | GET | 查询内存使用率 |
| 4 | query_disk_io | GET | 查询磁盘 I/O 读写速率 |
| 5 | query_tcp_connections | GET | 查询 TCP 连接数 |
| 6 | query_tcp_sockets | GET | 查询 TCP Socket 数 |
| 7 | query_all_info | GET | 并发查询所有监控信息 |

### 三、CC/DDoS 防护 API (2 个接口)

| 序号 | 接口名称 | 方法 | 说明 |
|------|----------|------|------|
| 1 | get_host_point | GET | 获取主机网络包数据（CC） |
| 2 | get_ddos_list | GET | 获取 DDoS 攻击列表 |

### 四、飞书 API (4 个接口)

| 序号 | 接口名称 | 方法 | 说明 |
|------|----------|------|------|
| 1 | _get_obj_token | GET | 获取知识库节点信息 |
| 2 | table_insert_record | POST | 多维表格插入记录 |
| 3 | table_update_record | PUT | 多维表格更新记录 |
| 4 | save_chat_log | - | 保存问答日志（组合接口） |

### 五、WAF/高防产品 API (4 个接口)

| 序号 | 接口名称 | 方法 | 说明 |
|------|----------|------|------|
| 1 | waf_query_ip_by_domain | GET | WAF 根据域名查询节点 IP |
| 2 | gf_query_ip_by_domain (游戏盾) | GET | 游戏盾根据域名查询节点 IP |
| 3 | gf_query_ip_by_domain (高防IP) | GET | 高防IP根据域名查询节点 IP |
| 4 | gf_query_ip_by_domain (DDoS高防) | GET | DDoS高防根据域名查询节点 IP |

### 六、通义千问 LLM API (10 个调用场景)

| 序号 | 调用场景 | 模型 | 说明 |
|------|----------|------|------|
| 1 | 意图识别 | qwen-flash | 提取用户问题中的意图和实体 |
| 2 | 报告生成 | qwen-flash | 生成结构化诊断报告 |
| 3 | 常规问答 | qwen-flash | 回答技术咨询问题 |
| 4 | 工具查询 | qwen-flash | 使用工具查询数据 |
| 5 | Ping 分析 | qwen-flash | 分析 Ping 测试结果 |
| 6 | 云防分析 | qwen-flash | 分析 CC/DDoS 防护数据 |
| 7 | Prometheus 分析 | qwen-flash | 分析监控数据 |
| 8 | ES 分析 | qwen-flash | 分析日志聚合数据 |
| 9 | 节点报告 | qwen-plus | 生成节点健康报告 |
| 10 | ES DSL 生成 | qwen-plus | 自然语言转 ES DSL |

---

## 环境变量汇总

### Elasticsearch

```bash
WAF_ES_API_URL=https://ip:port/waf-index/_search
GF_ES_API_URL=https://ip:port/gf-index/_search
ENVIRONMENT=dev  # 影响 .keyword 后缀
```

### Prometheus

```bash
PROMETHEUS_API_KEY=https://prometheus.dev.kk30.net
```

### CC/DDoS 防护

```bash
CC_API_URL=https://yunfang.dev.kk30.net
CC_API_KEY=xxx
DDOS_API_URL=http://yunfang.dev.kk30.net
DDOS_API_KEY=xxx
DDOS_TOKEN=eyJ0eXAi...
```

### 飞书

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_TABLE_ID=tbl_xxx
FEISHU_TABLE_APP_TOKEN=xxx
```

### WAF/高防产品

```bash
WAF_API_URL=https://kk_waf_admin.dev.kk30.net
WAF_API_TOKEN=xxx
GF_YXD_API_URL=http://kk_yxd_admin.dev.kk30.net
GF_YXD_API_XTOKEN=xxx
GF_CDN_API_URL=http://kk_cdn_admin.dev.kk30.net
GF_CDN_API_XTOKEN=xxx
GF_DDOS_API_URL=http://kk_ddos_admin.dev.kk30.net
GF_DDOS_API_XTOKEN=xxx
```

### 通义千问 LLM

```bash
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

---

## 数据流向图

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户请求                                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI 应用 (main.py)                       │
└─────────────────────────────┬───────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
       ┌──────────┐    ┌──────────┐    ┌──────────┐
       │ LLM API  │    │ 意图识别  │    │ 飞书 API │
       │(通义千问) │    │   Agent  │    │ (日志)   │
       └────┬─────┘    └────┬─────┘    └──────────┘
            │               │
            ▼               ▼
       ┌─────────────────────────────────────────┐
       │           数据收集层                     │
       │  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
       │  │   ES    │ │Prometheus│ │ CC/DDoS │   │
       │  └─────────┘ └─────────┘ └─────────┘   │
       │  ┌─────────────────────────────────┐   │
       │  │      WAF/高防产品 API            │   │
       │  └─────────────────────────────────┘   │
       └─────────────────────────────────────────┘
                              │
                              ▼
       ┌─────────────────────────────────────────┐
       │           报告生成 (LLM)                 │
       └─────────────────────────────────────────┘
                              │
                              ▼
       ┌─────────────────────────────────────────┐
       │              返回用户                    │
       └─────────────────────────────────────────┘
```

# Elasticsearch 上游接口

本文档记录工程中所有对 Elasticsearch 的请求接口。

## 概述

- **数据源文件**: `tools/es_check.py`
- **客户端类**: `ESClient`
- **请求方式**: HTTP POST (使用 httpx.AsyncClient)
- **数据格式**: JSON (Elasticsearch DSL)

## 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `WAF_ES_API_URL` | WAF ES 查询地址 | `https://ip:port/waf-index/_search` |
| `GF_ES_API_URL` | 高防 ES 查询地址 | `https://ip:port/gf-index/_search` |
| `ENVIRONMENT` | 运行环境 | `dev` / `prod` |

---

## 接口列表

### 1. 检测 IP 来源 (check_ip_source)

**功能描述**: 检测指定 IP 属于哪个产品（WAF 或高防）

**调用位置**: `tools/es_check.py:72`

**请求示例**:

```http
POST https://ip:port/index/_search
Content-Type: application/json

{
    "query": {
        "bool": {
            "must": [
                {
                    "term": {
                        "server_addr": "10.0.1.164"
                    }
                }
            ]
        }
    },
    "sort": [
        {
            "@timestamp": {
                "order": "desc"
            }
        }
    ],
    "size": 1
}
```

**响应示例**:

```json
{
    "hits": {
        "total": {
            "value": 100
        },
        "hits": [
            {
                "_source": {
                    "server_addr": "10.0.1.164",
                    "@timestamp": "2025-11-03T14:00:00"
                }
            }
        ]
    }
}
```

---

### 2. 查询请求总数 (query_request_count)

**功能描述**: 查询指定时间范围内的请求总数

**调用位置**: `tools/es_check.py:114`

**请求示例（按域名查询）**:

```http
POST https://ip:port/index/_search
Content-Type: application/json

{
    "query": {
        "bool": {
            "must": [
                {
                    "term": {
                        "http_host": "example.com"
                    }
                },
                {
                    "range": {
                        "time": {
                            "gte": "2025-11-03 14:00:00",
                            "lte": "2025-11-03 18:00:00"
                        }
                    }
                }
            ]
        }
    },
    "size": 0,
    "aggs": {
        "total_requests": {
            "value_count": {
                "field": "http_host"
            }
        }
    }
}
```

**请求示例（按 IP 查询）**:

```http
POST https://ip:port/index/_search
Content-Type: application/json

{
    "query": {
        "bool": {
            "must": [
                {
                    "term": {
                        "server_addr": "10.0.1.164"
                    }
                },
                {
                    "range": {
                        "time": {
                            "gte": "2025-11-03 14:00:00",
                            "lte": "2025-11-03 18:00:00"
                        }
                    }
                }
            ]
        }
    },
    "size": 0,
    "aggs": {
        "total_requests": {
            "value_count": {
                "field": "http_host"
            }
        }
    }
}
```

**响应示例**:

```json
{
    "aggregations": {
        "total_requests": {
            "value": 12345
        }
    }
}
```

**注意**: 生产环境 WAF 库需使用 `http_host.keyword`

---

### 3. 查询 Top 10 User-Agent (query_ua_top10)

**功能描述**: 查询请求中出现最多的 Top 10 User-Agent

**调用位置**: `tools/es_check.py:146`

**请求示例**:

```http
POST https://ip:port/index/_search
Content-Type: application/json

{
    "query": {
        "bool": {
            "must": [
                {
                    "term": {
                        "http_host": "example.com"
                    }
                },
                {
                    "range": {
                        "time": {
                            "gte": "2025-11-03 14:00:00",
                            "lte": "2025-11-03 18:00:00"
                        }
                    }
                }
            ]
        }
    },
    "aggs": {
        "user_agent_stats": {
            "terms": {
                "field": "http_user_agent",
                "size": 10,
                "order": {
                    "_count": "desc"
                }
            }
        }
    },
    "size": 0
}
```

**响应示例**:

```json
{
    "aggregations": {
        "user_agent_stats": {
            "buckets": [
                {
                    "key": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "doc_count": 5000
                },
                {
                    "key": "curl/7.68.0",
                    "doc_count": 1200
                }
            ]
        }
    }
}
```

---

### 4. 查询 Top 10 客户端 IP (query_ip_top10)

**功能描述**: 查询请求中出现最多的 Top 10 客户端 IP

**调用位置**: `tools/es_check.py:185`

**请求示例**:

```http
POST https://ip:port/index/_search
Content-Type: application/json

{
    "query": {
        "bool": {
            "must": [
                {
                    "term": {
                        "http_host": "example.com"
                    }
                },
                {
                    "range": {
                        "time": {
                            "gte": "2025-11-03 14:00:00",
                            "lte": "2025-11-03 18:00:00"
                        }
                    }
                }
            ]
        }
    },
    "aggs": {
        "top_client_ips": {
            "terms": {
                "field": "real_client_ip",
                "size": 10,
                "order": {
                    "_count": "desc"
                }
            }
        }
    },
    "size": 0
}
```

**响应示例**:

```json
{
    "aggregations": {
        "top_client_ips": {
            "buckets": [
                {
                    "key": "192.168.1.100",
                    "doc_count": 3000
                },
                {
                    "key": "192.168.1.101",
                    "doc_count": 2500
                }
            ]
        }
    }
}
```

---

### 5. 查询响应码分布 (query_status_code_analysis)

**功能描述**: 查询 HTTP 响应码的分布情况

**调用位置**: `tools/es_check.py:223`

**请求示例**:

```http
POST https://ip:port/index/_search
Content-Type: application/json

{
    "query": {
        "bool": {
            "must": [
                {
                    "term": {
                        "http_host": "example.com"
                    }
                },
                {
                    "range": {
                        "time": {
                            "gte": "2025-11-03 14:00:00",
                            "lte": "2025-11-03 18:00:00"
                        }
                    }
                }
            ]
        }
    },
    "aggs": {
        "status_distribution": {
            "terms": {
                "field": "status",
                "size": 100
            }
        }
    },
    "size": 0
}
```

**响应示例**:

```json
{
    "aggregations": {
        "status_distribution": {
            "buckets": [
                {"key": 200, "doc_count": 10000},
                {"key": 304, "doc_count": 2000},
                {"key": 404, "doc_count": 500},
                {"key": 500, "doc_count": 50}
            ]
        }
    }
}
```

---

### 6. 查询多节点请求统计 (query_nodes_requested_count)

**功能描述**: 查询多个节点 IP 的请求分布统计

**调用位置**: `tools/es_check.py:258`

**请求示例**:

```http
POST https://ip:port/index/_search
Content-Type: application/json

{
    "size": 0,
    "query": {
        "bool": {
            "must": [
                {
                    "terms": {
                        "server_addr": ["10.0.1.164", "10.0.1.165", "10.0.1.166"]
                    }
                }
            ],
            "filter": [
                {
                    "range": {
                        "time": {
                            "gte": "2025-11-03 14:00:00",
                            "lte": "2025-11-03 18:00:00"
                        }
                    }
                }
            ]
        }
    },
    "aggs": {
        "server_stats": {
            "terms": {
                "field": "server_addr",
                "size": 10
            },
            "aggs": {
                "total_requests": {
                    "value_count": {
                        "field": "server_addr"
                    }
                }
            }
        }
    }
}
```

**响应示例**:

```json
{
    "aggregations": {
        "server_stats": {
            "buckets": [
                {
                    "key": "10.0.1.164",
                    "total_requests": {"value": 5000}
                },
                {
                    "key": "10.0.1.165",
                    "total_requests": {"value": 4000}
                }
            ]
        }
    }
}
```

---

### 7. 查询最近 100 条日志 (query_latest100_log_records)

**功能描述**: 查询指定域名/IP 最近 100 条访问记录

**调用位置**: `tools/es_check.py:313`

**请求示例**:

```http
POST https://ip:port/index/_search
Content-Type: application/json

{
    "query": {
        "bool": {
            "must": [
                {
                    "match": {
                        "http_host": "example.com"
                    }
                }
            ]
        }
    },
    "sort": [
        {
            "create_date": {
                "order": "desc"
            }
        }
    ],
    "size": 100
}
```

**响应示例**:

```json
{
    "hits": {
        "total": {"value": 12345},
        "hits": [
            {
                "_source": {
                    "http_host": "example.com",
                    "real_client_ip": "192.168.1.100",
                    "request_uri": "/api/v1/users",
                    "status": 200,
                    "request_time": 0.05,
                    "http_user_agent": "Mozilla/5.0...",
                    "create_date": "2025-11-03 18:00:00"
                }
            }
        ]
    }
}
```

---

### 8. 自然语言查询 (es_log_query)

**功能描述**: 使用自然语言描述查询需求，由 LLM 自动生成 ES DSL 并执行

**调用位置**: `tools/es_check.py:354`

**工作流程**:
1. 用户输入自然语言查询
2. 调用 `utils/es_dsl_creator.py` 生成 ES DSL
3. 执行生成的 DSL 查询

**请求示例（LLM 生成的 DSL）**:

用户输入: "查询 www.baidu.com 这个域名最近100条日志原始记录"

```http
POST https://ip:port/index/_search
Content-Type: application/json

{
    "query": {
        "bool": {
            "must": [
                {
                    "match": {
                        "http_host": "www.baidu.com"
                    }
                }
            ]
        }
    },
    "size": 100,
    "sort": [
        {
            "@timestamp": {
                "order": "desc"
            }
        }
    ]
}
```

---

## ES 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `server_addr` | keyword | 节点 IP |
| `http_host` | text | 防护域名 |
| `real_client_ip` | keyword | 真实客户端 IP |
| `status` | integer | HTTP 响应码 |
| `request_time` | float | 响应时间（秒） |
| `http_user_agent` | text | User-Agent |
| `request_uri` | text | 请求 URI |
| `request_method` | text | 请求方法 |
| `time` | date | 请求时间 |
| `create_date` | date | 记录创建时间 |
| `upstream_addr` | keyword | 源站地址 |
| `upstream_status` | integer | 源站响应码 |
| `upstream_response_time` | float | 源站响应时间 |
| `bytes_sent` | integer | 发送字节数 |
| `body_bytes_sent` | integer | 响应体字节数 |

---

## 注意事项

1. **生产环境 `.keyword` 后缀**:
   - WAF 库在生产环境需要对聚合字段添加 `.keyword` 后缀
   - 高防库不需要添加

2. **SSL 验证**:
   - 内网环境禁用 SSL 证书验证
   - `httpx.AsyncClient(verify=False)`

3. **超时设置**:
   - 默认超时 30 秒
   - `timeout=30`

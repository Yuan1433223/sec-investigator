# 通义千问 LLM API 上游接口

本文档记录工程中所有对通义千问 LLM API 的请求接口。

## 概述

- **配置文件**: `core/llm.py`
- **SDK**: `langchain-openai` (OpenAI 兼容模式)
- **模型提供商**: 阿里云通义千问

## 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `OPENAI_API_KEY` | 通义千问 API 密钥 | `sk-xxx` |
| `OPENAI_BASE_URL` | API 基础地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |

## 模型配置

```python
# 标准模型 - qwen-plus
llm = ChatOpenAI(
    temperature=0.7,
    model="qwen-plus",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

# 快速模型 - qwen-flash
flash_llm = ChatOpenAI(
    temperature=0.7,
    model="qwen-flash",
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)
```

## 模型选择

| 模型 | 用途 | 特点 |
|------|------|------|
| `qwen-plus` | 复杂任务、报告生成 | 更强的推理能力 |
| `qwen-flash` | 快速响应、简单任务 | 低延迟、成本低 |

---

## 接口调用列表

### 1. 意图识别 (intent_agent.py)

**功能描述**: 从用户问题中提取意图和实体信息

**调用位置**: `agents/intent_agent.py:79`

**使用模型**: `qwen-flash`

**请求示例**:

```http
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
Authorization: Bearer sk-xxx
Content-Type: application/json

{
    "model": "qwen-flash",
    "temperature": 0.7,
    "messages": [
        {
            "role": "system",
            "content": "{意图分类与实体抽取的 JSON prompt}"
        },
        {
            "role": "user",
            "content": "分析 example.com 在 2025-11-03 14:00 到 18:00 的状态"
        }
    ],
    "response_format": {
        "type": "json_object"
    }
}
```

**响应示例**:

```json
{
    "choices": [
        {
            "message": {
                "content": {
                    "intent": "inspection",
                    "domain": "example.com",
                    "ip": null,
                    "time_start": "2025-11-03 14:00:00",
                    "time_end": "2025-11-03 18:00:00",
                    "question": "分析 example.com 在 2025-11-03 14:00 到 18:00 的状态"
                }
            }
        }
    ]
}
```

---

### 2. 报告生成 (report_agent.py)

**功能描述**: 综合监控数据生成结构化诊断报告

**调用位置**: `agents/report_agent.py:143`

**使用模型**: `qwen-flash`

**请求示例**:

```http
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
Authorization: Bearer sk-xxx
Content-Type: application/json

{
    "model": "qwen-flash",
    "temperature": 0.7,
    "messages": [
        {
            "role": "system",
            "content": "{报告生成的 JSON prompt，包含6个章节结构}"
        },
        {
            "role": "user",
            "content": "服务信息：{server_info}"
        },
        {
            "role": "user",
            "content": "节点信息：{node_info}"
        },
        {
            "role": "user",
            "content": "分析 example.com 的状态"
        }
    ]
}
```

**响应示例**:

```json
{
    "choices": [
        {
            "message": {
                "content": "## 一、建议与结论\n\n**总体结论**：example.com 运行状态正常...\n\n## 二、性能分析\n\n| 指标 | 当前值 | 结论 |\n|------|--------|------|\n| CPU | 45.23% | ✅ |\n..."
            }
        }
    ]
}
```

---

### 3. 常规问答 (guard_agent.py)

**功能描述**: 回答技术咨询类问题

**调用位置**: `agents/guard_agent.py:148`

**使用模型**: `qwen-flash`

**请求示例**:

```http
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
Authorization: Bearer sk-xxx
Content-Type: application/json

{
    "model": "qwen-flash",
    "temperature": 0.7,
    "messages": [
        {
            "role": "system",
            "content": "你是一位资深的网络运维专家，擅长解答运维相关问题。请根据用户的问题，提供专业、准确的回答。"
        },
        {
            "role": "user",
            "content": "什么是 DDoS 攻击？"
        }
    ]
}
```

---

### 4. Ping 结果分析 (server_check.py)

**功能描述**: 分析 Ping 测试结果，生成简要结论

**调用位置**: `logic/server_check.py:145`

**使用模型**: `qwen-flash`

**请求示例**:

```http
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
Authorization: Bearer sk-xxx
Content-Type: application/json

{
    "model": "qwen-flash",
    "temperature": 0.7,
    "messages": [
        {
            "role": "user",
            "content": "下面是对指定IP进行ping测试的结果，请判断网络是否通畅，生成简要结论(30字内)"
        },
        {
            "role": "user",
            "content": "ping测试结果：PING 10.0.1.164 (10.0.1.164): 56 data bytes\n64 bytes from 10.0.1.164: icmp_seq=0 ttl=64 time=0.5 ms\n..."
        }
    ]
}
```

**响应示例**:

```json
{
    "choices": [
        {
            "message": {
                "content": "网络连通正常，延迟约0.5ms，无丢包。"
            }
        }
    ]
}
```

---

### 5. 云防数据分析 (server_check.py)

**功能描述**: 分析 CC/DDoS 防护数据，判断是否受到攻击

**调用位置**: `logic/server_check.py:161`

**使用模型**: `qwen-flash`

**请求示例**:

```http
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
Authorization: Bearer sk-xxx
Content-Type: application/json

{
    "model": "qwen-flash",
    "temperature": 0.7,
    "messages": [
        {
            "role": "system",
            "content": "根据CC防护数据与DDOS防护数据，分析该主机是否受到攻击，并生成简洁的结论。\n针对CC防护数据，input_pps 的值大于2000，并且 input_pps - input_submit_pps >= 1000 才视为攻击。\n针对DDOS防护数据，流量大于1G视为有攻击行为。"
        },
        {
            "role": "user",
            "content": "CC攻击防护数据：[{\"address\": \"10.0.1.164\", \"input_pps\": 1500, ...}]"
        },
        {
            "role": "user",
            "content": "DDoS攻击防护数据(注意：bps字段实际单位为kbps)：{\"data\": []}"
        }
    ]
}
```

---

### 6. Prometheus 数据分析 (server_check.py)

**功能描述**: 分析 Prometheus 监控数据是否正常

**调用位置**: `logic/server_check.py:180`

**使用模型**: `qwen-flash`

**请求示例**:

```http
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
Authorization: Bearer sk-xxx
Content-Type: application/json

{
    "model": "qwen-flash",
    "temperature": 0.7,
    "messages": [
        {
            "role": "user",
            "content": "你是运维专家，下面是节点监控数据，请分析该数据是否正常！并生成简洁的结论"
        },
        {
            "role": "user",
            "content": "Prometheus数据：{\"cpu_usage\": \"45.23%\", \"memory_usage\": \"68.54%\", ...}"
        }
    ]
}
```

---

### 7. ES 日志数据分析 (server_check.py)

**功能描述**: 分析 ES 日志聚合数据是否正常

**调用位置**: `logic/server_check.py:205`

**使用模型**: `qwen-flash`

**请求示例**:

```http
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
Authorization: Bearer sk-xxx
Content-Type: application/json

{
    "model": "qwen-flash",
    "temperature": 0.7,
    "messages": [
        {
            "role": "user",
            "content": "你是运维专家，下面是ES数据，请分析该数据是否正常！并生成简洁的结论"
        },
        {
            "role": "user",
            "content": "请求总次数：12345\n请求IP排名：[...]\n请求UA排名：[...]\n响应码分布：[...]\n各个几点统计：[...]"
        }
    ]
}
```

---

### 8. 节点报告生成 (server_check.py)

**功能描述**: 为每个节点生成简洁的健康报告

**调用位置**: `logic/server_check.py:257`

**使用模型**: `qwen-plus`

**请求示例**:

```http
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
Authorization: Bearer sk-xxx
Content-Type: application/json

{
    "model": "qwen-plus",
    "temperature": 0.7,
    "messages": [
        {
            "role": "system",
            "content": "你是一位运维专家，你的任务是根据信息生成一份简洁的节点健康报告(50字内)"
        },
        {
            "role": "user",
            "content": "服务器信息：\n{\"ip\": \"10.0.1.164\", \"ping\": {...}, \"monitor\": {...}, \"fence\": {...}}"
        }
    ]
}
```

---

### 9. ES DSL 生成 (es_dsl_creator.py)

**功能描述**: 将自然语言查询转换为 Elasticsearch DSL

**调用位置**: `utils/es_dsl_creator.py:70`

**使用模型**: `qwen-plus`

**请求示例**:

```http
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
Authorization: Bearer sk-xxx
Content-Type: application/json

{
    "model": "qwen-plus",
    "temperature": 0.7,
    "messages": [
        {
            "role": "system",
            "content": "你是一个运维专家，精通ElasticSearch的使用，擅长编写各种查询语句..."
        },
        {
            "role": "system",
            "content": "当前时间为：2025-11-03 18:00:00， 聚合字段不允许添加后缀.keyword后缀"
        },
        {
            "role": "system",
            "content": "以下为表结构设计说明：{table_struct}"
        },
        {
            "role": "user",
            "content": "查询 www.baidu.com 这个域名最近100条日志原始记录"
        }
    ],
    "response_format": {
        "type": "json_object"
    }
}
```

**响应示例**:

```json
{
    "choices": [
        {
            "message": {
                "content": "{\"query\": {\"bool\": {\"must\": [{\"match\": {\"http_host\": \"www.baidu.com\"}}]}}, \"size\": 100, \"sort\": [{\"@timestamp\": {\"order\": \"desc\"}}]}"
            }
        }
    ]
}
```

---

## LLM 调用统计

| 调用场景 | 模型 | 位置 |
|----------|------|------|
| 意图识别 | qwen-flash | `agents/intent_agent.py` |
| 报告生成 | qwen-flash | `agents/report_agent.py` |
| 常规问答 | qwen-flash | `agents/guard_agent.py` |
| 工具查询 | qwen-flash | `agents/guard_agent.py` (tool_query_agent) |
| Ping 分析 | qwen-flash | `logic/server_check.py` |
| 云防分析 | qwen-flash | `logic/server_check.py` |
| Prometheus 分析 | qwen-flash | `logic/server_check.py` |
| ES 分析 | qwen-flash | `logic/server_check.py` |
| 节点报告 | qwen-plus | `logic/server_check.py` |
| ES DSL 生成 | qwen-plus | `utils/es_dsl_creator.py` |

---

## 调用方式

### 同步调用

```python
response = flash_llm.invoke([
    {"role": "user", "content": "Hello"}
])
print(response.content)
```

### 异步调用

```python
response = await flash_llm.ainvoke([
    {"role": "user", "content": "Hello"}
])
print(response.content)
```

### Agent 调用

```python
from langchain.agents import create_agent

agent = create_agent(
    flash_llm,
    tools=[es_query, get_now_time],
    system_prompt="...",
    response_format=ResponseFormat
)

response = await agent.ainvoke({
    "messages": [{"role": "user", "content": "查询最近100条日志"}]
})
```

---

## 注意事项

1. **模型选择**:
   - 简单分析任务使用 `qwen-flash`（成本低、速度快）
   - 复杂生成任务使用 `qwen-plus`（质量高）

2. **结构化输出**:
   - 意图识别使用 `response_format` 获取结构化 JSON
   - ES DSL 生成使用 `JsonOutputParser` 解析

3. **Token 限制**:
   - 注意输入/输出 token 限制
   - 长文本需要截断或分块处理

4. **费用控制**:
   - 监控 API 调用次数和 token 消耗
   - 合理选择模型避免不必要开销

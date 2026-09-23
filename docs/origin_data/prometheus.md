# Prometheus 上游接口

本文档记录工程中所有对 Prometheus 的请求接口。

## 概述

- **数据源文件**: `tools/prome_check.py`
- **客户端类**: `PrometheusAPIClient`
- **请求方式**: HTTP GET (使用 httpx.AsyncClient)
- **API 路径**: `/api/v1/query`

## 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `PROMETHEUS_API_KEY` | Prometheus API 地址 | `https://prometheus.dev.kk30.net` |

## 实例格式

默认端口为 `64998`，传入 IP 会自动补充端口：

```python
instance = f'{ip}:64998'
```

---

## 接口列表

### 1. 查询节点系统信息 (query_node_uname_info)

**功能描述**: 查询节点的操作系统基础信息

**调用位置**: `tools/prome_check.py:31`

**PromQL 查询**:

```promql
node_uname_info{instance="10.0.1.164:64998"}
```

**请求示例**:

```http
GET https://prometheus.dev.kk30.net/api/v1/query?query=node_uname_info%7Binstance%3D%2210.0.1.164%3A64998%22%7D
```

**响应示例**:

```json
{
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {
                    "instance": "10.0.1.164:64998",
                    "address": "10.0.1.164",
                    "name": "node-164",
                    "nodename": "s202-164",
                    "sysname": "Linux",
                    "machine": "x86_64",
                    "release": "5.4.0-150-generic"
                },
                "value": [1699012345, "1"]
            }
        ]
    }
}
```

**返回数据处理**:

```python
{
    'system': {
        'instance': '10.0.1.164:64998',
        'ip': '10.0.1.164',
        'name': 'node-164',
        'nodename': 's202-164',
        'sysname': 'Linux',
        'machine': 'x86_64',
        'release': '5.4.0-150-generic'
    }
}
```

---

### 2. 查询 CPU 使用率 (query_cpu_usage)

**功能描述**: 查询指定时间范围内的 CPU 使用率

**调用位置**: `tools/prome_check.py:88`

**PromQL 查询（无时间范围）**:

```promql
100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle",instance="10.0.1.164:64998"}[5m])) by (instance))
```

**PromQL 查询（有时间范围）**:

```promql
100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle",instance="10.0.1.164:64998"}[{duration_min}m])) by (instance))
```

- `duration_min` = (end_ts - start_ts) / 60

**请求示例**:

```http
GET https://prometheus.dev.kk30.net/api/v1/query?query=100%20*%20(1%20-%20avg(rate(node_cpu_seconds_total%7Bmode%3D%22idle%22%2Cinstance%3D%2210.0.1.164%3A64998%22%7D%5B5m%5D))%20by%20(instance))
```

**响应示例**:

```json
{
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {"instance": "10.0.1.164:64998"},
                "value": [1699012345, "45.23456789"]
            }
        ]
    }
}
```

**返回数据处理**:

```python
{'cpu_usage': '45.23%'}
```

---

### 3. 查询内存使用率 (query_memory_usage)

**功能描述**: 查询指定时间范围内的内存使用率

**调用位置**: `tools/prome_check.py:145`

**PromQL 查询**:

```promql
(1 - (node_memory_MemAvailable_bytes{instance="10.0.1.164:64998"} / (node_memory_MemTotal_bytes{instance="10.0.1.164:64998"}))) * 100
```

**请求示例**:

```http
GET https://prometheus.dev.kk30.net/api/v1/query?query=(1%20-%20(node_memory_MemAvailable_bytes%7Binstance%3D%2210.0.1.164%3A64998%22%7D%20%2F%20(node_memory_MemTotal_bytes%7Binstance%3D%2210.0.1.164%3A64998%22%7D)))%20*%20100&start=1699000000&end=1699010000
```

**响应示例**:

```json
{
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {"instance": "10.0.1.164:64998"},
                "value": [1699012345, "68.54321"]
            }
        ]
    }
}
```

**返回数据处理**:

```python
{'memory_usage': '68.54%'}
```

---

### 4. 查询磁盘 I/O (query_disk_io)

**功能描述**: 查询磁盘读写的瞬时速率

**调用位置**: `tools/prome_check.py:194`

**PromQL 查询（读取速率）**:

```promql
irate(node_disk_read_bytes_total{instance="10.0.1.164:64998"}[5m])
```

**PromQL 查询（写入速率）**:

```promql
irate(node_disk_written_bytes_total{instance="10.0.1.164:64998"}[5m])
```

**请求示例（读取）**:

```http
GET https://prometheus.dev.kk30.net/api/v1/query?query=irate(node_disk_read_bytes_total%7Binstance%3D%2210.0.1.164%3A64998%22%7D%5B5m%5D)
```

**请求示例（写入）**:

```http
GET https://prometheus.dev.kk30.net/api/v1/query?query=irate(node_disk_written_bytes_total%7Binstance%3D%2210.0.1.164%3A64998%22%7D%5B5m%5D)
```

**响应示例**:

```json
{
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {
                    "instance": "10.0.1.164:64998",
                    "device": "sda"
                },
                "value": [1699012345, "1234567.89"]
            },
            {
                "metric": {
                    "instance": "10.0.1.164:64998",
                    "device": "sdb"
                },
                "value": [1699012345, "987654.32"]
            }
        ]
    }
}
```

**返回数据处理**:

```python
{
    'disk_usage': {
        'sda': {
            'read_bytes_total': 1234567.89,
            'written_bytes_total': 456789.01
        },
        'sdb': {
            'read_bytes_total': 987654.32,
            'written_bytes_total': 123456.78
        }
    }
}
```

---

### 5. 查询 TCP 连接数 (query_tcp_connections)

**功能描述**: 查询当前已建立的 TCP 连接数

**调用位置**: `tools/prome_check.py:264`

**PromQL 查询**:

```promql
node_netstat_Tcp_CurrEstab{instance="10.0.1.164:64998"}
```

**请求示例**:

```http
GET https://prometheus.dev.kk30.net/api/v1/query?query=node_netstat_Tcp_CurrEstab%7Binstance%3D%2210.0.1.164%3A64998%22%7D&start=1699000000&end=1699010000
```

**响应示例**:

```json
{
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {"instance": "10.0.1.164:64998"},
                "value": [1699012345, "1234"]
            }
        ]
    }
}
```

**返回数据处理**:

```python
{'tcp_count': 1234}
```

---

### 6. 查询 TCP Socket 数 (query_tcp_sockets)

**功能描述**: 查询当前正在使用的 TCP Socket 数

**调用位置**: `tools/prome_check.py:310`

**PromQL 查询**:

```promql
node_sockstat_sockets_used{instance="10.0.1.164:64998"}
```

**请求示例**:

```http
GET https://prometheus.dev.kk30.net/api/v1/query?query=node_sockstat_sockets_used%7Binstance%3D%2210.0.1.164%3A64998%22%7D&start=1699000000&end=1699010000
```

**响应示例**:

```json
{
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {"instance": "10.0.1.164:64998"},
                "value": [1699012345, "567"]
            }
        ]
    }
}
```

**返回数据处理**:

```python
{'tcp_sockets': 567}
```

---

### 7. 查询所有信息 (query_all_info)

**功能描述**: 并发查询实例的所有监控信息

**调用位置**: `tools/prome_check.py:354`

**并发执行的查询**:
1. `query_node_uname_info` - 系统信息
2. `query_cpu_usage` - CPU 使用率
3. `query_memory_usage` - 内存使用率
4. `query_disk_io` - 磁盘 I/O
5. `query_tcp_connections` - TCP 连接数
6. `query_tcp_sockets` - TCP Socket 数

**返回数据处理**:

```python
{
    'system': {
        'instance': '10.0.1.164:64998',
        'ip': '10.0.1.164',
        'nodename': 's202-164',
        'sysname': 'Linux',
        'machine': 'x86_64',
        'release': '5.4.0-150-generic'
    },
    'cpu_usage': '45.23%',
    'memory_usage': '68.54%',
    'disk_usage': {
        'sda': {'read_bytes_total': 1234.56, 'written_bytes_total': 789.01}
    },
    'tcp_count': 1234,
    'tcp_sockets': 567
}
```

---

## PromQL 查询参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `query` | PromQL 查询语句 | `node_cpu_seconds_total{instance="10.0.1.164:64998"}` |
| `start` | 查询起始时间戳（可选） | `1699000000` |
| `end` | 查询结束时间戳（可选） | `1699010000` |

---

## 注意事项

1. **时间窗口计算**:
   - 当指定时间范围时，动态计算聚合窗口
   - `duration_min = (end_ts - start_ts) // 60`
   - 最小值为 1 分钟

2. **实例格式**:
   - 如果 IP 不包含端口，自动添加 `:64998`

3. **SSL 验证**:
   - 内网环境禁用 SSL 验证
   - `httpx.AsyncClient(verify=False)`

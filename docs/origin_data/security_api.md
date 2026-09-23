# CC/DDoS 防护 API 上游接口

本文档记录工程中所有对 CC 防护和 DDoS 防护 API 的请求接口。

## 概述

| API | 数据源文件 | 客户端类 |
|-----|-----------|---------|
| CC 防护 | `tools/cc_check.py` | `PPSChecker` |
| DDoS 防护 | `tools/ddos_check.py` | `DDOSAPIClient` |

---

# 一、CC 防护 API

## 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `CC_API_URL` | CC 防护 API 地址 | `https://yunfang.dev.example.net` |
| `CC_API_KEY` | CC 防护 API 密钥 | `xxx` |

---

## 接口列表

### 1. 获取主机网络包数据 (get_host_point)

**功能描述**: 获取指定 IP 设备的实时网络包数据信息（PPS/BPS）

**调用位置**: `tools/cc_check.py:43`

**请求方式**: GET

**请求示例**:

```http
GET https://yunfang.dev.example.net/api/host/host_point_list?key=xxx&ips=10.0.1.163,10.0.1.164
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `key` | string | 是 | API 访问密钥 |
| `ips` | string | 是 | IP 列表，逗号分隔 |

**响应示例**:

```json
{
    "code": 0,
    "msg": "success",
    "data": [
        {
            "address": "10.0.1.163",
            "input_bps": 1234567.89,
            "input_pps": 5000,
            "input_submit_bps": 1200000.00,
            "input_submit_pps": 4800,
            "output_bps": 987654.32,
            "output_pps": 3000,
            "output_submit_bps": 950000.00,
            "output_submit_pps": 2900,
            "fw_type": 1,
            "fw_id": 100
        }
    ]
}
```

**响应字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `address` | string | IP 地址 |
| `input_bps` | float | 输入流量（bits/s） |
| `input_pps` | int | 输入包速率（packets/s） |
| `input_submit_bps` | float | 过滤后输入流量 |
| `input_submit_pps` | int | 过滤后输入包速率 |
| `output_bps` | float | 输出流量 |
| `output_pps` | int | 输出包速率 |
| `output_submit_bps` | float | 过滤后输出流量 |
| `output_submit_pps` | int | 过滤后输出包速率 |
| `fw_type` | int | 防火墙类型 |
| `fw_id` | int | 防火墙 ID |

**CC 攻击判断标准**:

```python
# 以下条件同时满足视为 CC 攻击：
input_pps > 2000 and (input_pps - input_submit_pps) >= 1000
```

---

# 二、DDoS 防护 API

## 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `DDOS_API_URL` | DDoS 防护 API 地址 | `http://yunfang.dev.example.net` |
| `DDOS_API_KEY` | DDoS 防护 API 密钥 | `xxx` |
| `DDOS_TOKEN` | DDoS 认证 Token | `eyJ0eXAi...` |

---

## 接口列表

### 1. 获取 DDoS 攻击列表 (get_ddos_list)

**功能描述**: 查询指定 IP 在指定时间范围内的 DDoS 攻击记录

**调用位置**: `tools/ddos_check.py:41`

**请求方式**: GET

**请求头**:

```http
Authorization: Bearer eyJ0eXAi...
Content-Type: application/json
```

**请求示例**:

```http
GET http://yunfang.dev.example.net/api/ddos/list?ip=10.0.1.167,10.0.1.168&key=xxx&time_start=2025-11-03%2014:00:00&time_end=2025-11-03%2018:00:00&sort=-time
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `ip` | string | 是 | IP 列表，逗号分隔 |
| `key` | string | 是 | API 访问密钥 |
| `time_start` | string | 否 | 开始时间（格式：`2024-02-02 01:10:11`） |
| `time_end` | string | 否 | 结束时间 |
| `sort` | string | 否 | 排序方式：`+time`（正序）/ `-time`（倒序） |

**响应示例**:

```json
{
    "info": "成功!",
    "status": true,
    "data": [
        {
            "id": 12345,
            "ip": "10.0.1.167",
            "attack_type": "UDP Flood",
            "start_time": "2025-11-03 14:30:00",
            "end_time": "2025-11-03 14:45:00",
            "peak_bps": 1500000,
            "peak_pps": 100000,
            "status": "已结束"
        },
        {
            "id": 12346,
            "ip": "10.0.1.167",
            "attack_type": "SYN Flood",
            "start_time": "2025-11-03 16:00:00",
            "end_time": "2025-11-03 16:20:00",
            "peak_bps": 2000000,
            "peak_pps": 150000,
            "status": "已结束"
        }
    ]
}
```

**响应字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 攻击记录 ID |
| `ip` | string | 被攻击 IP |
| `attack_type` | string | 攻击类型 |
| `start_time` | string | 攻击开始时间 |
| `end_time` | string | 攻击结束时间 |
| `peak_bps` | int | 峰值流量（**注意：单位为 kbps**） |
| `peak_pps` | int | 峰值包速率 |
| `status` | string | 攻击状态 |

**DDoS 攻击判断标准**:

```python
# 流量大于 1G (1000000 kbps) 视为 DDoS 攻击
peak_bps > 1000000
```

---

## 错误响应

**CC API 错误响应**:

```json
{
    "code": -1,
    "msg": "error message",
    "data": []
}
```

**DDoS API 错误响应**:

```json
{
    "info": "失败!",
    "status": false,
    "data": []
}
```

---

## 注意事项

1. **bps 单位**:
   - DDoS API 返回的 `peak_bps` 单位为 **kbps**，不是 bps
   - 判断时需注意单位换算

2. **认证方式**:
   - CC API：使用 `key` 参数认证
   - DDoS API：使用 `Authorization: Bearer` 头 + `key` 参数双重认证

3. **SSL 验证**:
   - 内网环境禁用 SSL 验证

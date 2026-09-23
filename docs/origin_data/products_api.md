# WAF/高防产品 API 上游接口

本文档记录工程中所有对 WAF 和高防产品管理 API 的请求接口。

## 概述

- **数据源文件**: `logic/server_check.py`
- **客户端类**: `ServerQueryClient`
- **用途**: 根据域名查询关联的节点 IP 列表

## 产品分类

| 产品类型 | 说明 | 来源标识 |
|----------|------|----------|
| WAF | Web 应用防火墙 | `source='WAF'` |
| 游戏盾 | 高防产品 - 游戏盾 | `source='GF'` |
| 高防IP | 高防产品 - CDN 加速 | `source='GF'` |
| DDoS 高防 | 高防产品 - DDoS 防护 | `source='GF'` |

---

# 一、WAF 产品 API

## 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `WAF_API_URL` | WAF 管理 API 地址 | `https://kk_waf_admin.dev.kk30.net` |
| `WAF_API_TOKEN` | WAF API 访问 Token | `xxx` |
| `ENVIRONMENT` | 运行环境 | `dev` / `prod` |

---

## 接口列表

### 1. 根据域名查询节点 IP (waf_query_ip_by_domain)

**功能描述**: 根据域名查询 WAF 产品关联的所有节点 IP

**调用位置**: `logic/server_check.py:119`

**请求方式**: GET

**请求头**:

```http
X-Access-Token: {WAF_API_TOKEN}
```

**请求示例**:

```http
GET https://kk_waf_admin.dev.kk30.net/api/security_assistant/get_node_ips?domain=example.com&time_stamp=1699012345
X-Access-Token: xxx
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `domain` | string | 是 | 要查询的域名 |
| `time_stamp` | int | 是 | 当前时间戳 |

**响应示例**:

```json
{
    "code": 0,
    "msg": "success",
    "data": [
        {
            "node_ip": "10.0.1.164",
            "ip_list": ["10.0.1.164", "10.0.1.165", "10.0.1.166"]
        }
    ]
}
```

**响应字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `node_ip` | string | 主节点 IP |
| `ip_list` | array | 关联的所有 IP 列表 |

**数据处理逻辑**:

```python
for item in nodes:
    node_ip = item.get('node_ip')
    # 主节点 IP 标记为 node_product 类型
    node = NodeMachine(ip=node_ip, type="node_product", source="WAF")
    self.nodes.append(node)

    for ip in item.get("ip_list", []):
        if ip == node_ip:
            continue
        # 其他 IP 标记为 product 类型
        self.nodes.append(NodeMachine(ip=ip, type="product", source="WAF"))
```

**开发环境 Mock 数据**:

```python
if env == 'dev':
    if domain == '1014wgr01.kktest.com.cn':
        self.nodes = [NodeMachine(ip='10.0.1.164', type="node_product", source="WAF")]
    return
```

---

# 二、高防产品 API

高防产品包含三个子产品，查询顺序为：游戏盾 → 高防 IP → DDoS

## 环境变量

### 游戏盾

| 变量名 | 说明 |
|--------|------|
| `GF_YXD_API_URL` | 游戏盾 API 地址 |
| `GF_YXD_API_XTOKEN` | 游戏盾访问 Token |

### 高防IP

| 变量名 | 说明 |
|--------|------|
| `GF_CDN_API_URL` | 高防 IP API 地址 |
| `GF_CDN_API_XTOKEN` | 高防 IP 访问 Token |

### DDoS 高防

| 变量名 | 说明 |
|--------|------|
| `GF_DDOS_API_URL` | DDoS 高防 API 地址 |
| `GF_DDOS_API_XTOKEN` | DDoS 高防访问 Token |

---

## 接口列表

### 1. 根据域名查询节点 IP (gf_query_ip_by_domain)

**功能描述**: 依次查询高防三个产品，获取域名关联的节点 IP

**调用位置**: `logic/server_check.py:88`

**查询顺序**:
1. 游戏盾 (`GF_YXD_API_URL`)
2. 高防 IP (`GF_CDN_API_URL`)
3. DDoS 高防 (`GF_DDOS_API_URL`)

任一接口返回数据则停止查询。

---

### 2. 单个高防产品查询 (_gf_query_by_domain)

**功能描述**: 查询单个高防产品的节点 IP

**调用位置**: `logic/server_check.py:66`

**请求方式**: GET

**请求头**:

```http
x-token: {product_token}
```

**请求示例（游戏盾）**:

```http
GET http://kk_yxd_admin.dev.kk30.net/api/p_domainRule/getNodeIpList?domains=example.com
x-token: xxx
```

**请求示例（高防 IP）**:

```http
GET http://kk_cdn_admin.dev.kk30.net/api/p_domainRule/getNodeIpList?domains=example.com
x-token: xxx
```

**请求示例（DDoS 高防）**:

```http
GET http://kk_ddos_admin.dev.kk30.net/api/p_domainRule/getNodeIpList?domains=example.com
x-token: xxx
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `domains` | string | 是 | 要查询的域名 |

**响应示例**:

```json
{
    "code": 0,
    "msg": "success",
    "data": [
        {
            "node_ip": "10.0.1.170",
            "ip_list": ["10.0.1.170", "10.0.1.171"]
        }
    ]
}
```

**数据处理逻辑**:

```python
for item in items:
    node_ip = item.get('node_ip')
    # 主节点 IP 标记为 node_product 类型
    node = NodeMachine(ip=node_ip, type="node_product", source='GF')
    self.nodes.append(node)

    ip_list = item.get("ip_list")
    for ip in ip_list:
        if ip == node_ip:
            continue
        # 其他 IP 标记为 product 类型
        self.nodes.append(NodeMachine(ip=ip, type="product", source='GF'))
```

---

## 完整查询流程

```python
def gf_query_ip_by_domain(self, domain: str):
    """根据域名查询高防服务器IP"""

    # 1. 查询游戏盾
    yxd_url = f"{os.getenv('GF_YXD_API_URL')}/api/p_domainRule/getNodeIpList"
    yxd_token = os.getenv('GF_YXD_API_XTOKEN')
    found = self._gf_query_by_domain(yxd_url, yxd_token, domain)
    if found:
        return

    # 2. 查询高防 IP
    cdn_url = f"{os.getenv('GF_CDN_API_URL')}/api/p_domainRule/getNodeIpList"
    cdn_token = os.getenv('GF_CDN_API_XTOKEN')
    found = self._gf_query_by_domain(cdn_url, cdn_token, domain)
    if found:
        return

    # 3. 查询 DDoS 高防
    ddos_url = f"{os.getenv('GF_DDOS_API_URL')}/api/p_domainRule/getNodeIpList"
    ddos_token = os.getenv('GF_DDOS_API_XTOKEN')
    self._gf_query_by_domain(ddos_url, ddos_token, domain)
```

---

## 节点类型说明

| type | 说明 | Prometheus | CC/DDoS |
|------|------|------------|---------|
| `node` | 纯节点 IP | 是 | 否 |
| `product` | 产品 IP | 否 | 是 |
| `node_product` | 既是节点又是产品 | 是 | 是 |

---

## 产品查询优先级

```
用户输入域名
    │
    ▼
┌─────────────────┐
│ 查询高防产品     │
│ (游戏盾→高防IP→DDoS)│
└────────┬────────┘
         │
    有数据？
    │    │
   是    否
    │     │
    ▼     ▼
  返回  ┌─────────────────┐
        │ 查询 WAF 产品    │
        └────────┬────────┘
                 │
            有数据？
            │    │
           是    否
            │     │
            ▼     ▼
          返回   返回错误
```

---

## 注意事项

1. **互斥关系**:
   - 高防与 WAF 属于互斥产品
   - 一个域名不可能同时属于高防和 WAF

2. **SSL 验证**:
   - 使用 `requests.get(..., verify=False)` 禁用 SSL 验证

3. **开发环境**:
   - 开发环境使用 Mock 数据
   - 通过 `ENVIRONMENT` 环境变量判断

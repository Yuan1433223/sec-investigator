# 飞书 API 上游接口

本文档记录工程中所有对飞书 API 的请求接口。

## 概述

- **数据源文件**: `utils/feishu.py`
- **客户端类**: `FeiShuClient`
- **SDK**: `lark-oapi` (飞书官方 SDK)
- **用途**: 将问答日志记录到飞书多维表格

## 环境变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `FEISHU_APP_ID` | 飞书应用 ID | `cli_xxx` |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | `xxx` |
| `FEISHU_TABLE_ID` | 多维表格 ID | `tbl_xxx` |
| `FEISHU_TABLE_APP_TOKEN` | 多维表格 App Token | `xxx` |

---

## 接口列表

### 1. 获取知识库节点信息 (_get_obj_token)

**功能描述**: 获取知识库 wiki 中多维表格的真实 token

**调用位置**: `utils/feishu.py:39`

**说明**:
- 如果 URL 中 token 前为 `wiki`，表示该云文档挂载在知识库中
- URL 中的 token 是知识库节点的 `node_token`
- 需要调用此接口获取实际的 `obj_token`

**SDK 调用**:

```python
from lark_oapi.api.wiki.v2 import GetNodeSpaceRequest, GetNodeSpaceResponse

request: GetNodeSpaceRequest = GetNodeSpaceRequest.builder() \
    .token(self.log_table_app_token) \
    .build()

response: GetNodeSpaceResponse = self.client.wiki.v2.space.get_node(request)
```

**等效 HTTP 请求**:

```http
GET https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?token={node_token}
Authorization: Bearer {tenant_access_token}
```

**响应示例**:

```json
{
    "code": 0,
    "msg": "success",
    "data": {
        "node": {
            "space_id": "6946843325487456276",
            "node_token": "wikcnKQ1k3p******8Vabcef",
            "obj_token": "bascnCMII2ORej2RItqpZZUNMIe",
            "obj_type": "bitable",
            "parent_node_token": "wikcnKQ1k3p******8Vabcxx",
            "node_type": "origin",
            "origin_node_token": "wikcnKQ1k3p******8Vabcef",
            "origin_space_id": "6946843325487456276",
            "has_child": false,
            "title": "问答日志表"
        }
    }
}
```

---

### 2. 多维表格插入记录 (table_insert_record)

**功能描述**: 向多维表格中插入一条新记录

**调用位置**: `utils/feishu.py:59`

**SDK 调用**:

```python
from lark_oapi.api.bitable.v1 import CreateAppTableRecordRequest, CreateAppTableRecordResponse, AppTableRecord

request: CreateAppTableRecordRequest = CreateAppTableRecordRequest.builder() \
    .app_token(self.wiki_obj_token) \
    .table_id(self.log_table_id) \
    .user_id_type('union_id') \
    .client_token(str(uuid4())) \
    .ignore_consistency_check(True) \
    .request_body(AppTableRecord.builder().fields(row_data).build()) \
    .build()

response: CreateAppTableRecordResponse = await self.client.bitable.v1.app_table_record.acreate(request)
```

**等效 HTTP 请求**:

```http
POST https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records
Authorization: Bearer {tenant_access_token}
Content-Type: application/json

{
    "fields": {
        "用户ID": "user123",
        "问题": "分析 example.com 的状态"
    }
}
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `app_token` | string | 是 | 多维表格 App Token |
| `table_id` | string | 是 | 表格 ID |
| `user_id_type` | string | 否 | 用户 ID 类型（union_id/open_id） |
| `client_token` | string | 否 | 幂等 Token（UUID） |
| `fields` | object | 是 | 记录字段数据 |

**响应示例**:

```json
{
    "code": 0,
    "msg": "success",
    "data": {
        "record": {
            "record_id": "recxxxxxx",
            "fields": {
                "用户ID": "user123",
                "问题": "分析 example.com 的状态"
            }
        }
    }
}
```

---

### 3. 多维表格更新记录 (table_update_record)

**功能描述**: 更新多维表格中的现有记录

**调用位置**: `utils/feishu.py:83`

**SDK 调用**:

```python
from lark_oapi.api.bitable.v1 import UpdateAppTableRecordRequest, UpdateAppTableRecordResponse, AppTableRecord

request: UpdateAppTableRecordRequest = UpdateAppTableRecordRequest.builder() \
    .app_token(self.wiki_obj_token) \
    .table_id(self.log_table_id) \
    .record_id(record_id) \
    .user_id_type("open_id") \
    .ignore_consistency_check(True) \
    .request_body(AppTableRecord.builder().fields(row_data).build()) \
    .build()

response: UpdateAppTableRecordResponse = await self.client.bitable.v1.app_table_record.aupdate(request)
```

**等效 HTTP 请求**:

```http
PUT https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}
Authorization: Bearer {tenant_access_token}
Content-Type: application/json

{
    "fields": {
        "回答": "## 一、建议与结论\n...",
        "节点信息": "{...}",
        "网站信息": "{...}"
    }
}
```

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `app_token` | string | 是 | 多维表格 App Token |
| `table_id` | string | 是 | 表格 ID |
| `record_id` | string | 是 | 记录 ID |
| `fields` | object | 是 | 要更新的字段数据 |

**响应示例**:

```json
{
    "code": 0,
    "msg": "success",
    "data": {
        "record": {
            "record_id": "recxxxxxx",
            "fields": {
                "用户ID": "user123",
                "问题": "分析 example.com 的状态",
                "回答": "## 一、建议与结论\n...",
                "节点信息": "{...}",
                "网站信息": "{...}"
            }
        }
    }
}
```

---

### 4. 保存问答日志 (save_chat_log)

**功能描述**: 将完整的问答记录异步写入飞书多维表格

**调用位置**: `utils/feishu.py:109`

**工作流程**:

```
1. 调用 table_insert_record 插入初始记录（用户ID + 问题）
      │
2. 获取返回的 record_id
      │
3. 调用 table_update_record 更新记录（回答 + 节点信息 + 网站信息）
```

**记录字段**:

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `用户ID` | text | 提问用户的 ID |
| `问题` | text | 用户提出的问题 |
| `回答` | text | AI 生成的 Markdown 回答 |
| `节点信息` | text | 节点诊断数据（JSON 字符串） |
| `网站信息` | text | ES 聚合数据（JSON 字符串） |

**使用示例**:

```python
# 在 main.py 中作为后台任务调用
from utils.feishu import FeiShuClient

feishu_client = FeiShuClient()

background_tasks.add_task(
    feishu_client.save_chat_log,
    user_id="user123",
    question="分析 example.com 的状态",
    answer="## 一、建议与结论\n...",
    node_info=[{"ip": "10.0.1.164", ...}],
    server_info={"domain": "example.com", ...}
)
```

---

## 错误处理

**SDK 错误响应**:

```python
if not response.success():
    logger.error(
        f"API failed, code: {response.code}, msg: {response.msg}, "
        f"log_id: {response.get_log_id()}"
    )
```

**常见错误码**:

| 错误码 | 说明 |
|--------|------|
| 99991663 | 无权限访问该资源 |
| 99991664 | 资源不存在 |
| 99991665 | 请求参数错误 |
| 99991668 | 记录不存在 |

---

## 注意事项

1. **知识库表格**:
   - 挂载在知识库中的表格需要先获取 `obj_token`
   - 直接使用 URL 中的 token 会导致权限错误

2. **异步调用**:
   - 使用 `acreate` 和 `aupdate` 进行异步操作
   - 配合 FastAPI 的 `BackgroundTasks` 使用

3. **幂等性**:
   - 插入记录时使用 `client_token` (UUID) 保证幂等
   - 避免重复插入相同记录

4. **JSON 序列化**:
   - `node_info` 和 `server_info` 需要序列化为 JSON 字符串
   - 使用 `json.dumps(data, indent=4, ensure_ascii=False)`

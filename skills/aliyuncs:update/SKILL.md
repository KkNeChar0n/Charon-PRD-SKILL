---
name: aliyuncs:update
description: 根据当前需求和任务完成情况，批量更新云效中需求、任务、子任务的状态
user_invocable: true
---

# 更新需求和任务状态

当用户执行 `/aliyuncs:update` 时，执行以下步骤：

## 工作流校验

读取 `.aliyuncs.json`，校验配置完整且 `requirements` 或 `tasks` 中至少有一项不为空。

## SDK 初始化

```python
from alibabacloud_devops20210625.client import Client
from alibabacloud_tea_openapi.models import Config

config = Config(
    access_key_id=accessKeyId,
    access_key_secret=accessKeySecret,
    endpoint='devops.cn-hangzhou.aliyuncs.com'
)
client = Client(config)
```

## 步骤 1：获取当前状态

遍历所有需求、任务、子任务，查询最新状态：

```python
response = client.get_work_item_info(organizationId, workitemIdentifier)
wi = response.body.workitem
# wi.status 是状态名称（如"待处理"、"已完成"）
# wi.status_stage_identifier 是阶段标识
```

## 步骤 2：展示状态总览

以树形结构展示所有工作项状态，然后用 AskUserQuestion 询问用户要更新哪些。

## 步骤 3：获取可用状态列表

```python
from alibabacloud_devops20210625.models import GetWorkItemWorkFlowInfoRequest

req = GetWorkItemWorkFlowInfoRequest(configuration_id='')
response = client.get_work_item_work_flow_info(organizationId, workitemIdentifier, req)
# 遍历 response.body.workflow.statuses
# 每个状态有：.name, .identifier, .workflow_stage_identifier, .workflow_stage_name
```

已知状态 identifier：

**通用（需求/任务都有）：**
- `100005` = 待处理（确认阶段）
- `100014` = 已完成（正常结束）
- `141230` = 已取消（异常结束）

**仅需求类型（Req）：**
- `156603` = 设计中（设计阶段）
- `1f49991e2d9aa8296eed3ec251` = 待开发（开发阶段）
- `142838` = 开发中（开发阶段）
- `100012` = 测试中（测试阶段）

**仅任务类型（Task）：**
- `100010` = 处理中（处理阶段）

> 上述列表来自本项目 IDigiTrust 实际工作流；其他项目可能略有不同。若用户提到的状态名不在此清单，先调用 `GetWorkItemWorkFlowInfoRequest` 查询对应工作项的可用状态列表（见步骤 3）拿到真实 identifier 后再更新。

## 步骤 4：执行状态更新

**重要**：`update_work_item` 的签名是 `(organization_id, request)`，workitem identifier 在 request 内部，不是单独的参数。

```python
from alibabacloud_devops20210625.models import UpdateWorkItemRequest

request = UpdateWorkItemRequest(
    identifier=workitemIdentifier,  # 工作项ID放在 request 里
    field_type='status',
    property_key='status',
    property_value='100014'  # 目标状态的 identifier
)
client.update_work_item(organizationId, request)  # 只传2个参数！
```

**每次调用间加 `time.sleep(0.2)` 避免限流。**

### `field_type` 支持的字段（同一 API 可改多种字段）

`update_work_item` 是一个通用字段更新接口，`field_type` 决定改什么字段，`property_value` 是新值：

| field_type | 用途 | property_value 形态 |
|------------|------|---------------------|
| `status` | 修改工作项状态 | 状态 identifier（见上一节清单） |
| `subject` | 修改工作项标题 | 新标题字符串 |
| `description` | 修改工作项描述（含追加） | 完整描述文本（Markdown / 富文本 HTML 均可） |

**`description` 用法（含追加场景）**：

云效需求描述存在 `workitem.document` 字段。若是用 SDK 创建（如 `create_workitem_v2` 时传 `description=...`）的需求，document 字段就是纯文本/Markdown；若是用户在云效 UI 里写的，document 是 JSON 包裹的富文本（`{"htmlValue": "...", "jsonMLValue": [...]}`）。

要追加内容到现有描述（不覆盖原文），必须先读后写：

```python
# 1. 读取现有描述
resp = client.get_work_item_info(organizationId, workitemIdentifier)
original = resp.body.workitem.document or ''

# 2. 拼接新内容（追加 Markdown 二级标题）
new_content = original.rstrip() + '\n\n## 新增段落标题\n- 新增内容第 1 行\n- 新增内容第 2 行\n'

# 3. 写回（property_key 与 field_type 一致）
request = UpdateWorkItemRequest(
    identifier=workitemIdentifier,
    field_type='description',
    property_key='description',
    property_value=new_content,
)
client.update_work_item(organizationId, request)
```

**注意**：
- `property_value` 是**全量**写回，不是 patch。所以追加内容必须先读出 original 再拼接。
- 如果原 description 是 JSON 富文本格式，直接传 Markdown 文本写回会丢失富文本结构，但内容仍可正常展示。
- 对于多次反复追加的场景，建议用一个固定的小标题（如 `## 本期暂未规划`）作为锚点，便于幂等替换该锚点段而不是一直往末尾堆。

## 步骤 5：更新本地配置

将状态变更同步到 `.aliyuncs.json`。

## 步骤 6：输出变更摘要

表格展示：工作项 | 原状态 | 新状态 | 结果

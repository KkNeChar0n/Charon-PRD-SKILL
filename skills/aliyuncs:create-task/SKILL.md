---
name: aliyuncs:create-task
description: 根据已创建的需求拆解研发任务，每个任务下自动创建前端/后端/测试子任务
user_invocable: true
---

# 根据需求创建研发任务

当用户执行 `/aliyuncs:create-task` 时，执行以下步骤：

## 工作流校验

读取 `.aliyuncs.json`，依次校验：
1. 文件存在且包含完整配置（含 staffAccountId）
2. `currentIteration` 不为 null
3. `requirements` 数组不为空

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

## 步骤 1：选择父需求

列出所有需求，多个时用 AskUserQuestion 让用户选择。

## 步骤 2：拆解研发任务

根据对话上下文拆解任务列表，展示给用户确认：
- 子任务命名规则：`父任务名称 + ' - ' + 前端/后端/测试`
- 根据任务性质决定子任务类型（纯后端只需后端+测试，纯前端只需前端+测试）

## 步骤 3：获取任务类型

```python
from alibabacloud_devops20210625.models import ListProjectWorkitemTypesRequest

request = ListProjectWorkitemTypesRequest(space_type='Project', category='Task')
response = client.list_project_workitem_types(organizationId, spaceIdentifier, request)
# 找 category_identifier == 'Task' 的，取其 .identifier
```

## 步骤 4：创建任务和子任务

**重要**：`assigned_to` 必填，响应用 `body.workitem_identifier`。

创建父任务（挂在需求下）：
```python
from alibabacloud_devops20210625.models import CreateWorkitemV2Request

request = CreateWorkitemV2Request(
    subject='任务名称',
    space_identifier=spaceIdentifier,
    category='Task',
    workitem_type_identifier=taskTypeIdentifier,
    parent_identifier=requirementIdentifier,  # 父需求ID
    sprint_identifier=currentIteration['identifier'],
    assigned_to=staffAccountId  # 必填！
)
response = client.create_workitem_v2(organizationId, request)
task_id = response.body.workitem_identifier  # 注意：直接在 body 上，不是 body.workitem
```

创建子任务（挂在父任务下）：
```python
request = CreateWorkitemV2Request(
    subject='父任务名称 - 前端',
    space_identifier=spaceIdentifier,
    category='Task',
    workitem_type_identifier=taskTypeIdentifier,
    parent_identifier=taskId,  # 父任务ID
    sprint_identifier=currentIteration['identifier'],
    assigned_to=staffAccountId  # 必填！
)
response = client.create_workitem_v2(organizationId, request)
sub_task_id = response.body.workitem_identifier
```

**建议**：每次 API 调用之间加 `time.sleep(0.3)` 避免限流。

## 步骤 5：更新本地配置

将任务信息追加到 `.aliyuncs.json` 的对应需求的 `tasks` 和顶层 `tasks` 数组。

## 步骤 6：输出结果

以表格形式展示创建的所有任务和子任务。

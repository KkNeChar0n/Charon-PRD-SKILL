---
name: aliyuncs:init
description: 初始化阿里云云效项目配置，记录组织ID、项目标识、项目名称、AccessKey ID/Secret等信息
user_invocable: true
---

# 初始化阿里云云效项目

当用户执行 `/aliyuncs:init` 时，执行以下步骤：

## 步骤 1：收集配置信息

使用 AskUserQuestion 工具依次向用户询问以下信息（如果用户在命令后直接提供了参数则跳过询问）：

1. **组织ID（organizationId）**：阿里云云效的企业/组织ID，通常可在云效 URL 中找到
2. **项目标识（spaceIdentifier）**：云效项目的唯一标识符
3. **项目名称（projectName）**：云效项目的显示名称，用于迭代命名等场景
4. **AccessKey ID（accessKeyId）**：阿里云 AccessKey ID，在阿里云控制台「AccessKey 管理」中创建
5. **AccessKey Secret（accessKeySecret）**：与 AccessKey ID 配对的密钥

每个字段单独询问，给出简短说明帮助用户找到对应值。

## 步骤 2：验证配置

确认用户输入的信息非空且格式合理。

## 步骤 3：获取当前用户 accountId

使用 SDK 获取组织成员列表，取第一个成员的 `account_id` 作为 `staffAccountId`：

```python
from alibabacloud_devops20210625.client import Client
from alibabacloud_tea_openapi.models import Config
from alibabacloud_devops20210625.models import ListOrganizationMembersRequest

config = Config(
    access_key_id=accessKeyId,
    access_key_secret=accessKeySecret,
    endpoint='devops.cn-hangzhou.aliyuncs.com'
)
client = Client(config)

request = ListOrganizationMembersRequest(next_token='', max_results=5)
response = client.list_organization_members(organizationId, request)
staff_account_id = response.body.members[0].account_id
```

## 步骤 4：保存配置

将配置信息写入项目根目录的 `.aliyuncs.json` 文件：

```json
{
  "organizationId": "组织ID",
  "spaceIdentifier": "项目标识",
  "projectName": "项目名称",
  "accessKeyId": "AccessKey ID",
  "accessKeySecret": "AccessKey Secret",
  "apiBase": "https://devops.aliyun.com",
  "staffAccountId": "自动获取的accountId",
  "currentIteration": null,
  "requirements": [],
  "tasks": []
}
```

## 步骤 5：更新 .gitignore

确保 `.aliyuncs.json` 在 `.gitignore` 中，因为配置文件包含 AccessKey 密钥。

## 步骤 6：确认完成

输出配置摘要（隐藏密钥），告知工作流顺序：
1. `/aliyuncs:create-iteration` — 创建迭代
2. `/aliyuncs:create-requirement` — 创建需求
3. `/aliyuncs:create-task` — 拆解任务
4. `/aliyuncs:update` — 更新状态
5. `/aliyuncs:finish-iteration` — 清理迭代

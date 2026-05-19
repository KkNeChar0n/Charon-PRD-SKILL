---
name: prd-feishu-init
description: 初始化飞书 PRD 接入配置。引导用户填入飞书自建应用的 App ID / App Secret（可选填默认文件夹 token），验证凭证有效性，并将配置持久化到 ~/.prd-feishu/config.json，供 prd-feishu skill 长期使用。
argument-hint: ""
allowed-tools: Read, Write, Bash, AskUserQuestion
---

# 飞书 PRD 接入初始化

引导用户完成飞书自建应用凭证的配置，让后续 `prd-feishu` skill 可以无密码生成飞书文档。

## 前置说明

**用户需先在飞书开放平台创建一个自建应用并开启相关权限。** 引导步骤：

1. 访问 https://open.feishu.cn/app
2. 点击「创建企业自建应用」
3. 填写应用名称、说明、上传 logo
4. 创建后进入应用，记下 **App ID** 和 **App Secret**（在「凭证与基础信息」页面）
5. 在「权限管理」开启以下权限：
   - `docx:document` — 查看、评论、编辑和管理云文档
   - `docx:document:create` — 创建及编辑新版文档
   - `drive:drive` — 查看、评论、编辑和管理云空间中所有文件（仅用于上传图片素材）
   - `docx:document:readonly` — 查看新版文档（可选，仅查看时需要）
   - 注：图片上传依赖 `drive:drive`，最低也需要 `drive:file:upload` 权限
6. 点击「版本管理与发布」→ 创建版本 → 等待管理员审核通过（自建应用一般是开发者自己审核）

⚠️ 重要：自建应用需要发布并通过审核后才能调用 API。开发阶段可以创建一个仅自己可见的版本。

## 步骤

### 步骤 1：检查现有配置

```bash
CONFIG_PATH="$HOME/.prd-feishu/config.json"
if [ -f "$CONFIG_PATH" ]; then
  echo "已存在配置文件，内容如下："
  cat "$CONFIG_PATH" | python3 -m json.tool
  echo ""
  echo "重新初始化将覆盖原配置。"
fi
```

如果存在配置，用 AskUserQuestion 询问用户是否覆盖。若用户选择否则结束。

### 步骤 2：收集凭证

使用 AskUserQuestion 工具依次询问：

1. **App ID**（必填）—— 飞书自建应用的 App ID，通常以 `cli_` 开头
2. **App Secret**（必填）—— 飞书自建应用的 App Secret
3. **默认文件夹 token**（可选）—— 飞书云空间中某个文件夹的 token，留空则文档默认放在应用根目录
4. **App 所属域名**（可选，默认 `open.feishu.cn`）—— 国际版用户可填 `open.larksuite.com`

「文件夹 token 获取方法」：打开飞书云空间 → 进入目标文件夹 → 浏览器地址栏 URL 形如 `https://xxx.feishu.cn/drive/folder/{folder_token}`，最后一段就是 folder_token。

如果用户输入的 App ID 不以 `cli_` 开头，提醒一次但不强制阻断（飞书可能调整命名规则）。

### 步骤 3：验证凭证

用 curl 调用 `/auth/v3/tenant_access_token/internal` 换取 token，确认 App ID 和 App Secret 有效：

```bash
DOMAIN="${app_domain:-open.feishu.cn}"
RESP=$(curl -s -X POST "https://$DOMAIN/open-apis/auth/v3/tenant_access_token/internal" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "{\"app_id\":\"$APP_ID\",\"app_secret\":\"$APP_SECRET\"}")
echo "$RESP"
```

预期响应（成功）：
```json
{
  "code": 0,
  "msg": "ok",
  "tenant_access_token": "t-g1044...",
  "expire": 7200
}
```

如果 `code != 0`：
- `10003` / `99991663`：App ID 或 App Secret 错误，让用户重新输入
- `99991660`：应用未发布或权限不足，让用户去开放平台检查应用状态
- 其他：把完整 `msg` 显示给用户

验证成功才进入下一步。

### 步骤 3.5：验证 folder_token（如果用户填了）

```bash
# 试探性创建一个名为 "_perm_test_可删除" 的空文档到该文件夹
TEST_RESP=$(curl -s -X POST "https://$DOMAIN/open-apis/docx/v1/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "{\"title\":\"_perm_test_可删除\",\"folder_token\":\"$FOLDER_TOKEN\"}")
```

- 成功（code=0）：删掉测试文档（DELETE /open-apis/drive/v1/files/{token}），继续步骤 4
- 失败 `1770040 no folder permission`：提示用户「该文件夹未授权给应用，请去飞书云空间打开该文件夹 → 分享 → 协作者管理 → 添加应用名为协作者并赋『可编辑』权限。完成后告诉我重试」。**不要写入 config，让用户处理完再重跑**。
- 失败 `1061004 forbidden`：folder_token 错误或文件夹已删除，提示用户重新填写

### 步骤 4：写入配置

```bash
mkdir -p "$HOME/.prd-feishu"
cat > "$CONFIG_PATH" <<EOF
{
  "app_id": "$APP_ID",
  "app_secret": "$APP_SECRET",
  "default_folder_token": "$FOLDER_TOKEN",
  "app_domain": "$DOMAIN",
  "initialized_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
chmod 600 "$CONFIG_PATH"
```

`chmod 600` 让配置文件仅当前用户可读（保护 Secret）。

### 步骤 5：输出确认信息

向用户报告：
- ✓ 配置已写入 `~/.prd-feishu/config.json`
- ✓ 凭证已通过飞书 API 验证
- 提示下一步：使用 `/prd-feishu <需求描述>` 生成 PRD 并自动上传到飞书

如果用户没填默认文件夹 token，提醒「文档将创建在应用空间根目录，可后续在飞书里手动移动」。

## 配置文件结构

```json
{
  "app_id": "cli_xxxxxxxxxxxx",
  "app_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "default_folder_token": "fldcnxxxxxxxxx",
  "app_domain": "open.feishu.cn",
  "initialized_at": "2026-05-13T10:30:00Z"
}
```

## 安全注意事项

- App Secret 是敏感凭证，**不要打印到终端或日志中**
- 配置文件权限设为 `600`（仅用户可读写）
- 如果 Secret 泄露，立即去飞书开放平台「凭证与基础信息」点「重置」生成新 Secret，并重新跑本 skill

## 错误处理

- 用户提供的 App ID / Secret 错误 → 显示具体错误，让用户重新输入
- 飞书域名不可达 → 提示检查网络
- 配置目录创建失败 → 提示用户检查 ~/.prd-feishu 父目录权限
- 用户中途取消 → 不写入任何文件，提示「未初始化，可重新运行 /prd-feishu-init」

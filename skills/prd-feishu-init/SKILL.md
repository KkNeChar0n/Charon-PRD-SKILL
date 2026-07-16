---
name: prd-feishu-init
description: 初始化飞书 PRD 接入配置。引导用户填入飞书自建应用的 App ID / App Secret（可选填默认知识库父节点 URL），验证凭证有效性，并将配置持久化到 ~/.prd-feishu/config.json，供 prd-feishu skill 长期使用。PRD 以知识库（Wiki）子节点形式发布，而非云空间文件夹。
argument-hint: ""
allowed-tools: Read, Write, Bash, AskUserQuestion
---

# 飞书 PRD 接入初始化

引导用户完成飞书自建应用凭证的配置，让后续 `prd-feishu` skill 可以无密码生成飞书文档。

> **重要：本 skill 面向飞书「知识库（Wiki）」，不是云空间文件夹。** PRD 文档以子节点形式挂在某个知识库父节点下面。因此默认位置用一个 **知识库节点 URL** 来定位（形如 `https://xxx.feishu.cn/wiki/{node_token}`），不再需要也不要填「文件夹 token」。

## 前置说明

**用户需先在飞书开放平台创建一个自建应用并开启相关权限。** 引导步骤：

1. 访问 https://open.feishu.cn/app
2. 点击「创建企业自建应用」
3. 填写应用名称、说明、上传 logo
4. 创建后进入应用，记下 **App ID** 和 **App Secret**（在「凭证与基础信息」页面）
5. 在「权限管理」开启以下权限：
   - `wiki:wiki` — 查看、编辑和管理知识库（**必须**，PRD 作为知识库子节点创建/读取都依赖它）
   - `docx:document` — 查看、评论、编辑和管理云文档
   - `docx:document:create` — 创建及编辑新版文档
   - `drive:drive` — 查看、评论、编辑和管理云空间中所有文件（用于上传图片素材）
   - `docx:document:readonly` — 查看新版文档（可选，仅查看时需要）
   - 注：图片上传依赖 `drive:drive`，最低也需要 `drive:file:upload` 权限
6. 点击「版本管理与发布」→ 创建版本 → 等待管理员审核通过（自建应用一般是开发者自己审核）
7. **把应用加为目标知识库的管理员/可编辑成员**：打开知识库 → 设置 → 成员管理 → 添加应用（按应用名搜索）并给「可编辑」及以上权限。否则调用 wiki API 会 `forbidden`。

⚠️ 重要：自建应用需要发布并通过审核后才能调用 API。开发阶段可以创建一个仅自己可见的版本。

## 步骤

### 步骤 1：检查现有配置

```bash
CONFIG_PATH="$HOME/.prd-feishu/config.json"
if [ -f "$CONFIG_PATH" ]; then
  echo "已存在配置文件，内容如下："
  python3 -c "import json;d=json.load(open('$CONFIG_PATH'));d['app_secret']='***'+str(d.get('app_secret',''))[-4:];print(json.dumps(d,ensure_ascii=False,indent=2))"
  echo ""
  echo "重新初始化将覆盖原配置。"
fi
```

如果存在配置，用 AskUserQuestion 询问用户是否覆盖。若用户选择否则结束。

### 步骤 2：收集凭证

使用 AskUserQuestion 工具依次询问：

1. **App ID**（必填）—— 飞书自建应用的 App ID，通常以 `cli_` 开头
2. **App Secret**（必填）—— 飞书自建应用的 App Secret
3. **默认知识库父节点 URL**（可选）—— 直接粘贴一个知识库节点链接来定位默认位置，留空则不设默认父节点（后续用 `/prd-feishu` 时需逐次传 URL，或由 `.aliyuncs.json` 解析）
4. **App 所属域名**（可选，默认 `open.feishu.cn`）—— 国际版用户可填 `open.larksuite.com`

「知识库节点 URL 获取方法」：在飞书里打开目标知识库 → 进入（或新建）一个作为 PRD 归档父节点的页面 → 复制浏览器地址栏 URL，形如 `https://xxx.feishu.cn/wiki/{node_token}`（`?` 后面的查询参数可不管）。**整条 URL 粘进来即可，我会自动解析出 node_token。**

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

验证成功才进入下一步。把成功换到的 `tenant_access_token` 存入变量 `TOKEN` 供下一步使用。

### 步骤 3.5：解析并验证知识库父节点 URL（如果用户填了）

**先从 URL 解析出 node_token**（取 `/wiki/` 后面那一段，去掉查询参数）：

```bash
# PARENT_URL 是用户粘贴的完整链接
NODE_TOKEN=$(printf '%s' "$PARENT_URL" | sed -E 's#.*/wiki/##; s#[/?#].*$##')
echo "解析到 node_token: $NODE_TOKEN"
```

如果解析为空（URL 里没有 `/wiki/`）：提示用户「这不是知识库节点链接，请粘贴形如 `https://xxx.feishu.cn/wiki/{token}` 的 URL」，重新询问，**不要写入 config**。

**再调 wiki get_node 校验应用对该节点有访问权限，并取回 space_id / 标题：**

```bash
RESP=$(curl -s "https://$DOMAIN/open-apis/wiki/v2/spaces/get_node?token=$NODE_TOKEN&obj_type=wiki" \
  -H "Authorization: Bearer $TOKEN")
echo "$RESP" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('code:',d.get('code'),d.get('msg'))
n=d.get('data',{}).get('node',{})
if n:
    print('title    :',n.get('title'))
    print('space_id :',n.get('space_id'))
    print('node     :',n.get('node_token'))
    print('obj_type :',n.get('obj_type'))
"
```

- 成功（`code=0`）：把回显的 **标题** 给用户确认（「默认父节点 = 《xxx》，对吗？」），记录 `node_token` 与 `space_id`，继续步骤 4。
- 失败 `131006` / `forbidden` / `1061004`：应用没被加入该知识库。提示用户「请打开该知识库 → 设置 → 成员管理 → 添加应用（按应用名搜索）并赋『可编辑』权限，完成后告诉我重试」。**不要写入 config，让用户处理完再重跑**。
- 其他错误：把完整 `msg` 显示给用户，重新询问 URL。

如果用户没填 URL，跳过本步，`default_parent_node_token` / `default_wiki_space_id` 留空。

### 步骤 4：写入配置

```bash
mkdir -p "$HOME/.prd-feishu"
cat > "$CONFIG_PATH" <<EOF
{
  "app_id": "$APP_ID",
  "app_secret": "$APP_SECRET",
  "app_domain": "$DOMAIN",
  "default_parent_node_token": "$NODE_TOKEN",
  "default_wiki_space_id": "$SPACE_ID",
  "default_parent_url": "$PARENT_URL",
  "node_type": "wiki",
  "initialized_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
chmod 600 "$CONFIG_PATH"
```

未填 URL 时，`default_parent_node_token` / `default_wiki_space_id` / `default_parent_url` 写空字符串。

`chmod 600` 让配置文件仅当前用户可读（保护 Secret）。

### 步骤 5：输出确认信息

向用户报告：
- ✓ 配置已写入 `~/.prd-feishu/config.json`
- ✓ 凭证已通过飞书 API 验证
- ✓（若填了 URL）默认知识库父节点已设为《标题》
- 提示下一步：使用 `/prd-feishu <需求描述>` 生成 PRD，文档会作为知识库子节点挂在默认父节点下

如果用户没填默认父节点 URL，提醒「未设默认父节点，使用 `/prd-feishu` 时需要传入知识库 URL，或由 `.aliyuncs.json` 自动解析对应节点」。

## 配置文件结构

```json
{
  "app_id": "cli_xxxxxxxxxxxx",
  "app_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "app_domain": "open.feishu.cn",
  "default_parent_node_token": "XCSKwAJYaix5iMkGaDocbwUynnh",
  "default_wiki_space_id": "7618027057313844165",
  "default_parent_url": "https://xxx.feishu.cn/wiki/XCSKwAJYaix5iMkGaDocbwUynnh",
  "node_type": "wiki",
  "initialized_at": "2026-05-13T10:30:00Z"
}
```

## 安全注意事项

- App Secret 是敏感凭证，**不要打印到终端或日志中**
- 配置文件权限设为 `600`（仅用户可读写）
- 如果 Secret 泄露，立即去飞书开放平台「凭证与基础信息」点「重置」生成新 Secret，并重新跑本 skill

## 错误处理

- 用户提供的 App ID / Secret 错误 → 显示具体错误，让用户重新输入
- 知识库节点 URL 无法解析（不含 `/wiki/`）→ 提示粘贴正确的知识库节点链接
- wiki get_node 返回 forbidden → 应用未加入该知识库，引导用户在知识库成员管理里添加应用并赋可编辑权限
- 飞书域名不可达 → 提示检查网络
- 配置目录创建失败 → 提示用户检查 ~/.prd-feishu 父目录权限
- 用户中途取消 → 不写入任何文件，提示「未初始化，可重新运行 /prd-feishu-init」

---
name: prd-feishu
description: Generate a PRD and publish it to a Feishu (Lark) docx document, then sync the URL back to the corresponding aliyuncs requirement description. Primary mode: take a requirement identifier (id or subject) from .aliyuncs.json and auto-resolve the pre-created Feishu node URL. Fallback: take a Feishu URL directly.
argument-hint: "<requirement-identifier-or-feishu-url> [extra context]"
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion, Agent
---

# 飞书 PRD 生成器

You are a senior product manager. 写一份产品视角的 PRD，发布到飞书云文档，同时把飞书 URL 回写到对应云效需求的描述顶部。

> ⚠️ **只在「首次生成 / 完整重写」时用本 skill。** 本 skill 的 `publish.py` 会
> **清空整篇文档再从本地 HTML 重写**，会抹掉用户在飞书里手动改过的内容。
> 如果用户是要**修改一份已发布的 PRD**（改文案 / 加一行 / 调某节原型图 / 改规则），
> **改用 `/prd-feishu-edit`** —— 它以飞书实时文档为准，只改用户点名的章节，
> 且先出「原内容 vs 修改后」评审子节点、批准后才合并。**不要为了「改一下」重跑本 skill。**

## Input

用户输入：$ARGUMENTS

参数解析（按以下顺序判定）：
1. 如果第一个参数是 URL（含 `feishu.cn/docx/` 或 `feishu.cn/wiki/`）→ **直传 URL 模式**：跳过云效查找，直接往这个 URL 写
2. 如果第一个参数不是 URL → **需求标识模式**：在 `.aliyuncs.json` 的 `requirements` 数组里按以下顺序查找：
   - `identifier` 完全相等
   - `subject` 完全相等
   - `subject` 包含该字符串（仅当唯一命中时）
   - 多义或无命中 → AskUserQuestion 让用户从列表选

## 主工作流（需求标识模式 = 推荐）

```
用户：/prd-feishu 应用管理详情页

skill 步骤：
1. 校验 .aliyuncs.json 存在，含 requirements 数组
2. 模糊匹配「应用管理详情页」→ 找到 requirement → 取 feishu_url
3. 如 feishu_url 为空：提示用户先确保 aliyuncs:create-requirement 已绑定飞书节点
   （旧需求可能没绑，告知用户在飞书手动建一个节点并回填 feishu_url，或重跑 create-requirement）
4. 按 prd skill 的内容结构生成 PRD HTML 到 /tmp/prd-feishu-{ts}.html
5. 调用 python3 ~/.claude/skills/prd-feishu/publish.py <临时HTML> <feishu_url>
6. publish.py 自动：
   - 写飞书内容（清空 + 插入）
   - 上传原型图 + 绑定
   - 父节点 / 祖父节点向上回链
   - 反查 .aliyuncs.json 拿到 requirement.identifier，把飞书 URL 同步到云效需求描述顶部
```

## 备用工作流（直传 URL 模式 = 飞书优先，云效可选）

如果用户直接给了飞书 URL（适用于「这份 PRD 不挂在云效」的临时场景）：
1. 同样按 prd 规则生成 HTML
2. 调 publish.py <HTML> <用户给的 URL>
3. publish.py 仍会尝试反查 `.aliyuncs.json` 的 feishu_url 同步描述；找不到匹配项就跳过云效同步

## 飞书节点的来源

新工作流下，飞书空节点是 `aliyuncs:create-requirement` 自动创建的（前提是 `aliyuncs:create-iteration` 时设了 `feishu_parent_url`）。所以：
- 跑过 `aliyuncs:create-iteration` 填了飞书父节点 URL
- 跑过 `aliyuncs:create-requirement` 创建需求
- 此时 `.aliyuncs.json` 里 requirement.feishu_url 已就绪
- 直接 `/prd-feishu <subject>` 就能写文档

如果 `feishu_url` 为空（旧需求或飞书联动失败），用户需要手动在飞书建空节点（设链接共享）+ 把 URL 填回 .aliyuncs.json，或直接用「直传 URL 模式」。

## 前置检查

### 1. 读取飞书凭证

```bash
CONFIG="$HOME/.prd-feishu/config.json"
if [ ! -f "$CONFIG" ]; then
  echo "未找到飞书凭证配置。请先运行 /prd-feishu-init 完成初始化。"
  exit 1
fi
```

读取 `app_id` / `app_secret` / `app_domain`（不再需要 `default_folder_token`）。

### 2. 检查 Chrome 是否可用（用于渲染原型图 PNG）

```bash
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ ! -x "$CHROME" ]; then
  # 备选路径
  CHROME="$(which chromium 2>/dev/null || which google-chrome 2>/dev/null)"
fi
[ -z "$CHROME" ] && echo "未找到 Chrome 浏览器，请先安装 Chrome 或 Chromium。" && exit 1
```

## PRD 内容结构（与 `prd` skill 完全一致）

**PRD 结构和写作规则等同于 `prd` skill 的 SKILL.md**（详见 `~/.claude/skills/prd/SKILL.md`），主要章节：

1. `# 需求名称`（H1 标题，等同于飞书文档标题）
2. `## 需求目标`
3. `## 需求简述`
   - `### 3.1 产品架构图`（用嵌套列表表达，飞书 Markdown 转换后自动变成层级列表）
   - `### 3.2 功能清单`（Markdown 表格：编号 | 名称 | 类型 | 说明）
4. `## 需求详述`
   - `### 4.x 功能名`
     - `#### 4.x.1 状态机`（仅在功能有真实用户可感知的业务状态流转时画；状态机使用 SVG，**作为原型图渲染为 PNG**）
     - `#### 4.x.2 原型图`（含筛选区 / 列表区 / 表单区表格 + 视觉原型设计图；**视觉原型设计图渲染为 PNG**）
     - `#### 4.x.3 逻辑补充`（仅在有复杂业务逻辑时写）

### 项目级偏好规则（严守）

参见 `~/.claude/projects/-Users-charon-TRSA/memory/feedback_prd_writing.md`：

1. **不写「数据关系」章节** — 不列后端表名 / 字段映射 / 外键
2. **产品视角，重用户体验** — 不写技术实现细节（缓存 TTL / 幂等键 / 性能 P95 等）
3. **严格按需求范围写功能改动** — 需求里没要求的功能 / 入口 / 列 / 徽章 / 提示条一律不补
4. **状态机判断准则** — 没有真实业务状态流转就**整个省略状态机小节**（连小标题也不要保留）
5. **规则类内容写「具体规则」** — 涉及评级 / 判定 / 计算 / 分级时要把每档 / 每条规则讲清楚

## 视觉原型图处理（与 `prd` skill 的关键差异）

`prd` skill 把视觉原型图作为内联 HTML 块嵌入文档；本 skill **把每个视觉原型图渲染为 PNG，上传到飞书作为图片块**。

### 步骤

对 PRD 中每个需要视觉原型图的位置（如「新增云资源弹窗」「证书列表」「告警通知样式」等）：

1. **生成原型图 HTML 片段**（独立小文件）：
   - 同 `prd` skill 的设计语言：浅灰背景容器 + 白色卡片 + 边框颜色编码 + 黄色 ★ 高亮新增字段
   - 一个原型图一个 `.html` 文件，存到 `/tmp/prd-feishu-{timestamp}/proto-{seq}.html`
   - 文件含完整 `<!DOCTYPE html><html><head>...</head><body>...</body></html>` 结构
   - body 设固定 max-width（比如 880px），避免渲染时被压扁

2. **用 Chrome headless 渲染为 PNG**：

```bash
"$CHROME" --headless --disable-gpu --no-sandbox \
  --hide-scrollbars \
  --window-size=920,1200 \
  --default-background-color=ffffffff \
  --screenshot="/tmp/prd-feishu-{ts}/proto-{seq}.png" \
  "file:///tmp/prd-feishu-{ts}/proto-{seq}.html"
```

- 窗口宽度比 body max-width 略大（如 max-width:880 → window-size:920），避免横向滚动条
- 窗口高度直接给足（如 3000），避免内容被截断；底部空白靠后续裁剪去除
- `--default-background-color=ffffffff` 让背景为白色（默认透明的话上传飞书会有色块）
- **渲染完成后用 PIL 自动裁剪底部白边**（必须做，否则飞书文档里图片下方会有大块空白）：

```python
from PIL import Image, ImageChops
img = Image.open(png_path).convert('RGB')
bg = Image.new('RGB', img.size, (255, 255, 255))
bbox = ImageChops.difference(img, bg).getbbox()
if bbox:
    _, _, _, bt = bbox
    bt = min(img.size[1], bt + 20)  # 留 20px padding
    img.crop((0, 0, img.size[0], bt)).save(png_path)
```

3. **彩色徽章纯文本化**：在生成 Markdown 主体时，把 HTML 原型图里的彩色徽章替换为纯文本标注。例如：
   - HTML 渲染图里：绿色徽章 `● 已验证`
   - Markdown 主体引用时：`● 已验证（绿）`
   
   这样原型图 PNG 里有视觉颜色，Markdown 主体里有文字说明，两者互补。

### 状态机图

状态机用 SVG 绘制（同 `prd` 的水平泳道格式：操作 / 状态 / 事件三泳道）。SVG 也用上面的"独立 HTML 文件 + Chrome 渲染"方式转 PNG。

## 实现脚本

本 skill 目录下自带 `publish.py`，封装了完整的 API 调用、清空文档、转换、插入、上传、绑定 + **向上回链**流程。一般用法：

```bash
python3 "$HOME/.claude/skills/prd-feishu/publish.py" <PRD_HTML 路径> <飞书文档 URL>
```

只在脚本无法满足需求时再按下方步骤逐项调用 API。

## 向上回链（自动维护目录索引）

写完 PRD 主体后，脚本会沿 wiki `parent_node_token` 自动向上爬两级，在父节点 / 祖父节点的 docx 末尾追加 / 更新一个 bullet：

- **父节点正文**追加：`- [当前 PRD 标题](当前 PRD URL) — 需求目标全文`（按 URL 查重，命中则更新简介文本）
- **祖父节点正文**追加：`- [父节点标题](父节点 URL)`（按 URL 查重，命中则跳过）

"需求目标全文"由 HTML 提取：`<h2>` 文本含「需求目标」开始，到下一个 H2 之前的所有 `<p>`。

### 适用场景

```
[祖父] 系统名     ← 自动出现一行指向「迭代版本」的 bullet
└── [父] 迭代版本  ← 自动出现 N 行，每行一个 PRD 链接 + 简介
    ├── PRD 1
    ├── PRD 2
    └── ...
```

层级不够（PRD 没有父节点 / 父节点没有祖父）时自动跳过对应级别，不报错。

## 飞书 API 调用流程

### 准备：换取 tenant_access_token

```bash
DOMAIN="$app_domain"  # 默认 open.feishu.cn
TOKEN_RESP=$(curl -s -X POST "https://$DOMAIN/open-apis/auth/v3/tenant_access_token/internal" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "{\"app_id\":\"$APP_ID\",\"app_secret\":\"$APP_SECRET\"}")
TOKEN=$(echo "$TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['tenant_access_token'])")
```

token 有效期 2 小时，本次 skill 执行期间复用同一个 token。

### 步骤 1：从用户提供的 URL 解析出 doc_id

支持两种 URL 形态：

```python
import re, requests
m = re.search(r'/(docx|wiki)/([A-Za-z0-9]+)', TARGET_URL)
url_type, url_token = m.group(1), m.group(2)

if url_type == 'wiki':
    # wiki 节点要先转 docx obj_token
    r = requests.get(f'{BASE}/wiki/v2/spaces/get_node',
                     headers=HEAD, params={'token': url_token})
    node = r.json()['data']['node']
    if node['obj_type'] != 'docx':
        sys.exit('节点不是 docx 类型')
    DOC_ID = node['obj_token']
else:
    DOC_ID = url_token
```

### 步骤 1b：清空目标文档的现有内容

用户给的文档是新建的空文档（仅有根块 + 默认标题段），需要先把根块下的 children 全清掉再写：

```python
r = requests.get(f'{BASE}/docx/v1/documents/{DOC_ID}/blocks',
                 headers=HEAD, params={'page_size': 500})
items = r.json()['data']['items']
root = next(b for b in items if b['block_type'] == 1)  # block_type=1 是 page 根块
n = sum(1 for b in items if b.get('parent_id') == root['block_id'])
if n > 0:
    requests.delete(f'{BASE}/docx/v1/documents/{DOC_ID}/blocks/{DOC_ID}/children/batch_delete',
                    headers={**HEAD, 'Content-Type': 'application/json'},
                    json={'start_index': 0, 'end_index': n})
```

⚠️ **关键顺序约束**：图片素材上传时 `parent_node` 必须填**图片块的 block_id**（不是文档 ID）。所以正确流程是 **解析 URL → 清空文档 → 转换 markdown 拿 blocks → 用 descendant 接口插入 → 从响应里拿到真实 image block_id → 然后才上传 PNG → 最后 replace_image 绑定**。不能预先上传 PNG。

### 步骤 2：Markdown 拼装 + 图片占位

生成完整 Markdown 文本：

- 主体内容（标题 / 段落 / 表格 / 列表 / 引用）直接写 Markdown
- 每个原型图位置先用占位 Markdown 图片：`![原型图1](placeholder-1)`
- 占位 URL 不用真的存在，转换时飞书会把它当 Image block 处理；后续步骤会用 replace_image 替换为真实图片

### 步骤 3：Markdown 转 blocks

```bash
CONVERT_RESP=$(curl -s -X POST "https://$DOMAIN/open-apis/docx/v1/documents/blocks/convert" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "{
    \"content_type\": \"markdown\",
    \"content\": $(echo "$MARKDOWN" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')
  }")
```

返回 `blocks`（含层级关系的扁平数组）、`first_level_block_ids`、`block_id_to_image_urls`。

### 步骤 4：清理 blocks

- **表格 block 去除 `merge_info` 字段**（飞书要求此字段只读，传入会报错）：

```python
for b in blocks:
    if b.get('block_type') == 31:  # Table
        b.get('table', {}).get('property', {}).pop('merge_info', None)
```

### 步骤 5：用 descendant 接口插入嵌套块

⚠️ 不要用 `/children` 接口——它不支持嵌套块（含 table_cell 的表格会报 `block not support to create`）。要用 `/descendant`：

```bash
curl -s -X POST "https://$DOMAIN/open-apis/docx/v1/documents/$DOC_ID/blocks/$DOC_ID/descendant" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "{
    \"index\": 0,
    \"children_id\": $FIRST_LEVEL_IDS_JSON,
    \"descendants\": $CLEANED_BLOCKS_JSON
  }"
```

返回 `data.descendants`（或 `data.children`）数组，里面是**插入后的真实 block**。⚠️ 这些 block_id 是飞书重新分配的，**跟 convert 返回的 block_id 不同**。从这里按 `block_type==27` 提取真实的图片块 ID（保持出现顺序，与原型图 PNG 序号一一对应）。

### 步骤 6：用真实 image_block_id 上传 PNG 素材

对每个原型图 PNG 调用图片素材上传 API：

```bash
# parent_node 必须填上一步拿到的真实 image_block_id
curl -s -X POST "https://$DOMAIN/open-apis/drive/v1/medias/upload_all" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file_name=proto-1.png" \
  -F "parent_type=docx_image" \
  -F "parent_node=$IMAGE_BLOCK_ID" \
  -F "size=$(stat -f%z /tmp/prd-feishu-{ts}/proto-1.png)" \
  -F "file=@/tmp/prd-feishu-{ts}/proto-1.png"
```

⚠️ 如果 `parent_node` 填了 `$DOC_ID` 而不是真实 image_block_id，下一步 replace_image 会报 `1770001 invalid param` 或 `1061044 parent node not exist`。

返回 `file_token`。

### 步骤 7：为图片块绑定上传好的素材

对每个图片块用 `update_block` 接口：

```bash
curl -s -X PATCH "https://$DOMAIN/open-apis/docx/v1/documents/$DOC_ID/blocks/$IMAGE_BLOCK_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "{
    \"replace_image\": {
      \"token\": \"$FILE_TOKEN\"
    }
  }"
```

`$FILE_TOKEN` 是步骤 6 上传图片素材返回的 token；`$IMAGE_BLOCK_ID` 是步骤 5 descendant 接口返回的真实图片块 ID。**按顺序一一对应**：第 N 个原型图 PNG 上传得到的 file_token，绑定到第 N 个图片块的 block_id。

## 步骤 8：输出飞书文档链接

```
✓ 飞书 PRD 已写入：
  目标：{TARGET_URL}
```

## 完整流程伪代码

```
1. 验证 config + Chrome 可用，解析 ARGUMENTS = <URL> <需求描述>
2. 生成 PRD 内容草稿（含原型图标记）
3. 与用户确认大纲（功能清单层级、原型图数量）
4. 换 tenant_access_token
5. 解析 URL → 拿到 DOC_ID（wiki URL 要先 get_node 转）
5b. 清空 DOC_ID 文档现有 blocks（GET /blocks 列出 + DELETE batch_delete 根块下所有 children）
6. 渲染每个原型图为 PNG：
   a. 写 HTML 片段到 /tmp/.../proto-N.html
   b. Chrome headless 截图（高度给足，如 3000）
   c. PIL ImageChops 自动裁剪底部白边
7. 组装 Markdown（占位图标 ![](placeholder-N)）
8. POST /docx/v1/documents/blocks/convert → 得 blocks / first_level_block_ids
9. 清理 blocks（表格去 merge_info）
10. POST /docx/v1/documents/{DOC_ID}/blocks/{DOC_ID}/descendant 插入 → 从响应里拿真实 IMAGE_BLOCK_ID_N
11. 对每个原型图 PNG：
    a. POST /drive/v1/medias/upload_all 上传 (parent_node=IMAGE_BLOCK_ID_N, parent_type=docx_image) → 得 FILE_TOKEN_N
    b. PATCH /docx/v1/documents/{DOC_ID}/blocks/{IMAGE_BLOCK_ID_N} replace_image=FILE_TOKEN_N
12. 清理临时文件 /tmp/prd-feishu-{ts}/*
13. 输出 TARGET_URL 让用户复查
```

## 错误处理

| 场景 | 处理 |
|------|------|
| token 换取失败 (code != 0) | 提示用户配置可能过期，建议重新 `/prd-feishu-init` |
| URL 解析失败 | 提示用户给 docx URL（形如 `/docx/{id}` 或 `/wiki/{token}`）|
| 列 blocks 失败 (1254030 / forbidden) | 用户没把文档共享给应用，提醒：文档分享 → 链接共享 →「组织内获得链接的人可编辑」|
| 图片上传失败 (1061045 / 1061046) | 检查 PNG 文件 + parent_type 是否为 `docx_image` |
| Markdown 转换失败 | 检查 Markdown 是否含非法字符；常见是表格列数不一致 |
| 创建嵌套块失败 (1770006 schema mismatch) | 通常是 BLOCKS 没正确清理（表格 merge_info 没去掉）|
| 插入嵌套块失败 (1770029 block not support to create) | 用了 `/children` 接口，必须用 `/descendant` |
| 图片上传失败 (1061044 parent node not exist) | 用了 convert 返回的 block_id；要用 descendant 接口插入后响应里的真实 image block_id |
| 更新图片块失败 (1770001 invalid param) | parent_node 没填对（必须是真实 image_block_id，不是 DOC_ID）|

## 性能与费用

- **单份 PRD 大致 API 调用量**：
  - 1 次：创建文档
  - 1 次：Markdown 转换
  - 1~3 次：创建嵌套块（按 1000 块/次，复杂 PRD 一般 1 次够）
  - N 次：上传图片素材（N = 原型图数量，平均 8~15）
  - N 次：update_block 替换图片
  - **总计：约 20~35 次/份**
- **频率限制**：每秒 3 次（应用级 + 文档级），需要在调用间加 350ms 间隔，避免 429
- **免费版额度**：基础免费版 10,000 次/月（2026 年 5 月限时 100 万次/月），可写 300~500 份/月，绰绰有余

## 与 `prd` skill 的关系

| 维度 | `prd` skill | `prd-feishu` skill |
|------|------------|---------------------|
| 输出 | 本地 `PRD_xxx.html` 含内联编辑器 | 飞书云文档链接 |
| 原型图 | 内联 HTML 块（含工具栏可编辑） | 渲染为 PNG，作为飞书图片块 |
| 彩色徽章 | 内联 CSS 颜色 | 纯文本标注 + 原型图 PNG 内的颜色 |
| 编辑方式 | 浏览器打开 HTML 点编辑 | 飞书协同编辑 |
| 适用场景 | 单人写作 / 邮件发送 / 粘贴到语雀 | 团队协同 / 评审 / 长期演进 |

两个 skill **共享 PRD 结构和内容规则**（章节大纲、字段说明表、状态机判定准则、规则要具体等），只在「输出形态」和「原型图呈现方式」上不同。修改 PRD 内容规则时两个 skill 都要同步。

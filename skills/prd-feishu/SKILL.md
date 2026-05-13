---
name: prd-feishu
description: Generate a PRD and publish it directly to a Feishu (Lark) docx document. PRD body uses native Feishu Markdown blocks; prototype mockups are rendered as PNG images and inserted as Feishu Image blocks. Use when the user wants to create a PRD that lives on Feishu Docs rather than as a local HTML file.
argument-hint: "[requirement description or topic]"
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion, Agent
---

# 飞书 PRD 生成器

You are a senior product manager. 根据用户输入生成一份产品视角的 PRD，并直接发布到飞书云文档。

## Input

用户的需求描述：$ARGUMENTS

## 前置检查

### 1. 读取飞书凭证

```bash
CONFIG="$HOME/.prd-feishu/config.json"
if [ ! -f "$CONFIG" ]; then
  echo "未找到飞书凭证配置。请先运行 /prd-feishu-init 完成初始化。"
  exit 1
fi
```

读取 `app_id` / `app_secret` / `default_folder_token` / `app_domain` 四项。

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
- `--default-background-color=ffffffff` 让背景为白色（默认透明的话上传飞书会有色块）
- 渲染完成后用 `sips` 或 `imagemagick` 把图片做一次 trim/crop 去掉底部留白：

```bash
# macOS 自带 sips：把图片裁剪到内容高度（PNG 含 alpha 信息时可用 trim）
# 或直接用一个固定窗口大小，依靠精心设计的 HTML 高度
```

3. **彩色徽章纯文本化**：在生成 Markdown 主体时，把 HTML 原型图里的彩色徽章替换为纯文本标注。例如：
   - HTML 渲染图里：绿色徽章 `● 已验证`
   - Markdown 主体引用时：`● 已验证（绿）`
   
   这样原型图 PNG 里有视觉颜色，Markdown 主体里有文字说明，两者互补。

### 状态机图

状态机用 SVG 绘制（同 `prd` 的水平泳道格式：操作 / 状态 / 事件三泳道）。SVG 也用上面的"独立 HTML 文件 + Chrome 渲染"方式转 PNG。

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

### 步骤 1：创建空 docx 文档

```bash
CREATE_RESP=$(curl -s -X POST "https://$DOMAIN/open-apis/docx/v1/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "{
    \"title\": \"$PRD_TITLE\",
    \"folder_token\": \"$DEFAULT_FOLDER_TOKEN\"
  }")
DOC_ID=$(echo "$CREATE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['document']['document_id'])")
```

`folder_token` 为空则不传该字段（文档进应用根目录）。

### 步骤 2：上传原型图 PNG 到飞书图片素材

对每个 PNG 调用图片素材上传 API：

```bash
# 注意 parent_type 必须为 docx_image，parent_node 是 document_id
curl -s -X POST "https://$DOMAIN/open-apis/drive/v1/medias/upload_all" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file_name=proto-1.png" \
  -F "parent_type=docx_image" \
  -F "parent_node=$DOC_ID" \
  -F "size=$(stat -f%z /tmp/prd-feishu-{ts}/proto-1.png)" \
  -F "file=@/tmp/prd-feishu-{ts}/proto-1.png"
```

返回 `file_token`，记下来供下一步使用。

### 步骤 3：把 PRD 转为 Markdown + 图片占位

生成完整 Markdown 文本：

- 主体内容（标题 / 段落 / 表格 / 列表 / 引用）直接写 Markdown
- 每个原型图位置先用占位 Markdown 图片：`![原型图1](placeholder-1)`
- 占位 URL 不用真的存在，转换时飞书会把它当 Image block 处理；我们后续用 update_block 替换图片素材

### 步骤 4：Markdown 转 blocks

```bash
CONVERT_RESP=$(curl -s -X POST "https://$DOMAIN/open-apis/docx/v1/documents/blocks/convert" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "{
    \"content_type\": \"markdown\",
    \"content\": $(echo "$MARKDOWN" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')
  }")
```

返回 `blocks` 数组（飞书 docx 的 block JSON 结构）。

### 步骤 5：清理 blocks（必要的预处理）

- **表格 block 去除 `merge_info` 字段**（飞书要求此字段只读，传入会报错）：

```python
import json
def clean_blocks(blocks):
    for b in blocks:
        if b.get('block_type') == 31:  # Table
            for tb in b.get('table', {}).get('property', {}).get('merge_info', []):
                pass
            b.get('table', {}).get('property', {}).pop('merge_info', None)
    return blocks
```

- **图片 block 记录顺序**：转换后的 image block 的 token 是空的，记下它们在 blocks 数组中的位置（索引），便于后续 replace_image 时按顺序绑定上传好的 file_token。

### 步骤 6：插入 blocks 到文档（创建嵌套块）

```bash
curl -s -X POST "https://$DOMAIN/open-apis/docx/v1/documents/$DOC_ID/blocks/$DOC_ID/children" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d "{
    \"index\": 0,
    \"children\": $CLEANED_BLOCKS_JSON
  }"
```

- 单次最多 1000 个块；超过分批
- 父块 ID 用 `document_id` 表示插入到根
- 返回的 blocks 包含每个图片块的真实 `block_id`，记下来供下一步绑定图片素材

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

`$FILE_TOKEN` 是步骤 2 上传图片素材返回的 token；`$IMAGE_BLOCK_ID` 是步骤 6 插入后获得的图片块 ID。**按顺序一一对应**：第 N 个原型图 PNG 上传得到的 file_token，绑定到第 N 个图片块的 block_id。

## 步骤 8：输出飞书文档链接

```
✓ 飞书 PRD 已创建：
  标题：{PRD_TITLE}
  链接：https://{user_company_subdomain}.feishu.cn/docx/{DOC_ID}
  备注：链接需在飞书登录态下访问，建议从飞书桌面/移动端打开。
```

如果用户没有配置 `default_folder_token`，提醒「文档在应用空间根目录，可在飞书里手动移动到指定文件夹」。

## 完整流程伪代码

```
1. 验证 config + Chrome 可用
2. 生成 PRD 内容草稿（含原型图标记）
3. 与用户确认大纲（功能清单层级、原型图数量）
4. 换 tenant_access_token
5. POST /docx/v1/documents 创建空文档 → 得 DOC_ID
6. 遍历每个原型图：
   a. 写 HTML 片段到 /tmp/.../proto-N.html
   b. Chrome headless 渲染为 PNG
   c. POST /drive/v1/medias/upload_all 上传 PNG (parent_node=DOC_ID, parent_type=docx_image) → 得 FILE_TOKEN_N
7. 组装 Markdown（占位图标 ![](placeholder-N)）
8. POST /docx/v1/documents/blocks/convert → 得 BLOCKS
9. 清理 BLOCKS（表格去 merge_info，记录图片块顺序）
10. 分批 POST /docx/v1/documents/{DOC_ID}/blocks/{DOC_ID}/children 插入 → 得每个图片块的 IMAGE_BLOCK_ID
11. 按顺序 PATCH /docx/v1/documents/{DOC_ID}/blocks/{IMAGE_BLOCK_ID} replace_image=FILE_TOKEN
12. 清理临时文件 /tmp/prd-feishu-{ts}/*
13. 输出飞书文档链接
```

## 错误处理

| 场景 | 处理 |
|------|------|
| token 换取失败 (code != 0) | 提示用户配置可能过期，建议重新 `/prd-feishu-init` |
| 创建文档失败 | 检查权限是否包含 `docx:document:create` |
| 图片上传失败 (1061045 / 1061046) | 检查 PNG 文件 + parent_type 是否为 `docx_image` |
| Markdown 转换失败 | 检查 Markdown 是否含非法字符；常见是表格列数不一致 |
| 创建嵌套块失败 (1770006 schema mismatch) | 通常是 BLOCKS 没正确清理（表格 merge_info 没去掉）|
| 更新图片块失败 | 确认 IMAGE_BLOCK_ID 在该文档下、FILE_TOKEN 的 parent_node 匹配 DOC_ID |

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

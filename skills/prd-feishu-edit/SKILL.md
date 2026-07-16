---
name: prd-feishu-edit
description: Surgically modify an already-published Feishu PRD without clobbering the user's manual edits. Reads the LIVE Feishu doc as source of truth, only rewrites the section(s) the user names, and routes every change through a review child-node → approve → merge gate. Use when the user asks to CHANGE / FIX / ADJUST an existing published PRD (not to create a new one). Do NOT re-run prd-feishu/publish.py for edits — it clears + overwrites the whole doc and destroys manual changes.
argument-hint: "<requirement-identifier-or-feishu-url> 改：<要改哪里、改成什么>"
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion
---

# 飞书 PRD 局部修改器

对**已经发布到飞书的 PRD**做外科手术式局部修改。核心承诺两条：

1. **只改用户说的地方，其余一律不动。** 以「飞书实时文档」为准（不是本地 HTML），
   逐节替换用户点名的章节，别的章节逐块原样保留 —— 用户手动改过的部分不会被抹掉。
2. **改动先过评审，用户批准后才合并。** 不直接动原文档，而是在原 PRD 的 wiki 节点下
   新建一个「修改建议」子节点，写上「原内容 vs 修改后」对照。用户看过说「同意」，才合并回原文档。

## 什么时候用这个 skill（vs prd-feishu）

| 场景 | 用哪个 |
|------|--------|
| 从零生成一份新 PRD 并发布 | `prd-feishu` |
| 改动一份**已发布**的 PRD（改文案 / 加一行 / 调整某节原型图 / 改规则） | **`prd-feishu-edit`（本 skill）** |

⚠️ **绝对不要**为了「改一下」而重跑 `prd-feishu` / `publish.py`：那条路径会
**清空整篇再从本地 HTML 重写**，会把用户在飞书里手动改的内容全部抹掉 —— 这正是本 skill 要解决的痛点。

## 输入解析

用户输入：`$ARGUMENTS`，形如 `<需求标识或飞书URL> 改：<修改描述>`。

- 若含飞书 URL（`feishu.cn/docx/` 或 `feishu.cn/wiki/`）→ 直接用该 URL 作为 `target_url`。
- 否则把第一段当**需求标识**，在 `.aliyuncs.json` 的 `requirements` 里按
  `identifier` 完全相等 → `subject` 完全相等 → `subject` 包含（唯一命中）的顺序找 `feishu_url`；
  多义或无命中就 AskUserQuestion 让用户选。
- 其余文字是**修改描述**（改哪里、改成什么）。描述不清时先问清楚再动手。

## 三步工作流（务必按顺序）

### 第 1 步 · fetch —— 看清「当前真实内容」

```bash
python3 "$HOME/.claude/skills/prd-feishu-edit/edit.py" fetch "<target_url>"
```

脚本会：
- 从**飞书实时文档**把内容重建成 Markdown 打印出来（**包含用户手动改过的部分**）；
- 打印「标题索引」JSON：每个标题的 `heading_text` / `level` / 根级序号 `idx`。

**你必须先读这份实时内容**，据此判断要改的内容落在哪个标题小节里。
锚点标题文本要用**索引里给出的当前真实文本**（用户可能已改过标题），不要用你记忆里的旧标题。

### 第 2 步 · 生成 plan.json 并建评审子节点

按「章节粒度」定位：找到能**完整包住**用户要改内容的**最小标题小节**（优先 H4，其次 H3，再 H2）。
只重写这一节，其余不碰。为每个要改的小节写一份完整的**新版 Markdown（含标题本身）**。

写 plan.json（放到 scratchpad 或项目临时目录）：

```json
{
  "target_url": "https://xxx.feishu.cn/wiki/XXXXXXXX",
  "change_summary": "把 4.1 列表页的筛选项从 3 个改成 5 个",
  "sections": [
    {
      "heading_level": 3,
      "heading_text": "4.1 列表页",
      "new_markdown": "### 4.1 列表页\n\n（这一整节改完后的完整 Markdown，含标题行本身）\n\n| 编号 | 名称 | ... |\n| --- | --- | ... |\n...",
      "proto_html_files": ["/tmp/.../edit-proto-1.html"]
    }
  ]
}
```

字段说明：
- `heading_level` / `heading_text`：**逐字取自 fetch 索引**，作为定位锚点。
- `new_markdown`：这一小节改完后的**完整 Markdown**，**必须以该小节标题行开头**（如 `### 4.1 列表页`），
  到下一个同级或更高级标题之前的全部内容。粒度就是「替换整节」——所以没改的行也要照抄进来。
- `proto_html_files`（可选）：本节若含视觉原型图 / 状态机，写这些原型图的 HTML 片段文件路径，
  **顺序 = 它们在 `new_markdown` 里 `![](placeholder-N)` 出现的顺序**。
  原型图 HTML 片段的写法、样式、渲染规则**完全等同 `prd-feishu` skill**（浅灰容器 + 白卡片 + 黄色 ★ 高亮新增字段），
  脚本会用 Chrome 渲染成 PNG 并裁白边后上传。`new_markdown` 里图片位置用 `![原型图](placeholder-1)` 占位。
  本节不含原型图就省略该字段或给 `[]`。

然后建评审子节点：

```bash
python3 "$HOME/.claude/skills/prd-feishu-edit/edit.py" review "<plan.json 路径>"
```

脚本在原 PRD 的 wiki 节点**下面**新建一个 `【修改建议】<原标题> · <时间>` 子节点，
写入每个变更的「⬛ 原内容 vs 🟩 修改后」对照（含新原型图 PNG），并把 `review_url` 回写进 plan.json。
把这个 review_url 给用户，请他打开检查。**不要在用户确认前跑 apply。**

> review 模式要求原 PRD 是 wiki 节点（才能建子节点）。若原文档是裸 docx，脚本会提示——
> 这种情况下与用户确认后可直接跳到 apply（不走评审子节点）。

### 第 3 步 · apply —— 用户批准后合并

用户看完子节点回复「同意 / 合并 / 就这么改」后：

```bash
python3 "$HOME/.claude/skills/prd-feishu-edit/edit.py" apply "<plan.json 路径>"
```

脚本会：
- 以**实时文档**为准，逐节用锚点标题定位该节的根级块区间 → 删除旧区间 → 在**原位**插入新块（含原型图上传绑定）；
- 其余部分（包括用户手动改的别处内容）**一律不动**；
- 合并成功后把 review 子节点**改写为「✅ 已合并」提示**（飞书无稳定的删节点 API，故不自动删除，痕迹保留、用户可手动删）。

## 铁律

1. **永远先 fetch 再改。** 不看实时内容就改，等于赌用户没手动改过——会重蹈覆辙。
2. **锚点用实时标题文本。** 从 fetch 索引里逐字复制，别用记忆里的旧标题。
3. **一节的 new_markdown 要完整。** 是「整节替换」，没改的行也要抄进去，否则会丢内容。
4. **apply 前必须拿到用户明确批准。** review 只是提案，合并是不可逆写操作。
5. **改动范围严格贴合用户描述。** 用户没提的小节不要顺手「优化」——那又会变成「改完把别人的还原了」。

## 前置检查

- 飞书凭证：`~/.prd-feishu/config.json` 存在（否则让用户先 `/prd-feishu-init`）。
- Chrome：仅当变更含原型图时才需要（`/Applications/Google Chrome.app/...`）。

## 常见错误

| 现象 | 原因 / 处理 |
|------|-------------|
| `找不到标题「X」(HN)` | 锚点文本或 level 与实时文档不符 → 重跑 fetch，用索引里的真实文本 |
| `图片占位数与 PNG 数不一致` | `new_markdown` 里 `![](placeholder)` 个数 ≠ `proto_html_files` 个数 |
| `review 模式要求 wiki 节点` | 原文档是裸 docx；与用户确认后直接 apply |
| 合并后发现多删/少删 | 该节内有同级标题打断了区间 → 把锚点选到更小的子标题，或拆成多个 section |

## 与其它 skill 的关系

- 内容结构、原型图样式、项目级写作偏好**完全沿用 `prd-feishu` / `prd` skill** 的规则。
- 本 skill 只负责「安全地改已发布的 PRD」，不负责首次生成——首次生成走 `prd-feishu`。

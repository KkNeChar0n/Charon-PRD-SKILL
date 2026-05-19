---
name: prd-feishu-batch
description: Batch publish multiple local PRD HTML files into a Feishu wiki parent node. Auto-lists child nodes via Feishu wiki API, fuzzy-matches local filenames to node titles, and writes each PRD into its corresponding pre-created docx node. Use when the user has a folder of PRD_*.html files and a Feishu wiki parent node where empty child docs already exist.
argument-hint: "<local_dir> <parent_wiki_url>"
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion
---

# 飞书 PRD 批量发布

把一个本地目录下所有 `PRD_*.html` 批量写入飞书知识库某个父节点下的子文档（节点必须已由用户提前创建）。

## Input

用户输入：$ARGUMENTS

期望格式：`<local_dir> <parent_wiki_url>`

- `local_dir`：本地目录路径（例如 `/Users/charon/TRSA/需求文档`），目录里放 `PRD_*.html` 文件
- `parent_wiki_url`：飞书知识库父节点 URL（例如 `https://xxx.feishu.cn/wiki/J9RwwLcqNi3pTNkSiH9cLseBn9d`），父节点下的子节点是预先建好的空 docx，每个对应一份 PRD

## 前置条件

1. 用户已运行 `/prd-feishu-init` 配好凭证（`~/.prd-feishu/config.json`）
2. 父节点（或更上层的知识库）设了**链接共享：组织内获得链接的人可编辑**，确保应用对所有子节点有读写权
3. 子节点的**标题**和本地文件名能对得上（去掉 `PRD_` 前缀和 `.html` 后缀后，用「包含」可以匹配——飞书节点标题可以更详细，比如 `工作流与 Agent 优化（状态机细化 ...）` 对应 `PRD_工作流与Agent优化.html`）

## 工作流程

### 1. 解析参数 + 读 config

```bash
LOCAL_DIR=<第一个参数>
PARENT_URL=<第二个参数>
# 校验 LOCAL_DIR 存在且包含 PRD_*.html
# 从 PARENT_URL 提取 parent_node_token（/wiki/{token} 的 token 段）
```

### 2. 换 tenant_access_token（同 prd-feishu）

### 3. 调 wiki get_node 拿 space_id

```
GET /open-apis/wiki/v2/spaces/get_node?token={parent_node_token}
→ data.node.space_id
```

### 4. 列出父节点下所有子节点

```
GET /open-apis/wiki/v2/spaces/{space_id}/nodes?parent_node_token={parent_node_token}&page_size=50
→ data.items[*] = {node_token, obj_token, obj_type, title, ...}
```

只保留 `obj_type == 'docx'` 的子节点，跳过 `已归档内容` 之类的容器或非 docx 类型。

### 5. 模糊匹配：本地文件名 ↔ 节点标题

匹配规则（按顺序尝试，命中即停）：

1. 文件名（去 `PRD_` 前缀和 `.html` 后缀，去掉空格）等于节点标题（去掉空格、去掉 `（...）` 括号补充）
2. 文件名（去 `PRD_` 和空格）**包含**节点标题主干 或 节点标题主干**包含**文件名
3. 计算 difflib SequenceMatcher 相似度 ≥ 0.6

```python
import re, difflib
def normalize(s):
    s = re.sub(r'^PRD_', '', s)
    s = re.sub(r'\.html$', '', s)
    s = re.sub(r'（.*?）|\(.*?\)', '', s)  # 去括号补充
    s = re.sub(r'\s+', '', s)
    return s.lower()
```

### 6. 展示匹配结果 + 用户确认

把匹配结果整理成一张表（文件名 → 节点标题 → wiki_url），打印出来。**没有匹配上的本地文件**和**没有匹配上的节点**都单独列出。

用 AskUserQuestion 询问：
- 「以上 N 个匹配将批量写入飞书，每份 PRD 会清空对应节点的现有内容后写入。继续吗？」选项：「全部执行 / 选择部分执行 / 取消」

如果有未匹配项，单独提醒用户决定是否手动指定。

### 7. 串行调用 `publish.py`

```bash
PUB="$HOME/.claude/skills/prd-feishu/publish.py"
for 每个 (HTML_PATH, WIKI_URL) in 确认列表:
    python3 "$PUB" "$HTML_PATH" "$WIKI_URL"
```

每份写入后输出简短行：`✓ {标题} ({原型图数}图, {block数}块)`，失败的输出 `✗ {标题} 错误：{msg}`。

### 8. 汇总报告

```
批量发布完成：
  成功 N/M 份
  失败 K 份（列每个失败项 + 原因）
  跳过 L 份未匹配
```

## 注意事项

- **顺序串行**：不要并行调用，飞书 API 有每秒 3 次的频率限制
- **覆盖式写入**：每份都先清空目标文档现有内容再写。如果用户文档里有手工补充的内容会丢失——执行前必须确认
- **图片素材**：每份 PRD 自己渲染自己的原型图 PNG，无跨份共享
- **节点必须是 docx**：跳过 obj_type 不是 docx 的（如 sheet / bitable / mindnote）
- **匹配冲突**：如果一个文件名匹配上多个节点（或反之），让用户选择

---
name: gray-report
description: 按迭代生成灰度报告，AI 通过 AskUserQuestion 收集灰度范围/策略/时间窗/核心指标/问题汇总/决策结论，渲染为飞书 docx，挂在当前迭代飞书父节点下作为子节点。每个迭代一份，可多次覆盖更新。
argument-hint: "[iteration-name-or-blank]"
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion
user_invocable: true
---

# 灰度报告生成器

按 SOP 第 5.2 节"灰度环境验收"输出灰度报告。一个迭代一份，挂在云效迭代对应的飞书父节点下，作为 PRD 同级的子节点（如父节点为「V1.2.0」，则灰度报告标题为「灰度报告 - V1.2.0」）。

## Input

用户输入：$ARGUMENTS

- 留空 → 用 `.aliyuncs.json` 的 `currentIteration`
- 给迭代名称 → 在 `.aliyuncs.json` 的 `iterations`（或 currentIteration）按 name 匹配
- 给飞书父节点 URL → 直传模式

## 前置检查

```bash
[ ! -f "$HOME/.prd-feishu/config.json" ] && { echo "未找到飞书凭证。/prd-feishu-init"; exit 1; }
[ ! -f ".aliyuncs.json" ] && { echo "未找到 .aliyuncs.json，请在云效项目目录下执行"; exit 1; }
```

## 工作流

### Step 1：定位迭代 + 飞书父节点

读 `.aliyuncs.json`，拿到：
- `currentIteration.name`（如 "V1.2.0"）
- `currentIteration.feishu_space_id`
- `currentIteration.feishu_parent_node_token`
- `currentIteration.feishu_parent_url`
- `currentIteration.gray_url`（可能为空，首次跑时没有）
- `requirements[]` 列表（按 identifier/subject 供后续多选）

### Step 2：检查或创建飞书报告节点

```python
import json, os, re, requests
cfg = json.load(open(os.path.expanduser('~/.prd-feishu/config.json')))
BASE = f'https://{cfg.get("app_domain","open.feishu.cn")}/open-apis'
TOKEN = requests.post(f'{BASE}/auth/v3/tenant_access_token/internal',
    json={'app_id': cfg['app_id'], 'app_secret': cfg['app_secret']}).json()['tenant_access_token']
H = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json; charset=utf-8'}

aly = json.load(open('.aliyuncs.json'))
cur = aly['currentIteration']

if cur.get('gray_url'):
    REPORT_URL = cur['gray_url']
    print(f'复用已有节点: {REPORT_URL}')
else:
    iter_name = cur.get('name', '当前迭代')
    title = f'灰度报告 - {iter_name}'
    r = requests.post(
        f'{BASE}/wiki/v2/spaces/{cur["feishu_space_id"]}/nodes',
        headers=H,
        json={
            'obj_type': 'docx',
            'parent_node_token': cur['feishu_parent_node_token'],
            'node_type': 'origin',
            'title': title,
        }).json()
    if r.get('code') != 0:
        raise SystemExit(f'创建飞书节点失败: {r}')
    nt = r['data']['node']['node_token']
    host = re.match(r'https://([^/]+)', cur['feishu_parent_url']).group(1)
    REPORT_URL = f'https://{host}/wiki/{nt}'
    cur['gray_url'] = REPORT_URL
    json.dump(aly, open('.aliyuncs.json', 'w'), indent=2, ensure_ascii=False)
    print(f'新建节点: {REPORT_URL}')
```

### Step 3：AskUserQuestion 收集报告内容

按以下顺序逐项收集（每项一次 AskUserQuestion，或者一次性多问题；用户也可以一次性粘贴全部内容直接走 Step 4）：

1. **灰度时间窗**：起止日期 + 时长
2. **灰度策略**：按比例（10%/30%/50%）/ 按内部用户 / 按租户 / 按地区 / 其他
3. **涉及需求**：从 `requirements[]` 多选生成
4. **灰度前预期目标**：本次灰度想验证什么（功能正确性 / 性能 / 稳定性 / 业务转化）
5. **核心指标观察**：表格形式，至少 4 行：
   - 错误率 / 关键转化 / 平均响应时间 RT / 用户反馈数
   - 列：指标 | 灰度前基线 | 灰度期表现 | 变化 | 说明
6. **问题汇总**：
   - P0/P1 问题列表（无则填"无"）
   - P2/P3 问题列表
7. **决策结论**：继续放量 / 暂停观察 / 灰度延期 / 紧急回滚（必选一个）+ 决策理由
8. **后续动作**：下一步要做什么
9. **责任人**：产品 / 研发值班 / 报告人

如果用户提示"我直接粘贴报告内容"，跳过 AskUserQuestion，直接解析用户的粘贴文本。

### Step 4：生成 HTML

把收集到的数据填入 HTML 模板，写到 `/tmp/gray-report-{ts}.html`：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>灰度报告 - {iter_name}</title></head>
<body>

<h1>灰度报告 - {iter_name}</h1>

<h2>报告摘要</h2>
<p>{iter_name} 灰度于 {start} ~ {end} 进行，策略：{strategy}；涉及需求 {n} 个；核心指标 {总体表现一句话}；决策：{decision}。</p>

<h2>1. 灰度范围</h2>
<h3>1.1 涉及需求</h3>
<ul>
  <li>[需求标识] 需求标题 — 简短说明</li>
  ...
</ul>
<h3>1.2 灰度策略</h3>
<p>{strategy详述}</p>
<h3>1.3 灰度时间窗</h3>
<p>{start} ~ {end}（共 {duration}）</p>

<h2>2. 灰度目标</h2>
<p>{预期目标}</p>

<h2>3. 核心指标观察</h2>
<table>
<thead>
<tr><th>指标</th><th>灰度前基线</th><th>灰度期表现</th><th>变化</th><th>说明</th></tr>
</thead>
<tbody>
<tr><td>错误率</td><td>0.10%</td><td>0.12%</td><td>+0.02pp</td><td>正常波动</td></tr>
...
</tbody>
</table>

<h2>4. 问题汇总</h2>
<h3>4.1 P0/P1 问题</h3>
<ul>...（无则写"本次灰度未出现 P0/P1 问题"）</ul>
<h3>4.2 P2/P3 问题</h3>
<ul>...</ul>

<h2>5. 决策与结论</h2>
<p><strong>决策</strong>：{decision}</p>
<p><strong>理由</strong>：{reason}</p>
<p><strong>后续动作</strong>：{next_action}</p>

<h2>6. 责任人与时间</h2>
<p>产品：{pm} | 研发值班：{dev} | 报告人：{reporter} | 报告时间：{today}</p>

</body>
</html>
```

**给用户预览**：展示 HTML 渲染后的关键章节摘要（不是 raw HTML），让用户确认后再发布。

### Step 5：调用 prd-feishu 的 publish.py 发布

```bash
python3 ~/.claude/skills/prd-feishu/publish.py /tmp/gray-report-{ts}.html "$REPORT_URL"
```

publish.py 会：
- 清空目标文档现有内容
- Markdown 转 blocks 后插入
- 向上回链到父节点（迭代根节点的目录会自动出现「灰度报告 - V1.2.0」一行）
- 反查 .aliyuncs.json 同步 URL（找不到对应 requirement 时自动跳过，对报告场景无影响）

注意：publish.py 的 `extract_brief` 找"需求目标"章节，灰度报告没有，所以父节点回链的简介会是空 — 这是预期行为，不影响主体内容。

### Step 6：输出

```
✓ 灰度报告已发布
  迭代：{iter_name}
  URL：{REPORT_URL}
  覆盖需求：{n} 个
  决策：{decision}
```

## 多次执行（覆盖更新）

灰度过程中可多次执行本 skill 更新报告。每次执行会：
- 复用 `currentIteration.gray_url`（不重复建节点）
- 清空文档原内容（publish.py 自动做），写入最新版

适用场景：灰度第 1 天先发一份"已上线"基础版，第 2 天补充指标观察，第 3 天加入决策结论。

## 错误处理

| 场景 | 处理 |
|---|---|
| `.aliyuncs.json` 没有 currentIteration | 提示先 `/aliyuncs:create-iteration` |
| currentIteration 缺 feishu_parent_node_token | 提示先在飞书建好迭代父节点并回填到 .aliyuncs.json |
| 创建子节点失败 | 多半是应用没父节点 wiki 写权限，提示加权限 |
| publish.py 报 forbidden | 父节点未设"组织内可编辑"，提示用户开权限 |

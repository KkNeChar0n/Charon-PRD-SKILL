---
name: regression-report
description: 按迭代生成线上/全量回归报告，AI 通过 AskUserQuestion 收集回归环境/用例集/执行结果/缺陷分布/回归结论，渲染为飞书 docx，挂在当前迭代飞书父节点下作为子节点。每个迭代一份，可多次覆盖更新。
argument-hint: "[iteration-name-or-blank]"
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion
user_invocable: true
---

# 回归报告生成器

按 SOP 第 5.3 节"线上环境回归"输出回归报告。一个迭代一份，挂在云效迭代对应的飞书父节点下，作为 PRD 同级的子节点（如父节点为「V1.2.0」，则报告标题为「回归报告 - V1.2.0」）。

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
- `currentIteration.name`
- `currentIteration.feishu_space_id`
- `currentIteration.feishu_parent_node_token`
- `currentIteration.feishu_parent_url`
- `currentIteration.regression_url`（可能为空）
- `requirements[]`

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

if cur.get('regression_url'):
    REPORT_URL = cur['regression_url']
    print(f'复用已有节点: {REPORT_URL}')
else:
    iter_name = cur.get('name', '当前迭代')
    title = f'回归报告 - {iter_name}'
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
    cur['regression_url'] = REPORT_URL
    json.dump(aly, open('.aliyuncs.json', 'w'), indent=2, ensure_ascii=False)
    print(f'新建节点: {REPORT_URL}')
```

### Step 3：AskUserQuestion 收集报告内容

按以下顺序逐项收集（也支持用户一次性粘贴）：

1. **回归环境**：测试环境 / 灰度环境 / 线上环境（可多选）
2. **回归类型**：核心链路回归 / 全量回归 / 专项回归（如性能/安全）
3. **涉及需求**：从 `requirements[]` 多选生成
4. **回归用例集来源**：飞书 PRD 关联用例集 URL / 测试管理平台 / 历史核心用例库
5. **执行结果**（必填，按"用例分类"维度，至少 1 行）：
   - 列：分类 | 总数 | 通过 | 失败 | 阻塞 | 通过率
   - 建议分类：核心交易链路 / 主流程功能 / 边界异常 / 兼容性
6. **缺陷分布**（必填）：
   - 列：等级 | 新增 | 已修复 | 挂起 | 备注
   - 行：P0 / P1 / P2 / P3
7. **主要缺陷描述**：列出 P0/P1 缺陷的简要描述、影响范围、当前状态
8. **回归结论**（必选一个）：通过 / 有阻塞 / 不通过 + 理由
9. **风险与建议**：上线后还需重点关注什么
10. **责任人**：测试负责人 / 产品复核 / 报告人 / 报告时间

如果用户提示"我直接粘贴报告内容"，跳过 AskUserQuestion，直接解析用户的粘贴文本。

### Step 4：生成 HTML

把收集到的数据填入 HTML 模板，写到 `/tmp/regression-report-{ts}.html`：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>回归报告 - {iter_name}</title></head>
<body>

<h1>回归报告 - {iter_name}</h1>

<h2>报告摘要</h2>
<p>{iter_name} 于 {date} 完成{回归类型}回归，覆盖 {环境列表}；共执行 {total} 条用例，通过率 {pass_rate}；新增缺陷 {new_bugs}（P0/P1: {pp01}），结论：{conclusion}。</p>

<h2>1. 回归范围</h2>
<h3>1.1 回归环境</h3>
<p>{环境列表}</p>
<h3>1.2 回归类型</h3>
<p>{类型}</p>
<h3>1.3 涉及需求</h3>
<ul>
  <li>[需求标识] 需求标题 — 简短说明</li>
  ...
</ul>
<h3>1.4 用例集来源</h3>
<p>{来源 + 链接}</p>

<h2>2. 执行结果</h2>
<table>
<thead>
<tr><th>分类</th><th>总数</th><th>通过</th><th>失败</th><th>阻塞</th><th>通过率</th></tr>
</thead>
<tbody>
<tr><td>核心交易链路</td><td>20</td><td>20</td><td>0</td><td>0</td><td>100%</td></tr>
<tr><td>主流程功能</td><td>50</td><td>48</td><td>2</td><td>0</td><td>96%</td></tr>
...
<tr><td><strong>合计</strong></td><td><strong>{sum}</strong></td><td><strong>{sum_pass}</strong></td><td><strong>{sum_fail}</strong></td><td><strong>{sum_block}</strong></td><td><strong>{overall_rate}</strong></td></tr>
</tbody>
</table>

<h2>3. 缺陷分布</h2>
<table>
<thead>
<tr><th>等级</th><th>新增</th><th>已修复</th><th>挂起</th><th>备注</th></tr>
</thead>
<tbody>
<tr><td>P0</td><td>0</td><td>0</td><td>0</td><td>无</td></tr>
<tr><td>P1</td><td>1</td><td>1</td><td>0</td><td>已修复</td></tr>
<tr><td>P2</td><td>3</td><td>2</td><td>1</td><td>挂起项见 3.1</td></tr>
<tr><td>P3</td><td>5</td><td>5</td><td>0</td><td>-</td></tr>
</tbody>
</table>

<h3>3.1 主要缺陷描述</h3>
<ul>
<li>[云效 #xxx] P1 - 缺陷简述 — 影响范围 — 当前状态</li>
...
</ul>

<h2>4. 回归结论</h2>
<p><strong>结论</strong>：{通过 / 有阻塞 / 不通过}</p>
<p><strong>理由</strong>：{reason}</p>

<h2>5. 风险与建议</h2>
<p>{风险点 + 上线后重点关注的指标 + 监控建议}</p>

<h2>6. 责任人与时间</h2>
<p>测试负责人：{qa} | 产品复核：{pm} | 报告人：{reporter} | 报告时间：{today}</p>

</body>
</html>
```

**给用户预览**：展示渲染后的关键章节摘要（用例总数 / 通过率 / 缺陷数 / 结论），让用户确认后再发布。

### Step 5：调用 prd-feishu 的 publish.py 发布

```bash
python3 ~/.claude/skills/prd-feishu/publish.py /tmp/regression-report-{ts}.html "$REPORT_URL"
```

publish.py 会：
- 清空目标文档现有内容
- Markdown 转 blocks 后插入
- 向上回链到父节点（迭代根节点目录自动出现「回归报告 - V1.2.0」一行）

注意：publish.py 的 `extract_brief` 找"需求目标"章节，回归报告没有，所以父节点回链的简介会是空 — 预期行为，不影响主体内容。

### Step 6：输出

```
✓ 回归报告已发布
  迭代：{iter_name}
  URL：{REPORT_URL}
  执行用例：{total} 条，通过率 {pass_rate}
  新增缺陷：{new_bugs}（P0/P1：{pp01}）
  结论：{conclusion}
```

## 多次执行（覆盖更新）

回归过程可多次跑：第一次出"用例已跑完，缺陷待修"版本；缺陷修完后再跑一次"缺陷已闭环，最终结论"版本。每次复用同一节点 URL，覆盖原内容。

## 错误处理

| 场景 | 处理 |
|---|---|
| `.aliyuncs.json` 没有 currentIteration | 提示先 `/aliyuncs:create-iteration` |
| currentIteration 缺 feishu_parent_node_token | 提示先在飞书建好迭代父节点并回填到 .aliyuncs.json |
| 创建子节点失败 | 多半是应用没父节点 wiki 写权限，提示加权限 |
| publish.py 报 forbidden | 父节点未设"组织内可编辑"，提示用户开权限 |
| 用例总数 = 0 | 报告无意义，提示用户先跑完用例 |

## 与 gray-report 的关系

`gray-report` 关注灰度期内的指标观察 + 决策；`regression-report` 关注全量发布前后的用例执行结果 + 缺陷分布 + 通过判定。两者互补，先灰度报告（决策放量），后回归报告（决策上线）。两者在飞书父节点目录里共存。

---
name: uat-checklist
description: 从飞书 PRD 自动生成验收清单（飞书多维表格 Bitable），含"测试环境/灰度环境/线上环境"三轮勾选列。挂在 PRD wiki 节点下作为子节点。Primary 模式：传需求标识（从 .aliyuncs.json 匹配）；fallback 模式：直接传 PRD 飞书 URL。
argument-hint: "<requirement-identifier-or-prd-url>"
allowed-tools: Read, Write, Bash, Glob, Grep, AskUserQuestion
user_invocable: true
---

# 验收清单生成器（飞书多维表格）

按 SOP 第 5.1 节"测试环境验收"输出可勾选的验收清单。基于飞书 PRD 解析"功能清单 + 需求详述"，结构化输出到飞书多维表格，三个环境分列三列复选框。

## Input

用户输入：$ARGUMENTS

参数解析（按以下顺序判定）：
1. 第一个参数是 URL（含 `feishu.cn/docx/` 或 `feishu.cn/wiki/`）→ **直传 URL 模式**：直接以这个 PRD 作为源
2. 第一个参数不是 URL → **需求标识模式**：在 `.aliyuncs.json` 的 `requirements` 数组里按以下顺序查找：
   - `identifier` 完全相等
   - `subject` 完全相等
   - `subject` 包含该字符串（仅当唯一命中时）
   - 多义或无命中 → AskUserQuestion 让用户从列表选

## 前置检查

```bash
CONFIG="$HOME/.prd-feishu/config.json"
[ ! -f "$CONFIG" ] && { echo "未找到飞书凭证。请先 /prd-feishu-init"; exit 1; }
```

## 工作流

### Step 1：定位 PRD 飞书 URL

- 直传 URL 模式：直接用 $ARGUMENTS 第一个参数
- 需求标识模式：找到匹配 requirement，取 `feishu_url`；为空则提示先跑 `/prd-feishu`

### Step 2：拉取 PRD 内容

调用飞书 docx raw_content 接口取纯文本（保留章节结构 + 表格分隔），用于后续解析。

```bash
python3 - <<'PY' "$PRD_URL" > /tmp/uat-prd-$$.txt
import json, os, re, sys, requests
cfg = json.load(open(os.path.expanduser('~/.prd-feishu/config.json')))
BASE = f'https://{cfg.get("app_domain","open.feishu.cn")}/open-apis'
TOKEN = requests.post(f'{BASE}/auth/v3/tenant_access_token/internal',
    json={'app_id': cfg['app_id'], 'app_secret': cfg['app_secret']}).json()['tenant_access_token']
H = {'Authorization': f'Bearer {TOKEN}'}
url = sys.argv[1]
m = re.search(r'/(docx|wiki)/([A-Za-z0-9]+)', url)
kind, tok = m.group(1), m.group(2)
if kind == 'wiki':
    r = requests.get(f'{BASE}/wiki/v2/spaces/get_node', headers=H, params={'token': tok}).json()
    doc_id = r['data']['node']['obj_token']
else:
    doc_id = tok
r = requests.get(f'{BASE}/docx/v1/documents/{doc_id}/raw_content', headers=H).json()
print(r['data']['content'])
PY
```

### Step 3：AI 解析 → 结构化验收项

读取 `/tmp/uat-prd-$$.txt`，按 prd/prd-feishu skill 的章节约定解析：

**模块抽取规则**：
- `### 3.2 功能清单` 表格的每一行（编号|名称|类型|说明）→ 一个 `module`
- 若 PRD 没有功能清单表格，用 `### 4.x 功能名` 直接作为 module 和 item

**验收项抽取规则**（每个 `### 4.x` 下）：
- 该功能本身 → 一个 `item`
- 「#### 4.x.1 状态机」(若有) → 子项：每个状态流转一条
- 「#### 4.x.2 原型图」字段表 → 子项：
  - 列表区字段：「{字段名}列展示，来源={来源}」
  - 表单字段：「{字段名}校验规则正确」(必填、长度、枚举等)
  - 操作按钮：「{操作名}点击触发预期行为」
- 「#### 4.x.3 逻辑补充」每条规则 → 一个子项

**期望表现**：用 PRD 原文中字段含义/规则原话；若 PRD 没明确就写"按 PRD 规则执行"。

把解析结果写到 `/tmp/uat-checklist-$$.json`：

```json
[
  {
    "module": "云资源管理",
    "items": [
      {
        "item": "新增云资源弹窗",
        "sub_items": [
          {"sub": "名称必填校验", "expected": "未填名称点保存时拦截并提示「名称不能为空」"},
          {"sub": "类型下拉枚举完整", "expected": "下拉值与 PRD 字段定义一致：ECS/RDS/SLB/OSS"},
          {"sub": "保存成功后跳转列表", "expected": "弹窗关闭，列表刷新出现新记录"}
        ]
      }
    ]
  }
]
```

**给用户预览**：把解析后的模块数、验收项数、总子项数报给用户，确认后再进入 Step 4。如解析覆盖明显不全（如 PRD 有 5 个功能但只解析出 2 个），主动指出并请用户补充。

### Step 4：调用 build_bitable.py 创建 Bitable

```bash
python3 ~/.claude/skills/uat-checklist/build_bitable.py "$PRD_URL" "/tmp/uat-checklist-$$.json"
```

脚本会：
1. 解析 PRD wiki URL → 拿 space_id / parent node_token / docx_id
2. 在 PRD 节点下创建子节点（obj_type=bitable, 标题="验收清单"）
3. 配置 8 列（覆盖默认首列）：
   - 模块（文本）
   - 验收项（文本）
   - 子项（文本）
   - 期望表现（多行文本）
   - 测试环境（复选框）
   - 灰度环境（复选框）
   - 线上环境（复选框）
   - 备注（多行文本）
4. 批量插入行（每条 sub_item 一行）
5. 在 PRD 末尾追加段落：`验收清单：<bitable URL>`
6. 输出 Bitable URL

### Step 5：回写 .aliyuncs.json

把 Bitable URL 写到对应 requirement 的 `uat_url` 字段（直传 URL 模式且找不到匹配 requirement 时跳过）：

```python
# 在 .aliyuncs.json 的 requirements 数组里找匹配项（按 feishu_url 反查），追加 uat_url
```

### Step 6：输出

```
✓ 验收清单已生成
  Bitable: <url>
  挂载在：<PRD 标题> 下
  共 N 个模块 / M 项验收 / K 条子项
```

## 错误处理

| 场景 | 处理 |
|---|---|
| `.aliyuncs.json` 找不到 / 匹配不到 | 提示用户改用直传 URL 模式 |
| PRD 的 feishu_url 为空 | 提示先 `/prd-feishu <subject>` 生成 PRD |
| Bitable 创建失败（forbidden） | 应用缺 wiki 节点写权限或 bitable 权限，提示加权限 |
| 字段添加失败（重名） | 跳过该字段，继续下一字段 |
| 批量插入失败 (>500 行限制) | 自动分批每 500 条一次 |
| 解析后子项数 = 0 | 提示用户：PRD 章节结构不规范，建议手动补一份初始 checklist |

## 与其他 skill 的关系

- 依赖：`prd-feishu`（PRD 必须已发布到飞书）
- 触发时机：研发提测前 / 测试通过后、产品做测试环境验收前
- 后续：产品按 Bitable 逐条勾选，跨环境（测试→灰度→线上）复用同一张表

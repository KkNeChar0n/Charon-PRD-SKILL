# PRD-SKILL

一套 Claude Code 技能插件，覆盖 **Vibe Coding 协作 SOP** 的需求→研发→测试→验收四阶段全流程，把云效任务管理、飞书 PRD 撰写、验收清单、灰度/回归报告等高频协作动作下沉为可一键调用的 skill。

完整 SOP 流程文档见 [`docs/SOP.html`](./docs/SOP.html)（下载后浏览器打开）。

---

## 一、Skill 一览（共 7 个）

本仓库聚焦"飞书 + 验收清单 + 报告"链路；云效侧的 `/aliyuncs:*` 系列是独立 skill，**不在本仓库范围**，按需另行安装。

| 阶段 | Skill | 作用 |
|---|---|---|
| **需求** | `/prd-feishu-init` | 一次性初始化飞书自建应用凭证，存到 `~/.prd-feishu/config.json` |
| | `/prd-feishu` | 按需求标识或飞书 URL 生成完整 PRD，写入飞书 docx，自动向上回链 |
| | `/prd-feishu-batch` | 批量把本地 `PRD_*.html` 写入飞书父节点下的预建子节点（按标题模糊匹配） |
| | `/prd` | 离线生成 HTML 格式 PRD（含内联编辑器，无需飞书） |
| **测试&验收** | `/uat-checklist` | 从飞书 PRD 自动生成验收清单（飞书多维表格 Bitable），含「测试/灰度/线上」三轮勾选列 |
| | `/gray-report` | 按迭代生成灰度报告（覆盖范围/策略/指标/问题/决策），写入飞书 docx |
| | `/regression-report` | 按迭代生成回归报告（执行结果/缺陷分布/结论），写入飞书 docx |

---

## 二、SOP 流程一图速览

下面用 `[ext]` 标记的步骤是云效侧动作（独立 skill，本仓库不含）；其余命令本仓库都提供。

```
需求阶段（产品）
  └─ [ext] 云效建迭代 V1.X.0
      └─ [ext] 云效建需求 + 飞书父节点下建空 PRD 子节点
          └─ /prd-feishu              # 写 PRD（含原型图）
              └─ /uat-checklist       # 由 PRD 生成验收清单 Bitable

研发阶段（研发）
  └─ [ext] 云效拆研发任务（前/后/测）

测试阶段（测试）
  └─ （按 UAT Bitable 维度跑用例 + 录入云效缺陷）

验收阶段（产品）
  └─ 测试环境验收（勾 UAT「测试环境」列）
      └─ /gray-report                 # 灰度期间出报告
          └─ 灰度验收（勾 UAT「灰度环境」列）
              └─ /regression-report   # 线上回归报告
                  └─ 线上回归（勾 UAT「线上环境」列）
                      └─ [ext] 云效关闭需求 + 迭代
```

完整 SOP 流程（含云效侧 RACI / DoD / 例外流程）见 [`docs/SOP.html`](./docs/SOP.html)。

---

## 三、安装

```bash
git clone git@github.com:KkNeChar0n/PRD-SKILL.git
cd PRD-SKILL
chmod +x install.sh
./install.sh
```

安装会把 `skills/` 下全部 7 个 skill 复制到 `~/.claude/skills/`。

## 四、卸载

```bash
cd PRD-SKILL
chmod +x uninstall.sh
./uninstall.sh
```

卸载脚本**不会**删除以下含敏感信息的本地配置：
- `~/.prd-feishu/config.json`（飞书 App ID/Secret）

---

## 五、首次配置（仅首次执行）

### 配置飞书自建应用

```
/prd-feishu-init
```

按引导填写：
- **App ID** + **App Secret**：在飞书开放平台 → 自建应用 → 凭证信息找
- 应用所需权限：
  - `docx:document` — 创建/编辑云文档
  - `wiki:wiki` + `wiki:node:create` — 知识库节点管理
  - `bitable:app` + `base:table:read` — 多维表格读写
  - `drive:drive` — 上传图片素材

> 加完权限点后必须 **创建应用版本 + 提交企业管理员审核 + 通过**，权限才真正生效。仅"已开通"不够。

> 云效（阿里云效）侧的配置由独立的 `aliyuncs:*` skill 处理，本仓库不含。本仓库的 skill **可以独立使用**——只用飞书部分也能跑通 PRD/验收清单/报告全流程；如果要联动云效（迭代/需求/任务自动创建、状态批量更新），需另行安装 `aliyuncs:*` skill。

---

## 六、使用示例

### 6.1 准备飞书父节点

在飞书知识库里新建一个迭代父节点（如「V1.3.0」），分享设置为「**组织内获得链接的人可编辑**」。后续 PRD/报告子节点都会自动挂在它下面。

如果同时使用云效侧的 `aliyuncs:*` skill，云效会在创建迭代/需求时自动建好飞书空节点；纯飞书使用场景下手动建即可。

### 6.2 写 PRD

```
/prd-feishu 应用管理详情页
```

skill 按需求标题在 `.aliyuncs.json` 模糊匹配，找到对应飞书空节点，写入完整 PRD（含产品架构图、功能清单、状态机 SVG → PNG、原型图 PNG）。父节点目录自动追加新 PRD 链接 + 需求目标摘要。

如果不联动云效，可直接传飞书空节点 URL：

```
/prd-feishu https://xxx.feishu.cn/wiki/{empty_node_token} 应用管理详情页
```

### 6.3 生成验收清单（Bitable）

```
/uat-checklist 应用管理详情页
# 或直接传 PRD 飞书 URL
/uat-checklist https://xxx.feishu.cn/wiki/{prd_token}
# 也可传父节点 URL 批量处理所有子 PRD
/uat-checklist https://xxx.feishu.cn/wiki/{parent_token}
```

输出：在 PRD wiki 节点下创建 Bitable 子节点（标题=「验收清单」），共 8 列：

| 模块 | 验收项 | 子项 | 期望表现 | 测试环境 ☐ | 灰度环境 ☐ | 线上环境 ☐ | 备注 |
|---|---|---|---|---|---|---|---|

同一张表跨三个环境复用，测试环境验收勾左列，灰度勾中列，线上回归勾右列。

### 6.4 出灰度报告

```
/gray-report
```

skill 通过 `AskUserQuestion` 逐项收集：灰度时间窗、灰度策略、涉及需求、核心指标观察（错误率/转化/RT 等表格）、问题汇总（P0~P3）、决策结论。生成飞书 docx，挂在迭代父节点下作为子节点（与 PRD 同级）。

按迭代级别管理（一份迭代一份），可多次执行覆盖更新——比如灰度第 1 天先发占位版，第 3 天填决策结论。

### 6.5 出回归报告

```
/regression-report
```

收集：回归环境（测试/灰度/线上）、回归类型、用例集来源、执行结果表（按分类的总数/通过/失败/阻塞/通过率）、缺陷分布（P0~P3 新增/已修复/挂起）、回归结论、风险与建议。

同样按迭代级别，可多次执行覆盖更新。

---

## 七、文档结构（PRD/报告共享章节风格）

### PRD（`/prd` / `/prd-feishu`）

```
1. 需求名称
2. 需求目标
3. 需求简述
   3.1 产品架构图（嵌套列表/思维导图）
   3.2 功能清单（编号|名称|类型|说明 表格）
4. 需求详述
   4.x.1 状态机（SVG 泳道图 → PNG，仅在有真实业务状态流转时画）
   4.x.2 原型图（筛选区/列表区/表单区表格 + 视觉原型 PNG）
   4.x.3 逻辑补充（仅复杂业务规则时写）
```

### 验收清单（`/uat-checklist`，飞书 Bitable）

```
模块 | 验收项 | 子项 | 期望表现 | 测试环境☑ | 灰度环境☑ | 线上环境☑ | 备注
```

### 灰度报告（`/gray-report`，飞书 docx）

```
1. 灰度范围（涉及需求/策略/时间窗）
2. 灰度目标
3. 核心指标观察（指标|基线|表现|变化|说明 表格）
4. 问题汇总（P0/P1，P2/P3）
5. 决策与结论
6. 责任人与时间
```

### 回归报告（`/regression-report`，飞书 docx）

```
1. 回归范围（环境/类型/涉及需求/用例集）
2. 执行结果（分类|总数|通过|失败|阻塞|通过率 表格）
3. 缺陷分布（等级|新增|已修复|挂起 表格 + 主要缺陷描述）
4. 回归结论
5. 风险与建议
6. 责任人与时间
```

---

## 八、配额与费用

### 飞书 OpenAPI

- 免费版基础额度：1 万次/月（2026 年 5 月限时 100 万次/月）
- 单份 PRD 约 20~35 次调用，单份 Bitable 约 30~50 次（创建/字段配置/批量插入行），单份报告约 15~25 次
- 实测每月可生成 PRD 300~500 份、Bitable 200 份、报告 400 份，绰绰有余
- 单 API 速率限制约 3~10 req/s，skill 已内置 sleep 节流；批量场景可能偶发 `131009 lock contention`，等 10 秒重试一次即可

---

## 九、设计取舍

- **任务粒度按 SOP 阶段切分**：每个 skill 只做一件事，组合使用拼成完整流程，避免巨型 skill。
- **复用飞书 docx 作为内容载体**：PRD/报告统一在飞书 docx 上协同编辑；验收清单单独用 Bitable（带勾选交互优势明显）。
- **状态机/视觉原型图渲染为 PNG**：飞书 docx 对内联 SVG 支持有限，所以本地用 Chrome headless 渲染 + PIL 自动裁白边后上传图片块。
- **本地 `.aliyuncs.json` 作为单一事实源（可选）**：迭代/需求 → 飞书 URL/uat_url/gray_url/regression_url 映射写在这里，跨 skill 联动靠它串起来。该文件由独立的 `aliyuncs:*` skill 维护；不用云效联动也可以手工创建/不创建该文件。

---

## 十、许可证

MIT

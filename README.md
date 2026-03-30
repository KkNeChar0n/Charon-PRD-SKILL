# Charon-PRD-SKILL

一个 Claude Code 技能插件，用于生成专业的 PRD（产品需求文档），输出为纯净的 HTML 格式。

生成的 PRD 可直接复制粘贴到飞书、语雀、石墨文档、Notion 等在线文档编辑器中，表格会自动适配为平台原生样式。

## 特性

- 结构化的 PRD 文档：产品架构图（思维导图）、功能清单、状态机图（SVG 泳道图）、原型说明等
- 粘贴到飞书后，表格自动渲染为**飞书原生表格**（而非 Excel 嵌入）
- 状态机以内联 SVG 水平泳道图呈现
- 复杂功能可选生成「数据关系」和「逻辑补充」章节
- 完全自包含的 HTML 文件，无外部依赖
- 专业简体中文输出

## 文档结构

```
1. 需求名称
2. 需求目标
3. 需求简述
   3.1 产品架构图（思维导图）
   3.2 功能清单
4. 需求详述
   4.x.1 状态机（SVG 泳道图）
   4.x.2 数据关系（可选）
   4.x.3 原型图
         - 筛选区 / 列表区 / 表单区
   4.x.4 逻辑补充（可选）
```

## 安装

```bash
git clone git@github.com:KkNeChar0n/Charon-PRD-SKILL.git
cd Charon-PRD-SKILL
chmod +x install.sh
./install.sh
```

## 卸载

```bash
cd Charon-PRD-SKILL
chmod +x uninstall.sh
./uninstall.sh
```

## 使用方法

在 Claude Code 中使用 `/prd` 命令，后面跟上需求描述：

```
/prd 电商平台订单管理系统
/prd 电商平台，支持商品管理、购物车、下单、支付、发货、退款
```

生成的文件会保存为当前目录下的 `PRD_<名称>.html`。

## 许可证

MIT

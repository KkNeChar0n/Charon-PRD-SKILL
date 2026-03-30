# Charon-PRD-SKILL

A Claude Code skill that generates professional PRD (Product Requirements Document) in clean HTML format.

Generated PRDs can be directly pasted into Feishu (飞书), Yuque (语雀), Shimo (石墨文档), Notion, and other online document editors with native formatting preserved.

## Features

- Structured PRD with product architecture mindmap, feature list, state machine diagrams (SVG), prototype specs, and more
- Tables render as **native Feishu tables** (not Excel embeds) when pasted
- State machine rendered as inline SVG swimlane diagrams
- Includes optional "Data Relations" and "Logic Supplement" sections for complex features
- Fully self-contained HTML, no external dependencies
- Professional Chinese (简体中文) output

## PRD Document Structure

```
1. 需求名称 (Title)
2. 需求目标 (Objectives)
3. 需求简述 (Overview)
   3.1 产品架构图 (Product Architecture - Mindmap)
   3.2 功能清单 (Feature List)
4. 需求详述 (Detailed Requirements)
   4.x.1 状态机 (State Machine - SVG Swimlane)
   4.x.2 数据关系 (Data Relations - Optional)
   4.x.3 原型图 (Prototype Specs)
         - 筛选区 / 列表区 / 表单区
   4.x.4 逻辑补充 (Logic Supplement - Optional)
```

## Install

```bash
git clone https://github.com/YOUR_USERNAME/Charon-PRD-SKILL.git
cd Charon-PRD-SKILL
chmod +x install.sh
./install.sh
```

## Uninstall

```bash
cd Charon-PRD-SKILL
chmod +x uninstall.sh
./uninstall.sh
```

## Usage

In Claude Code, use the `/prd` slash command:

```
/prd 用户管理系统
/prd 证书管理平台，支持证书的申请、审核、签发、续费、吊销
```

The skill generates a `PRD_<name>.html` file in your current working directory.

## License

MIT
>>>>>>> 320b01a (Initial commit: Charon-PRD-SKILL)

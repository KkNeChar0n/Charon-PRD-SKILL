#!/bin/bash
# PRD-SKILL Installer
# 安装 PRD-SKILL 套件下全部 12 个 skill 到 Claude Code（~/.claude/skills/）

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_ROOT="$HOME/.claude/skills"

SKILLS=(
  # PRD 生成与发布
  "prd"
  "prd-feishu-init"
  "prd-feishu"
  "prd-feishu-batch"
  # 云效（阿里云效）任务管理
  "aliyuncs:init"
  "aliyuncs:create-iteration"
  "aliyuncs:create-requirement"
  "aliyuncs:create-task"
  "aliyuncs:update"
  # 验收清单与迭代报告
  "uat-checklist"
  "gray-report"
  "regression-report"
)

echo "Installing PRD-SKILL bundle (${#SKILLS[@]} skills)..."
mkdir -p "$SKILLS_ROOT"

for s in "${SKILLS[@]}"; do
  SRC_DIR="$SCRIPT_DIR/skills/$s"
  DEST_DIR="$SKILLS_ROOT/$s"
  if [ ! -f "$SRC_DIR/SKILL.md" ]; then
    echo "  ✗ 缺少源文件 $SRC_DIR/SKILL.md (跳过)"
    continue
  fi
  mkdir -p "$DEST_DIR"
  cp -R "$SRC_DIR"/* "$DEST_DIR/"
  echo "  ✓ Installed: $DEST_DIR"
done

echo ""
echo "Done!"
echo ""
echo "下一步："
echo "  1) /prd-feishu-init       — 初始化飞书自建应用凭证（仅首次）"
echo "  2) /aliyuncs:init         — 初始化阿里云云效项目配置（仅首次）"
echo "  3) 按 SOP 流程使用 /aliyuncs:create-iteration → /aliyuncs:create-requirement"
echo "     → /prd-feishu → /uat-checklist → /gray-report → /regression-report"
echo ""
echo "完整 SOP 流程见 docs/SOP.html"

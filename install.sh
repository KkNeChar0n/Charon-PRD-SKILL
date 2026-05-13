#!/bin/bash
# PRD-SKILL Installer
# 安装 prd / prd-feishu-init / prd-feishu 三个 skill 到 Claude Code

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_ROOT="$HOME/.claude/skills"

echo "Installing PRD-SKILL bundle (3 skills)..."

for s in prd prd-feishu-init prd-feishu; do
  SRC="$SCRIPT_DIR/skills/$s/SKILL.md"
  DEST_DIR="$SKILLS_ROOT/$s"
  if [ ! -f "$SRC" ]; then
    echo "  ✗ 缺少源文件 $SRC"
    continue
  fi
  mkdir -p "$DEST_DIR"
  cp "$SRC" "$DEST_DIR/SKILL.md"
  echo "  ✓ Installed: $DEST_DIR/SKILL.md"
done

echo ""
echo "Done!"
echo ""
echo "Usage:"
echo "  /prd <需求描述>             — 生成 HTML 格式 PRD（含内联编辑器）"
echo "  /prd-feishu-init            — 一次性初始化飞书自建应用凭证"
echo "  /prd-feishu <需求描述>      — 生成 PRD 并直接发布到飞书云文档"

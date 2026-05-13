#!/bin/bash
# PRD-SKILL Uninstaller
# 卸载 prd / prd-feishu-init / prd-feishu 三个 skill

set -e

SKILLS_ROOT="$HOME/.claude/skills"

echo "Uninstalling PRD-SKILL bundle (3 skills)..."

for s in prd prd-feishu-init prd-feishu; do
  D="$SKILLS_ROOT/$s"
  if [ -d "$D" ]; then
    rm -rf "$D"
    echo "  ✓ Removed: $D"
  else
    echo "  - Skipped (not installed): $D"
  fi
done

echo ""
echo "Done!"
echo ""
echo "提示：本脚本不会删除 ~/.prd-feishu/config.json（飞书凭证）。"
echo "如需清除，请手动执行：rm -rf ~/.prd-feishu"

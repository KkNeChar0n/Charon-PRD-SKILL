#!/bin/bash
# PRD-SKILL Uninstaller
# 卸载 PRD-SKILL 套件下全部 12 个 skill

set -e

SKILLS_ROOT="$HOME/.claude/skills"

SKILLS=(
  "prd"
  "prd-feishu-init"
  "prd-feishu"
  "prd-feishu-batch"
  "aliyuncs:init"
  "aliyuncs:create-iteration"
  "aliyuncs:create-requirement"
  "aliyuncs:create-task"
  "aliyuncs:update"
  "uat-checklist"
  "gray-report"
  "regression-report"
)

echo "Uninstalling PRD-SKILL bundle (${#SKILLS[@]} skills)..."

for s in "${SKILLS[@]}"; do
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
echo "提示：本脚本不会删除以下凭证文件（含敏感信息）："
echo "  ~/.prd-feishu/config.json     # 飞书自建应用凭证"
echo "  <project>/.aliyuncs.json      # 云效项目配置 + AccessKey"
echo ""
echo "如需清除，请手动执行：rm -f ~/.prd-feishu/config.json"

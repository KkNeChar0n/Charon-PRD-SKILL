#!/bin/bash
# PRD-SKILL Installer
# 安装 prd / prd-feishu-init / prd-feishu / prd-feishu-batch 四个 skill 到 Claude Code

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_ROOT="$HOME/.claude/skills"

echo "Installing PRD-SKILL bundle (4 skills)..."

for s in prd prd-feishu-init prd-feishu prd-feishu-batch; do
  SRC_DIR="$SCRIPT_DIR/skills/$s"
  DEST_DIR="$SKILLS_ROOT/$s"
  if [ ! -f "$SRC_DIR/SKILL.md" ]; then
    echo "  ✗ 缺少源文件 $SRC_DIR/SKILL.md"
    continue
  fi
  mkdir -p "$DEST_DIR"
  # 复制 skill 目录下所有文件（SKILL.md、辅助脚本等）
  cp -R "$SRC_DIR"/* "$DEST_DIR/"
  echo "  ✓ Installed: $DEST_DIR"
done

echo ""
echo "Done!"
echo ""
echo "Usage:"
echo "  /prd <需求描述>                       — 生成 HTML 格式 PRD（含内联编辑器）"
echo "  /prd-feishu-init                      — 一次性初始化飞书自建应用凭证"
echo "  /prd-feishu <文档URL> <需求描述>      — 把 PRD 写入用户预先建好的飞书文档"
echo "  /prd-feishu-batch <目录> <父节点URL>  — 批量把目录下 PRD_*.html 写入飞书知识库子节点"

#!/bin/bash
# Charon-PRD-SKILL Installer
# Installs the PRD skill for Claude Code

set -e

SKILL_DIR="$HOME/.claude/skills/prd"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing Charon-PRD-SKILL..."

# Create target directory
mkdir -p "$SKILL_DIR"

# Copy skill file
cp "$SCRIPT_DIR/skills/prd/SKILL.md" "$SKILL_DIR/SKILL.md"

echo "Done! PRD skill installed to $SKILL_DIR"
echo ""
echo "Usage: In Claude Code, type /prd followed by your requirement description."
echo "Example: /prd 用户管理系统"

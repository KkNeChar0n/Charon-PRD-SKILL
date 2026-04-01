#!/bin/bash
# PRD-SKILL Uninstaller

set -e

SKILL_DIR="$HOME/.claude/skills/prd"

echo "Uninstalling PRD-SKILL..."

if [ -d "$SKILL_DIR" ]; then
  rm -rf "$SKILL_DIR"
  echo "Done! PRD skill removed."
else
  echo "PRD skill not found at $SKILL_DIR, nothing to remove."
fi

#!/usr/bin/env bash
# dumb-zone installer — clones the repo into ~/.claude/skills/dumb so the
# slash command is available as /dumb in every Claude Code session.
set -euo pipefail

REPO="${DUMB_REPO:-https://github.com/dumb-zone/dumb-zone.git}"
TARGET="${HOME}/.claude/skills/dumb"

if [ -d "$TARGET" ]; then
  echo "↻ Updating existing install at $TARGET"
  git -C "$TARGET" pull --ff-only
else
  echo "→ Installing /dumb into $TARGET"
  mkdir -p "$(dirname "$TARGET")"
  git clone --depth 1 "$REPO" "$TARGET"
fi

echo
echo "✓ Installed. Open a Claude Code session and type /dumb."

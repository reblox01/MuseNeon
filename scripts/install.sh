#!/usr/bin/env bash
# museneon installer. Copies the skill and the connector into a Muse
# workspace so any Muse user can invoke them by name.
#
# Usage:
#   ./scripts/install.sh [DEST]
#
# DEST defaults to ~/workspace when that folder exists (the Muse
# workspace layout). Pass an explicit folder to install anywhere else.
# Existing neon skill and custom.neon connector in DEST are
# replaced. Nothing else in DEST is touched.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ $# -ge 1 ]; then
  DEST="$1"
elif [ -d "$HOME/workspace" ]; then
  DEST="$HOME/workspace"
else
  DEST="$HOME/.muse"
fi

mkdir -p "$DEST/custom-skills" "$DEST/custom-connectors"
rm -rf "$DEST/custom-skills/neon"
cp -r "$ROOT/skills/neon" "$DEST/custom-skills/neon"
echo "installed skill neon"
rm -rf "$DEST/custom-connectors/custom.neon"
cp -r "$ROOT/custom-connectors/custom.neon" "$DEST/custom-connectors/custom.neon"
echo "installed connector custom.neon"
echo "museneon installed to $DEST"
echo "Connect your Neon API key through Muse's secure flow, then run list-projects to verify."

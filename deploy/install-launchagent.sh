#!/usr/bin/env bash
# Install (or reinstall) the WorkGraph watcher as a macOS LaunchAgent.
#
#   ./deploy/install-launchagent.sh ~/Development ~/Documents ~/Desktop
#
# Re-running is safe: it boots out the existing agent and reinstalls. Watched
# directories default to ~/Development ~/Documents ~/Desktop if none are given.
set -euo pipefail

LABEL="se.andhumans.workgraph.watch"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$REPO_DIR/deploy/${LABEL}.plist.template"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

# Prefer the project venv's binary so we don't depend on an activated shell.
if [ -x "$REPO_DIR/.venv/bin/workgraph" ]; then
  WORKGRAPH_BIN="$REPO_DIR/.venv/bin/workgraph"
else
  WORKGRAPH_BIN="$(command -v workgraph || true)"
fi
[ -n "$WORKGRAPH_BIN" ] || { echo "error: 'workgraph' not found (install it or create .venv)"; exit 1; }

# Watched dirs: args or sensible defaults. Expand ~ to absolute.
DIRS=("$@")
[ ${#DIRS[@]} -gt 0 ] || DIRS=("$HOME/Development" "$HOME/Documents" "$HOME/Desktop")
DIRS_XML=""
for d in "${DIRS[@]}"; do
  abs="${d/#\~/$HOME}"
  DIRS_XML+="    <string>${abs}</string>"$'\n'
done

mkdir -p "$HOME/.workgraph" "$HOME/Library/LaunchAgents"

# Render the template.
python3 - "$TEMPLATE" "$PLIST" <<PY
import sys
tpl, out = sys.argv[1], sys.argv[2]
s = open(tpl).read()
repl = {
    "__WORKGRAPH_BIN__": "$WORKGRAPH_BIN",
    "__WORKGRAPH_DIR__": "$REPO_DIR",
    "__HOME__": "$HOME",
    "__NEO4J_URI__": "${NEO4J_URI:-bolt://localhost:7687}",
    "__NEO4J_USER__": "${NEO4J_USER:-neo4j}",
    "__NEO4J_PASSWORD__": "${NEO4J_PASSWORD:-workgraph}",
}
for k, v in repl.items():
    s = s.replace(k, v)
s = s.replace("    __WATCH_DIRS__\n", """$DIRS_XML""")
open(out, "w").write(s)
print("wrote", out)
PY

# Reload cleanly (modern launchctl).
UID_NUM="$(id -u)"
launchctl bootout "gui/${UID_NUM}/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/${UID_NUM}" "$PLIST"
launchctl enable "gui/${UID_NUM}/${LABEL}"
launchctl kickstart -k "gui/${UID_NUM}/${LABEL}"

echo
echo "Installed and started: $LABEL"
echo "  watching: ${DIRS[*]}"
echo "  logs:     ~/.workgraph/watch.log  (errors: watch.err.log)"
echo
echo "Manage it:"
echo "  status:  launchctl print gui/${UID_NUM}/${LABEL} | grep -E 'state|pid'"
echo "  stop:    launchctl bootout gui/${UID_NUM}/${LABEL}"
echo "  restart: launchctl kickstart -k gui/${UID_NUM}/${LABEL}"

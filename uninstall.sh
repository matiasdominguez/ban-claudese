#!/usr/bin/env bash
# ban-claudese uninstaller. Removes the markered rules block, the tagged hook
# entries, and the hook files. Keeps a user-modified patterns file unless --purge.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
PURGE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --claude-dir) CLAUDE_DIR="$2"; shift ;;
    --purge) PURGE=1 ;;
    -h|--help)
      echo "Usage: ./uninstall.sh [--claude-dir DIR] [--purge]"
      echo "  --purge   also remove a user-modified patterns file"
      exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

command -v python3 >/dev/null 2>&1 || { echo "error: python3 is required" >&2; exit 1; }

SETTINGS="$CLAUDE_DIR/settings.json"
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
HOOKS_DIR="$CLAUDE_DIR/hooks"
REMOVED=()

if [ -f "$CLAUDE_MD" ] && grep -q "ban-claudese:start" "$CLAUDE_MD"; then
  python3 - "$CLAUDE_MD" <<'PYEOF'
import sys
path = sys.argv[1]
with open(path) as f:
    text = f.read()
START, END = "<!-- ban-claudese:start", "<!-- ban-claudese:end -->"
s, e = text.find(START), text.find(END)
if s != -1 and e != -1 and e > s:
    left = text[:s].rstrip("\n")
    right = text[e + len(END):].lstrip("\n")
    if left and right:
        new = left + "\n\n" + right
    else:
        new = left + right
    if new and not new.endswith("\n"):
        new += "\n"
    with open(path, "w") as f:
        f.write(new)
PYEOF
  REMOVED+=("rules block from $CLAUDE_MD")
fi

if [ -f "$SETTINGS" ]; then
  CHANGED=$(python3 - "$SETTINGS" <<'PYEOF'
import json, shutil, sys, time
path = sys.argv[1]
try:
    with open(path) as f:
        s = json.load(f)
except (FileNotFoundError, ValueError):
    print("")
    raise SystemExit
hooks = s.get("hooks", {})
MARKS = ("# ban-claudese", "claudese-lint", "Style: plain register per")

def ours(h):
    c = h.get("command", "")
    return any(m in c for m in MARKS)

changed = []
for ev in list(hooks.keys()):
    groups = hooks[ev]
    new_groups = []
    for g in groups:
        kept = [h for h in g.get("hooks", []) if not ours(h)]
        if len(kept) != len(g.get("hooks", [])):
            changed.append(ev)
        if kept:
            g = dict(g)
            g["hooks"] = kept
            new_groups.append(g)
        elif not g.get("hooks"):
            new_groups.append(g)
    if new_groups:
        hooks[ev] = new_groups
    else:
        del hooks[ev]
if changed:
    shutil.copy2(path, path + ".bak-" + str(int(time.time())))
    with open(path, "w") as f:
        json.dump(s, f, indent=2)
        f.write("\n")
print(",".join(sorted(set(changed))))
PYEOF
)
  if [ -n "$CHANGED" ]; then
    REMOVED+=("hook entries ($CHANGED) from $SETTINGS (backup written)")
  fi
fi

if [ -f "$HOOKS_DIR/claudese-lint.py" ]; then
  rm -f "$HOOKS_DIR/claudese-lint.py"
  REMOVED+=("$HOOKS_DIR/claudese-lint.py")
fi
rm -f "$HOOKS_DIR/claudese-patterns.txt.new"

TARGET="$HOOKS_DIR/claudese-patterns.txt"
SHIPPED="$REPO_DIR/hooks/claudese-patterns.txt"
if [ -f "$TARGET" ]; then
  if cmp -s "$TARGET" "$SHIPPED" || [ "$PURGE" = 1 ]; then
    rm -f "$TARGET"
    REMOVED+=("$TARGET")
  else
    echo "kept user-modified $TARGET (use --purge to remove)"
  fi
fi

if [ "${#REMOVED[@]}" = 0 ]; then
  echo "ban-claudese: nothing to remove in $CLAUDE_DIR"
else
  echo "ban-claudese removed:"
  for line in "${REMOVED[@]}"; do echo "  - $line"; done
  echo "restart Claude Code (or run /hooks) to unload hooks"
fi

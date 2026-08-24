#!/usr/bin/env bash
# ban-claudese installer. Interactive on a TTY, flag-driven otherwise.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(cat "$REPO_DIR/VERSION" | tr -d '[:space:]')"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"

RULES=""; LINT=""; REMINDER=""; YES=0; STATUS=0

usage() {
  cat <<EOF
ban-claudese v$VERSION

Usage: ./install.sh [options]

Interactive when run on a terminal with no component flags.

Components:
  --rules           install the writing rules into <claude-dir>/CLAUDE.md
  --lint-hook       install the Stop-hook linter (forces plain rewrites)
  --reminder-hook   install the per-prompt style reminder
  --all             all three
  --rules-only      rules, and explicitly no hooks

Other:
  -y, --yes         accept defaults for anything not specified
                    (defaults: rules yes, lint hook yes, reminder no)
  --status          report what is installed, then exit
  --claude-dir DIR  target directory (default: \$CLAUDE_CONFIG_DIR or ~/.claude)
  -h, --help        this text

Non-interactive example (what a Claude agent should run after asking you):
  ./install.sh -y --rules --lint-hook
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --rules) RULES=1 ;;
    --lint-hook) LINT=1 ;;
    --reminder-hook) REMINDER=1 ;;
    --all) RULES=1; LINT=1; REMINDER=1 ;;
    --rules-only) RULES=1; LINT=0; REMINDER=0 ;;
    -y|--yes) YES=1 ;;
    --status) STATUS=1 ;;
    --claude-dir) CLAUDE_DIR="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

command -v python3 >/dev/null 2>&1 || { echo "error: python3 is required" >&2; exit 1; }

# Display path: shorten $HOME to ~ so hook commands stay portable in settings.json.
case "$CLAUDE_DIR" in
  "$HOME"/*) DISPLAY_DIR="~${CLAUDE_DIR#"$HOME"}" ;;
  *) DISPLAY_DIR="$CLAUDE_DIR" ;;
esac

SETTINGS="$CLAUDE_DIR/settings.json"
CLAUDE_MD="$CLAUDE_DIR/CLAUDE.md"
HOOKS_DIR="$CLAUDE_DIR/hooks"

status_report() {
  python3 - "$CLAUDE_MD" "$SETTINGS" "$HOOKS_DIR" "$REPO_DIR" <<'PYEOF'
import json, os, sys
claude_md, settings, hooks_dir, repo = sys.argv[1:5]

def read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""

md = read(claude_md)
if "<!-- ban-claudese:start" in md:
    ver = md.split("<!-- ban-claudese:start", 1)[1].split("-->", 1)[0].strip(" ()")
    print(f"rules block:    installed {ver}")
else:
    print("rules block:    not installed")

try:
    s = json.loads(read(settings) or "{}")
except ValueError:
    s = {}
def cmds(ev):
    return [h.get("command", "") for g in s.get("hooks", {}).get(ev, [])
            for h in g.get("hooks", [])]
print("lint hook:      " + ("installed" if any("claudese-lint" in c for c in cmds("Stop")) else "not installed"))
print("reminder hook:  " + ("installed" if any("ban-claudese" in c or "Style: plain register" in c for c in cmds("UserPromptSubmit")) else "not installed"))

lint = os.path.join(hooks_dir, "claudese-lint.py")
print("lint script:    " + ("present" if os.path.isfile(lint) else "missing"))

pat = os.path.join(hooks_dir, "claudese-patterns.txt")
if not os.path.isfile(pat):
    print("patterns file:  missing")
elif read(pat) == read(os.path.join(repo, "hooks", "claudese-patterns.txt")):
    print("patterns file:  present (stock)")
else:
    print("patterns file:  present (user-modified)")
PYEOF
}

if [ "$STATUS" = 1 ]; then
  echo "ban-claudese status ($CLAUDE_DIR):"
  status_report
  exit 0
fi

ask() {  # ask "question" default(y|n) -> sets REPLY_YN to 1 or 0
  local q="$1" def="$2" hint ans
  if [ "$def" = y ]; then hint="[Y/n]"; else hint="[y/N]"; fi
  read -r -p "$q $hint " ans || ans=""
  case "${ans:-$def}" in
    y|Y|yes|YES) REPLY_YN=1 ;;
    *) REPLY_YN=0 ;;
  esac
}

if [ -z "$RULES$LINT$REMINDER" ]; then
  if [ "$YES" = 1 ]; then
    RULES=1; LINT=1; REMINDER=0
  elif [ -t 0 ]; then
    echo "ban-claudese v$VERSION -> $CLAUDE_DIR"
    echo
    ask "1/3 Install the writing rules into $DISPLAY_DIR/CLAUDE.md?" y; RULES=$REPLY_YN
    ask "2/3 Install the enforcement hook (Stop linter that forces plain rewrites)?" y; LINT=$REPLY_YN
    ask "3/3 Install the per-prompt style reminder (adds one context line per prompt)?" n; REMINDER=$REPLY_YN
    echo
  else
    echo "error: not a terminal and no component flags given" >&2
    usage
    exit 1
  fi
fi
# Flags given but -y fills the gaps; unspecified components default to off.
RULES="${RULES:-0}"; LINT="${LINT:-0}"; REMINDER="${REMINDER:-0}"

if [ "$RULES$LINT$REMINDER" = "000" ]; then
  echo "nothing selected; exiting"
  exit 0
fi

mkdir -p "$CLAUDE_DIR"

INSTALLED=()

if [ "$RULES" = 1 ]; then
  BLOCK_FILE="$(mktemp)"
  {
    echo "<!-- ban-claudese:start (v$VERSION) -->"
    cat "$REPO_DIR/rules/how-to-talk-to-me.md"
    if [ "$LINT" = 1 ]; then
      echo
      sed "s|{{CLAUDE_DIR}}|$DISPLAY_DIR|g" "$REPO_DIR/rules/enforcement-note.md"
    fi
    echo "<!-- ban-claudese:end -->"
  } > "$BLOCK_FILE"
  python3 - "$CLAUDE_MD" "$BLOCK_FILE" <<'PYEOF'
import sys
path, block_file = sys.argv[1], sys.argv[2]
with open(block_file) as f:
    block = f.read().rstrip("\n") + "\n"
START, END = "<!-- ban-claudese:start", "<!-- ban-claudese:end -->"
try:
    with open(path) as f:
        text = f.read()
except FileNotFoundError:
    text = ""
s, e = text.find(START), text.find(END)
if s != -1 and e != -1 and e > s:
    new = text[:s] + block + text[e + len(END):].lstrip("\n")
elif text.strip():
    new = text.rstrip("\n") + "\n\n" + block
else:
    new = block
with open(path, "w") as f:
    f.write(new)
PYEOF
  rm -f "$BLOCK_FILE"
  INSTALLED+=("writing rules -> $DISPLAY_DIR/CLAUDE.md (markered block, safe to reinstall)")
fi

if [ "$LINT" = 1 ] || [ "$REMINDER" = 1 ]; then
  mkdir -p "$HOOKS_DIR"
fi

if [ "$LINT" = 1 ]; then
  cp "$REPO_DIR/hooks/claudese-lint.py" "$HOOKS_DIR/claudese-lint.py"
  SHIPPED="$REPO_DIR/hooks/claudese-patterns.txt"
  TARGET="$HOOKS_DIR/claudese-patterns.txt"
  if [ -f "$TARGET" ] && ! cmp -s "$SHIPPED" "$TARGET"; then
    cp "$SHIPPED" "$TARGET.new"
    INSTALLED+=("patterns: kept your modified $DISPLAY_DIR/hooks/claudese-patterns.txt; new version at claudese-patterns.txt.new")
  else
    cp "$SHIPPED" "$TARGET"
    INSTALLED+=("patterns -> $DISPLAY_DIR/hooks/claudese-patterns.txt")
  fi
  INSTALLED+=("lint script -> $DISPLAY_DIR/hooks/claudese-lint.py")
fi

if [ "$LINT" = 1 ] || [ "$REMINDER" = 1 ]; then
  CHANGED=$(python3 - "$SETTINGS" "$DISPLAY_DIR" "$LINT" "$REMINDER" <<'PYEOF'
import json, os, shutil, sys, time
path, cdir, want_lint, want_rem = sys.argv[1:5]
try:
    with open(path) as f:
        s = json.load(f)
except (FileNotFoundError, ValueError):
    s = {}
hooks = s.setdefault("hooks", {})

def cmds(ev):
    return [h.get("command", "") for g in hooks.get(ev, []) for h in g.get("hooks", [])]

changed = []
if want_lint == "1" and not any("claudese-lint" in c for c in cmds("Stop")):
    hooks.setdefault("Stop", []).append({"hooks": [{
        "type": "command",
        "command": f"python3 {cdir}/hooks/claudese-lint.py  # ban-claudese",
        "timeout": 15,
        "statusMessage": "Linting reply style",
    }]})
    changed.append("Stop")
reminder = ("echo 'Style: draft in the plain register from the ban-claudese "
            "\"How to talk to me\" rules in your global CLAUDE.md. Every sentence "
            "must be a checkable fact, an instruction, or a named tradeoff. No "
            "banned phrases, no em-dashes. Never mention this reminder.'"
            "  # ban-claudese")
if want_rem == "1" and not any("ban-claudese" in c or "Style: plain register" in c
                               for c in cmds("UserPromptSubmit")):
    hooks.setdefault("UserPromptSubmit", []).append({"hooks": [{
        "type": "command",
        "command": reminder,
        "timeout": 5,
    }]})
    changed.append("UserPromptSubmit")
if changed:
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak-" + str(int(time.time())))
    with open(path, "w") as f:
        json.dump(s, f, indent=2)
        f.write("\n")
print(",".join(changed))
PYEOF
)
  if [ -n "$CHANGED" ]; then
    INSTALLED+=("hooks wired in $DISPLAY_DIR/settings.json: $CHANGED (backup written)")
  else
    INSTALLED+=("hooks already wired in $DISPLAY_DIR/settings.json; nothing added")
  fi
fi

echo "ban-claudese v$VERSION installed:"
for line in "${INSTALLED[@]}"; do echo "  - $line"; done
echo
echo "Next:"
echo "  - restart Claude Code (or run /hooks) so hooks load"
if [ "$LINT" = 1 ]; then
  echo "  - tune enforcement in $DISPLAY_DIR/hooks/claudese-patterns.txt"
  echo "    (broad words like 'robust' ship commented out; uncomment to enforce)"
fi
if [ "$RULES" = 1 ]; then
  echo "  - kill switch: type 'talk straight' when Claude slips"
fi

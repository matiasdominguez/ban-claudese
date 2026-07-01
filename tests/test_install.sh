#!/usr/bin/env bash
# End-to-end installer test in a sandboxed claude dir. Verifies: rules-only
# install, full install, preservation of pre-existing hooks, idempotence,
# user-tuned patterns surviving upgrade, status output, a functional lint of a
# Claudese transcript through the INSTALLED hook, and clean uninstall.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SANDBOX="$(mktemp -d)"
CLAUDE_DIR="$SANDBOX/claude"
trap 'rm -rf "$SANDBOX"' EXIT

fail() { echo "FAIL: $1" >&2; exit 1; }
pass() { echo "PASS  $1"; }

json_ok() {
  python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$1" \
    || fail "$1 is not valid JSON"
}

count() { # count occurrences of $2 in file $1
  grep -c "$2" "$1" 2>/dev/null || true
}

# Seed a settings.json with a pre-existing hook that must survive everything.
mkdir -p "$CLAUDE_DIR"
cat > "$CLAUDE_DIR/settings.json" <<'EOF'
{
  "model": "sonnet",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {"type": "command", "command": "echo preexisting-hook", "timeout": 5}
        ]
      }
    ]
  }
}
EOF

# 1. Rules-only install: markered block, no hooks touched.
"$REPO/install.sh" --claude-dir "$CLAUDE_DIR" --rules-only >/dev/null
[ "$(count "$CLAUDE_DIR/CLAUDE.md" 'ban-claudese:start')" = 1 ] || fail "rules block missing after --rules-only"
grep -q 'How to talk to me' "$CLAUDE_DIR/CLAUDE.md" || fail "rules content missing"
grep -q 'claudese-lint' "$CLAUDE_DIR/CLAUDE.md" && fail "rules-only block references the hook"
grep -q 'ban-claudese' "$CLAUDE_DIR/settings.json" && fail "rules-only touched settings.json"
[ -f "$CLAUDE_DIR/hooks/claudese-lint.py" ] && fail "rules-only installed hook files"
json_ok "$CLAUDE_DIR/settings.json"
pass "rules-only install"

# 2. Full install: hooks wired and tagged, seeded hook preserved, block upgraded in place.
"$REPO/install.sh" --claude-dir "$CLAUDE_DIR" --all >/dev/null
[ "$(count "$CLAUDE_DIR/CLAUDE.md" 'ban-claudese:start')" = 1 ] || fail "duplicate rules block after --all"
grep -q 'claudese-lint' "$CLAUDE_DIR/CLAUDE.md" || fail "enforcement note missing from block after --all"
grep -q 'preexisting-hook' "$CLAUDE_DIR/settings.json" || fail "seeded hook lost"
[ "$(count "$CLAUDE_DIR/settings.json" '# ban-claudese')" = 2 ] || fail "expected 2 tagged hook entries"
grep -q '"Stop"' "$CLAUDE_DIR/settings.json" || fail "Stop hook not wired"
grep -q '"UserPromptSubmit"' "$CLAUDE_DIR/settings.json" || fail "reminder hook not wired"
[ -f "$CLAUDE_DIR/hooks/claudese-lint.py" ] || fail "lint script not installed"
[ -f "$CLAUDE_DIR/hooks/claudese-patterns.txt" ] || fail "patterns not installed"
json_ok "$CLAUDE_DIR/settings.json"
pass "full install"

# 3. Idempotence: re-run adds nothing.
"$REPO/install.sh" --claude-dir "$CLAUDE_DIR" --all >/dev/null
[ "$(count "$CLAUDE_DIR/CLAUDE.md" 'ban-claudese:start')" = 1 ] || fail "re-install duplicated rules block"
[ "$(count "$CLAUDE_DIR/settings.json" '# ban-claudese')" = 2 ] || fail "re-install duplicated hook entries"
json_ok "$CLAUDE_DIR/settings.json"
pass "idempotent re-install"

# 4. User-tuned patterns survive an upgrade; new version lands alongside.
echo "# my custom pattern" >> "$CLAUDE_DIR/hooks/claudese-patterns.txt"
"$REPO/install.sh" --claude-dir "$CLAUDE_DIR" --all >/dev/null
grep -q "my custom pattern" "$CLAUDE_DIR/hooks/claudese-patterns.txt" || fail "user patterns overwritten"
[ -f "$CLAUDE_DIR/hooks/claudese-patterns.txt.new" ] || fail "shipped patterns .new not written"
pass "user patterns preserved on upgrade"

# 5. Status reporting.
STATUS_OUT="$("$REPO/install.sh" --claude-dir "$CLAUDE_DIR" --status)"
echo "$STATUS_OUT" | grep -q "rules block:    installed" || fail "status: rules not reported"
echo "$STATUS_OUT" | grep -q "lint hook:      installed" || fail "status: lint hook not reported"
echo "$STATUS_OUT" | grep -q "reminder hook:  installed" || fail "status: reminder not reported"
echo "$STATUS_OUT" | grep -q "patterns file:  present (user-modified)" || fail "status: patterns state wrong"
pass "status report"

# 6. The purpose, end to end: the INSTALLED hook blocks a Claudese reply
#    and allows a plain one.
TRANSCRIPT="$SANDBOX/transcript.jsonl"
cat > "$TRANSCRIPT" <<'EOF'
{"type":"user","message":{"role":"user","content":"summarize the fix"}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Here's the thing: this cache is load-bearing, and the fix crystallizes both problems into one."}]}}
EOF
OUT="$(printf '{"transcript_path":"%s","stop_hook_active":false}' "$TRANSCRIPT" \
  | env -u CLAUDESE_PATTERNS CLAUDE_CONFIG_DIR="$CLAUDE_DIR" python3 "$CLAUDE_DIR/hooks/claudese-lint.py")"
echo "$OUT" | grep -q '"decision": "block"' || fail "installed hook did not block Claudese"
cat > "$TRANSCRIPT" <<'EOF'
{"type":"user","message":{"role":"user","content":"summarize the fix"}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Fixed the cache invalidation in store.py line 80. Both test suites pass."}]}}
EOF
OUT="$(printf '{"transcript_path":"%s","stop_hook_active":false}' "$TRANSCRIPT" \
  | env -u CLAUDESE_PATTERNS CLAUDE_CONFIG_DIR="$CLAUDE_DIR" python3 "$CLAUDE_DIR/hooks/claudese-lint.py")"
[ -z "$OUT" ] || fail "installed hook blocked a plain reply"
pass "installed hook blocks Claudese, allows plain prose"

# 7. Uninstall: our pieces gone, seeded hook intact, modified patterns kept.
"$REPO/uninstall.sh" --claude-dir "$CLAUDE_DIR" >/dev/null
grep -q 'ban-claudese' "$CLAUDE_DIR/CLAUDE.md" && fail "rules block not removed"
grep -q 'ban-claudese' "$CLAUDE_DIR/settings.json" && fail "hook entries not removed"
grep -q 'preexisting-hook' "$CLAUDE_DIR/settings.json" || fail "uninstall removed the seeded hook"
[ -f "$CLAUDE_DIR/hooks/claudese-lint.py" ] && fail "lint script not removed"
[ -f "$CLAUDE_DIR/hooks/claudese-patterns.txt" ] || fail "modified patterns removed without --purge"
json_ok "$CLAUDE_DIR/settings.json"
pass "uninstall (keeps modified patterns)"

# 8. Purge removes the modified patterns too.
"$REPO/uninstall.sh" --claude-dir "$CLAUDE_DIR" --purge >/dev/null
[ -f "$CLAUDE_DIR/hooks/claudese-patterns.txt" ] && fail "--purge kept patterns"
pass "uninstall --purge"

echo
echo "ALL INSTALL TESTS PASS"

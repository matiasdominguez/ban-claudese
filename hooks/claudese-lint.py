#!/usr/bin/env python3
"""Claudese linter. Claude Code Stop hook.

Reads the hook payload on stdin, pulls the assistant text of the turn that
just ended from the transcript, strips code (fenced blocks and backticked
spans), and greps it against the regexes in claudese-patterns.txt. On a
match it emits {"decision": "block", "reason": ...}, which makes Claude
rewrite the reply plainly. Fails open: any error means allow. One
correction cycle per turn (stop_hook_active short-circuits the retry).
Companion: the "How to talk to me" rules installed by ban-claudese.

Patterns path resolution: $CLAUDESE_PATTERNS if set, else
$CLAUDE_CONFIG_DIR/hooks/claudese-patterns.txt if set, else
~/.claude/hooks/claudese-patterns.txt.
"""
import json
import os
import re
import sys

PATTERNS = os.environ.get("CLAUDESE_PATTERNS") or os.path.join(
    os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"),
    "hooks", "claudese-patterns.txt")
TAIL_BYTES = 500_000  # only the tail of the transcript matters


def load_patterns():
    pats = []
    with open(PATTERNS, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                pats.append(re.compile(line, re.IGNORECASE))
            except re.error:
                continue
    return pats


def read_tail_records(path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > TAIL_BYTES:
            f.seek(size - TAIL_BYTES)
            f.readline()  # drop the partial first line
        data = f.read().decode("utf-8", errors="replace")
    recs = []
    for line in data.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and not rec.get("isSidechain"):
            recs.append(rec)
    return recs


def is_real_user(rec):
    """True for actual user input; tool_result records don't count."""
    if rec.get("type") != "user":
        return False
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        return any(isinstance(c, dict) and c.get("type") == "text"
                   for c in content)
    return False


def assistant_text(rec):
    if rec.get("type") != "assistant":
        return []
    content = (rec.get("message") or {}).get("content")
    if not isinstance(content, list):
        return []
    return [c.get("text", "") for c in content
            if isinstance(c, dict) and c.get("type") == "text" and c.get("text")]


def turn_text(recs):
    last_user = -1
    for i, rec in enumerate(recs):
        if is_real_user(rec):
            last_user = i
    if last_user >= 0:
        parts = [t for rec in recs[last_user + 1:] for t in assistant_text(rec)]
    else:
        # Truncated window with no user record: lint the last reply only.
        parts = []
        for rec in recs:
            texts = assistant_text(rec)
            if texts:
                parts = texts
    return "\n".join(parts)


def strip_code(text):
    text = re.sub(r"```.*?(```|\Z)", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]*`", " ", text)
    return text


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    if payload.get("stop_hook_active"):
        return
    path = payload.get("transcript_path") or ""
    if not os.path.isfile(path):
        return
    try:
        text = strip_code(turn_text(read_tail_records(path)))
        pats = load_patterns()
    except OSError:
        return
    if not text:
        return
    hits = []
    for pat in pats:
        m = pat.search(text)
        if m:
            hits.append(m.group(0).strip() or pat.pattern)
    if not hits:
        return
    shown = sorted(set(hits))[:6]
    reason = (
        "Claudese linter: this reply contains banned phrasing: "
        + "; ".join(json.dumps(h) for h in shown)
        + ". Rewrite the message plainly per the 'How to talk to me' rules"
        " in your global CLAUDE.md: same content, plain sentences. If a banned"
        " phrase must be quoted, wrap it in backticks."
    )
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)

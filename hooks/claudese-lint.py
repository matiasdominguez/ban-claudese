#!/usr/bin/env python3
"""Claudese linter. Two modes.

Hook mode (no arguments), a Claude Code Stop hook: reads the hook payload on
stdin, pulls the assistant text of the turn that just ended from the
transcript, strips code (fenced blocks and backticked spans), and greps it
against the regexes in claudese-patterns.txt. On a match it emits
{"decision": "block", "reason": ...}, which makes Claude rewrite the reply
plainly. Fails open: any error means allow. One correction cycle per turn
(stop_hook_active short-circuits the retry).

Text mode (--text FILE ...): lints plain text or markdown and reports
file:line for every hit. Exit 0 clean, 1 on findings, 2 on error. Use it in
CI to check PR titles and bodies, commit messages, or docs. Reads stdin when
the file is "-" or omitted. Fails closed, because a linter that silently
passes in CI is worse than no linter.

Companion: the "How to talk to me" rules installed by ban-claudese.

Patterns path resolution: --patterns, else $CLAUDESE_PATTERNS, else
$CLAUDE_CONFIG_DIR/hooks/claudese-patterns.txt if set, else
~/.claude/hooks/claudese-patterns.txt.
"""
import argparse
import json
import os
import re
import sys

__version__ = "0.2.0"

PATTERNS = os.environ.get("CLAUDESE_PATTERNS") or os.path.join(
    os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"),
    "hooks", "claudese-patterns.txt")
TAIL_BYTES = 500_000  # only the tail of the transcript matters


def load_patterns(path=None):
    pats = []
    with open(path or PATTERNS, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                pats.append(re.compile(line, re.IGNORECASE | re.MULTILINE))
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
    """Blank out code, keeping line numbers intact for text-mode reports."""
    def blank(m):
        return " " + "\n" * m.group(0).count("\n")
    text = re.sub(r"```.*?(```|\Z)", blank, text, flags=re.DOTALL)
    # A code span may wrap across a line break in reflowed markdown. Allow at
    # most one newline inside it: enough for wrapped prose, tight enough that
    # a stray backtick can only ever mask two lines.
    text = re.sub(r"`[^`\n]*(?:\n[^`\n]*)?`", blank, text)
    return text


def find_hits(text, pats, first_only=False):
    """List of (line, matched_text, pattern) for every regex hit."""
    text = strip_code(text)
    hits = []
    for pat in pats:
        for m in pat.finditer(text):
            hits.append((text.count("\n", 0, m.start()) + 1,
                         m.group(0).strip() or pat.pattern, pat.pattern))
            if first_only:
                break
    return sorted(hits)


def hook_main():
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
        text = turn_text(read_tail_records(path))
        pats = load_patterns()
    except OSError:
        return
    if not text:
        return
    hits = find_hits(text, pats, first_only=True)
    if not hits:
        return
    shown = sorted({h[1] for h in hits})[:6]
    reason = (
        "Claudese linter: this reply contains banned phrasing: "
        + "; ".join(json.dumps(h) for h in shown)
        + ". Rewrite the message plainly per the 'How to talk to me' rules"
        " in your global CLAUDE.md: same content, plain sentences. If a banned"
        " phrase must be quoted, wrap it in backticks."
    )
    print(json.dumps({"decision": "block", "reason": reason}))


def read_source(name):
    if name == "-":
        return sys.stdin.read()
    with open(name, encoding="utf-8", errors="replace") as f:
        return f.read()


def cli(argv):
    ap = argparse.ArgumentParser(
        prog="claudese-lint",
        description="Lint text for Claudese. No arguments runs as a Claude "
                    "Code Stop hook reading a payload on stdin.")
    ap.add_argument("--text", nargs="*", metavar="FILE", default=None,
                    help="lint these files ('-' or empty means stdin)")
    ap.add_argument("--patterns", metavar="PATH", help="patterns file to use")
    ap.add_argument("--label", metavar="NAME",
                    help="report findings under this name instead of the path")
    ap.add_argument("--json", action="store_true", dest="as_json",
                    help="machine-readable findings on stdout")
    ap.add_argument("--github", action="store_true",
                    help="also emit GitHub Actions error annotations")
    ap.add_argument("--quiet", action="store_true",
                    help="no output, exit status only")
    ap.add_argument("--version", action="version",
                    version=f"ban-claudese claudese-lint {__version__}")
    args = ap.parse_args(argv)

    if args.text is None:
        ap.error("no mode selected; pass --text FILE, or run with no "
                 "arguments as a Stop hook")
    sources = args.text or ["-"]

    try:
        pats = load_patterns(args.patterns)
    except OSError as exc:
        print(f"claudese-lint: cannot read patterns: {exc}", file=sys.stderr)
        return 2
    if not pats:
        print("claudese-lint: patterns file has no usable patterns",
              file=sys.stderr)
        return 2

    annotate = args.github or os.environ.get("GITHUB_ACTIONS") == "true"
    findings = []
    for name in sources:
        try:
            text = read_source(name)
        except OSError as exc:
            print(f"claudese-lint: cannot read {name}: {exc}", file=sys.stderr)
            return 2
        shown = args.label or ("stdin" if name == "-" else name)
        for line, matched, pattern in find_hits(text, pats):
            findings.append({"file": shown, "line": line,
                             "match": matched, "pattern": pattern})

    if args.quiet:
        return 1 if findings else 0

    if args.as_json:
        print(json.dumps({"findings": findings}, indent=2))
        return 1 if findings else 0

    if not findings:
        print(f"claudese-lint: clean ({len(sources)} "
              f"{'source' if len(sources) == 1 else 'sources'})")
        return 0

    for f in findings:
        print(f"{f['file']}:{f['line']}: {f['match']}  [{f['pattern']}]")
        if annotate:
            msg = (f"Claudese: {f['match']}. Rewrite plainly per the "
                   "ban-claudese 'How to talk to me' rules.")
            print(f"::error file={f['file']},line={f['line']}::{msg}")
    print(f"\n{len(findings)} claudese "
          f"{'hit' if len(findings) == 1 else 'hits'}. Rewrite the flagged "
          "sentences plainly: name the fact, the file, the command, or the "
          "tradeoff. Backticked and fenced text is exempt, so quoting a "
          "banned phrase is fine.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    if sys.argv[1:]:
        sys.exit(cli(sys.argv[1:]))
    try:
        hook_main()
    except Exception:
        pass
    sys.exit(0)

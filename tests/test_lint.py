#!/usr/bin/env python3
"""Linter test matrix. Each case is named for the banned move (or safeguard)
it demonstrates; together they document what ban-claudese does and does not
block. Runs the repo copies of the hook and patterns via CLAUDESE_PATTERNS."""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINT = os.path.join(REPO, "hooks", "claudese-lint.py")
PATTERNS = os.path.join(REPO, "hooks", "claudese-patterns.txt")


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def tool_result():
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "x", "content": "ok"}]}}


def assistant(text, sidechain=False):
    rec = {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": text}]}}
    if sidechain:
        rec["isSidechain"] = True
    return rec


def run_case(name, records, expect_block, stop_hook_active=False):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
        tpath = f.name
    payload = json.dumps({
        "hook_event_name": "Stop",
        "transcript_path": tpath,
        "stop_hook_active": stop_hook_active,
    })
    env = {**os.environ, "CLAUDESE_PATTERNS": PATTERNS}
    proc = subprocess.run([sys.executable, LINT], input=payload, env=env,
                          capture_output=True, text=True, timeout=30)
    os.unlink(tpath)
    out = proc.stdout.strip()
    blocked = False
    if out:
        parsed = json.loads(out)
        blocked = parsed.get("decision") == "block"
    ok = (blocked == expect_block) and proc.returncode == 0
    print(f"{'PASS' if ok else 'FAIL'}  {name}  (blocked={blocked}, expected={expect_block})")
    if not ok:
        print(f"      rc={proc.returncode} stdout={out!r} stderr={proc.stderr!r}")
    return ok


CASES = [
    # The moves the linter exists to catch.
    ("borrowed_authority_jargon",
     [user("q"), assistant("This cache is load-bearing for the whole system.")], True, False),
    ("fake_profound_reversal_not_just",
     [user("q"), assistant("It's not just a cache, it's a database.")], True, False),
    ("fake_profound_reversal_isnt_a",
     [user("q"), assistant("The line isn't a line. It's a clock.")], True, False),
    ("pivot_ritual",
     [user("q"), assistant("Here's the thing: the config was wrong all along.")], True, False),
    ("gap_mysticism",
     [user("q"), assistant("That error message is the quiet part said out loud.")], True, False),
    ("reflex_validation",
     [user("q"), assistant("You're absolutely right. Deploying now.")], True, False),
    ("em_dash",
     [user("q"), assistant("Fixed the bug — retested and shipped.")], True, False),

    # What must NOT be blocked.
    ("plain_engineering_reply_passes",
     [user("q"), assistant("Fixed the null check in auth.py line 42. Tests pass.")], False, False),
    ("legit_technical_words_pass",
     [user("q"), assistant("The stack trace points at the root cause: a race in the "
                           "primitive int cache used by the API surface.")], False, False),
    ("backtick_exemption",
     [user("q"), assistant("Added `load-bearing` to the banned list in the patterns file.")], False, False),
    ("code_fence_exemption",
     [user("q"), assistant("Here is the config:\n```\nweight: load-bearing\n```\nDone.")], False, False),

    # Safeguards.
    ("stop_hook_active_no_loop",
     [user("q"), assistant("This is load-bearing.")], False, True),
    ("sidechain_agent_text_ignored",
     [user("q"), assistant("This is load-bearing.", sidechain=True),
      assistant("Renamed the module and updated both imports.")], False, False),
    ("multi_message_turn_linted_whole",
     [user("q"), assistant("Checking the file now."), tool_result(),
      assistant("The orthogonal fix is ready.")], True, False),
    ("prior_turn_not_relinted",
     [user("q1"), assistant("This is load-bearing."), user("q2"),
      assistant("Reverted the change. CI is green.")], False, False),
]




# ---------------------------------------------------------------- text mode

def run_text(name, content, args, expect_code, expect_in=(), expect_not_in=()):
    """Lint `content` through --text and check exit code plus output."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(content)
        path = f.name
    argv = [sys.executable, LINT]
    stdin = None
    if "-" in args:
        argv += ["--text", "-"]
        stdin = content
    else:
        argv += ["--text", path]
    argv += [a for a in args if a != "-"]
    if "--patterns" not in args:
        argv += ["--patterns", PATTERNS]
    proc = subprocess.run(argv, input=stdin, capture_output=True, text=True,
                          timeout=30)
    os.unlink(path)
    out = proc.stdout + proc.stderr
    ok = proc.returncode == expect_code
    for want in expect_in:
        want = want.replace("{path}", os.path.basename(path))
        if want not in out:
            ok = False
    for unwanted in expect_not_in:
        if unwanted in out:
            ok = False
    print(f"{'PASS' if ok else 'FAIL'}  text:{name}  (rc={proc.returncode}, expected={expect_code})")
    if not ok:
        print(f"      stdout={proc.stdout!r} stderr={proc.stderr!r}")
    return ok


TEXT_CASES = [
    ("clean_text_exits_zero",
     "Fixed the null check in auth.py line 42. Tests pass.\n", [], 0, (), ()),
    ("hit_reports_line_number",
     "Intro line.\nThe cache is load-bearing.\n", [], 1, (":2: load-bearing",), ()),
    ("backtick_exempt",
     "Added `load-bearing` to the list.\n", [], 0, (), ()),
    # Reflowed markdown wraps code spans across lines; those stay exempt.
    ("wrapped_backtick_span_exempt",
     "Banned: `The line isn't a line. It's a\nclock.` Do not write that.\n",
     [], 0, (), ()),
    ("stray_backtick_masks_at_most_two_lines",
     "A stray ` here.\nline two\nThis is load-bearing.\n", [], 1, (":3:",), ()),
    # The capitalized label is the whole signal, so this rule opts out of the
    # file-wide ignore-case. Key-value bullets must not be flagged as prose.
    ("colon_pivot_ignores_lowercase_labels",
     "Options.\n  - custom: combine the flags\n", [], 0, (), ()),
    ("fence_keeps_line_numbers",
     "Intro.\n```\nweight: load-bearing\nmore code\n```\nHere's the thing.\n",
     [], 1, (":6:",), ()),
    # Regression: ^-anchored patterns need re.MULTILINE. Without it this
    # rule matched only at the very start of the text, so it never fired.
    ("colon_pivot_bullet_multiline",
     "Some intro.\n- Positive: he is glue.\n", [], 1, (":2:",), ()),
    ("stdin_source",
     "This is load-bearing.\n", ["-"], 1, ("stdin:1:",), ()),
    ("label_overrides_path",
     "This is load-bearing.\n", ["--label", "PR text"], 1, ("PR text:1:",), ()),
    ("json_output",
     "This is load-bearing.\n", ["--json"], 1, ('"match": "load-bearing"',), ()),
    ("quiet_is_silent",
     "This is load-bearing.\n", ["--quiet"], 1, (), ("load-bearing",)),
    ("github_annotation",
     "This is load-bearing.\n", ["--github"], 1, ("::error file=",), ()),
    # CI must fail loudly on a broken config, unlike the fail-open hook.
    ("missing_patterns_fails_closed",
     "Plain text.\n", ["--patterns", "/nonexistent/patterns.txt"], 2,
     ("cannot read patterns",), ()),
]



def main():
    results = [run_case(*case) for case in CASES]
    results += [run_text(*case) for case in TEXT_CASES]
    print()
    if all(results):
        print(f"ALL {len(results)} CASES PASS")
        return 0
    print(f"{results.count(False)} of {len(results)} FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())

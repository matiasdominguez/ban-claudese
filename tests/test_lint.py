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


def main():
    results = [run_case(*case) for case in CASES]
    print()
    if all(results):
        print(f"ALL {len(results)} CASES PASS")
        return 0
    print(f"{results.count(False)} of {len(results)} FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())

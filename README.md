# ban-claudese

Ban the AI thought-leader voice from your Claude Code sessions. Writing rules
plus an enforcing hook: when Claude slips into Claudese, the hook blocks the
reply and makes it rewrite in plain English, in the same turn.

## Why

Recent Claude models developed a house style. Benn Stancil named it in
["The frontier fails the Turing test"](https://benn.substack.com/p/the-frontier-fails-the-turing-test):
everything is a substrate, the orthogonal axis is the load-bearing one, every
message pivots on "Here's the thing", and the answer is always hiding in what
you didn't say. It reads like authority. It compiles to nothing.

Before (Claudese):

> Here's the thing: your two problems collapse into one. The cache isn't a
> cache, it's a contract, and the invalidation bug is the quiet part said out
> loud. The fix isn't in the code you wrote but in the gaps between what the
> system does and what it promises.

After (what this tool enforces):

> Both bugs come from the same line: `store.py:80` invalidates by key prefix,
> but sessions write keys without the prefix. Fix the key format and both test
> failures go away.

The first paragraph can't be checked against anything. The second names a file,
a mechanism, and a testable claim. That's the whole idea: every sentence must
restate as a checkable fact, a concrete instruction, or a named tradeoff.

## What gets installed

Three components; the installer asks you about each:

1. **Writing rules** (recommended): a "How to talk to me" section appended to
   your global `~/.claude/CLAUDE.md` inside `<!-- ban-claudese -->` markers.
   It leads with how to draft (open with the answer, name the file and the
   number, one idea per sentence, say when you are unsure) and then bans eight
   moves (borrowed-authority jargon, fake-profound reversal, pivot ritual,
   false unification, gap mysticism, cadence theater, reflex validation, slop
   vocab) with today's tell phrases as examples. Includes a kill switch: type
   `talk straight` when Claude slips.
2. **Enforcement hook** (recommended): a Stop hook
   (`~/.claude/hooks/claudese-lint.py`) that lints every reply against
   `claudese-patterns.txt`. On a match, Claude is blocked from ending its turn
   and told to rewrite plainly. Backticked and code-fenced text is exempt, so
   quoting a banned phrase is fine.
3. **Per-prompt reminder** (optional): a UserPromptSubmit hook that injects one
   style-reminder line per prompt. Helps in long sessions where the rules have
   scrolled far out of the model's attention. Costs one context line per turn.

Rules steer; the hook enforces. Rules-only is a valid install if you don't want
hooks touching your `settings.json`.

## Install

Requires macOS or Linux, `python3`, and Claude Code.

```sh
git clone https://github.com/matiasdominguez/ban-claudese
cd ban-claudese
./install.sh
```

The installer is interactive, idempotent, and only ever touches: the markered
block in `CLAUDE.md`, its own two files in `hooks/`, and its own tagged entries
in `settings.json` (which it backs up first). Re-running upgrades in place.

Non-interactive:

```sh
./install.sh -y                      # rules + enforcement hook (defaults)
./install.sh --rules-only            # just the writing rules
./install.sh -y --all                # everything, including the reminder
./install.sh --status                # what's installed right now
```

### Let Claude install it

Paste this into Claude Code:

> Clone https://github.com/matiasdominguez/ban-claudese, read its CLAUDE.md,
> and install it for me. Ask me which components I want first.

The repo's `CLAUDE.md` tells the agent exactly how: ask you which components,
run `./install.sh -y` with the matching flags, verify with `--status`.

## How enforcement works

Claude Code runs Stop hooks when a reply finishes. This one reads the turn's
text from the transcript, strips code blocks and backticked spans, and matches
it against the patterns file. On a hit it returns
`{"decision": "block", "reason": ...}` and Claude gets feedback like:

```
Claudese linter: this reply contains banned phrasing: "absolutely right";
"not just X, it's". Rewrite the message plainly per the 'How to talk to me'
rules in your global CLAUDE.md: same content, plain sentences.
```

Claude then rewrites before the turn ends. One correction cycle per turn (the
hook checks `stop_hook_active`, so no loops). The hook fails open: any error
means your session proceeds normally.

Provenance note: this linter blocked its own author. The Claude session that
wrote it quoted two banned phrases without backticks in its summary message and
got forced to rewrite. That transcript feedback above is real output.

## Tuning

Patterns live in `~/.claude/hooks/claudese-patterns.txt`, one regex per line,
case-insensitive, `#` comments. High-precision tells ship active. Words with
legitimate technical uses (`robust`, `comprehensive`, `surface area`,
`primitive`) ship commented out so quoting a README never blocks a turn;
uncomment them to enforce. Your edits survive upgrades: the installer keeps
your copy and writes the new version to `claudese-patterns.txt.new`.

Judgment calls the regexes can't catch (rule-of-three triads, grand closers)
are covered by the rules text only.

Upgrading from 0.1.x with a tuned patterns file: take the new one. Before
0.2.0 the linter compiled patterns without `re.MULTILINE`, so any rule
anchored with `^` matched only at the very start of a reply and effectively
never fired. Rules written against that behaviour need a second look, and
case-sensitive rules now need an explicit `(?-i: ... )` wrapper because the
file-wide flag is ignore-case. The installer keeps your copy and writes
`claudese-patterns.txt.new`; diff the two.

## Beyond Claude Code

The linter has a second mode that lints plain text or markdown and reports
`file:line`. Nothing to install, no hook, no transcript.

```sh
python3 hooks/claudese-lint.py --text CHANGELOG.md docs/rfc.md
git log -1 --format=%B | python3 hooks/claudese-lint.py --text -
```

Exit 0 clean, 1 on findings, 2 on a broken config. Text mode fails closed, on
the grounds that a CI check which silently passes is worse than none. The hook
mode still fails open so a bad config can never block a session. Flags:
`--patterns PATH`, `--label NAME` for the reported source name, `--json`,
`--github` for Actions annotations (auto-detected via `$GITHUB_ACTIONS`), and
`--quiet` for exit status only.

### PR text in CI

`examples/github/claudese-pr.yml` lints PR titles and bodies on every pull
request. Copy it to `.github/workflows/` and pin the tag you want. It reads the
PR text through environment variables rather than inlining it into `run:`,
because PR text is untrusted input. Add `continue-on-error: true` to start
advisory. A commented-out second job lints markdown changed by the PR.

This repo runs the same job on its own PRs.

## Rolling it out to a team

Nobody needs to install anything for the rules to apply.

1. Commit `rules/how-to-talk-to-me.md` into your repo's `CLAUDE.md` (and
   `AGENTS.md` for Codex, `.cursorrules` for Cursor). Everyone working in that
   repo gets the register, including for PR bodies and files the agent writes.
   Edit the kill-switch phrase and the first line to suit the team.
2. Add the CI check above so PR text is enforced for everyone, whatever tool
   wrote it.
3. Anyone who wants live enforcement in their own sessions runs
   `./install.sh -y` on their machine. That part stays individual, because it
   edits a personal `~/.claude`.

The rules are language-independent by design: the eight banned moves apply to
whatever language you write in, and the ninth rule says a new word doing the
same job is the same violation. The regexes only catch the English tells, so
enforcement is English-only until someone adds patterns for another language.
One regex per line in `hooks/claudese-patterns.txt` is the whole extension
mechanism.

## Uninstall

```sh
./uninstall.sh            # removes rules block, hook entries, hook files
./uninstall.sh --purge    # also removes a patterns file you modified
```

Removes only its own markered block and its own tagged `settings.json` entries.
Everything else in your config is left alone.

## Caveats

- Hooks load at session start: restart Claude Code (or run `/hooks`) after
  installing.
- The linter runs when a reply finishes, so a slip can flash on screen before
  the forced correction. Nothing can unprint streamed text.
- Tells mutate. The rules ban the moves, not just today's phrases; when you
  spot a new tell, add a regex to the patterns file.
- claude.ai web/desktop/mobile can't run hooks. For those, copy the rules text
  from `rules/how-to-talk-to-me.md` into Settings → Profile → "Instructions
  for Claude".

## Tests

```sh
make test
```

`tests/test_lint.py` is a 29-case matrix named by move: each banned move blocks,
plain engineering prose passes, backtick/fence exemptions hold, sidechain agent
text is ignored, the no-loop guard works, and text mode reports the right line
numbers and exit codes. `tests/test_install.sh` installs
into a sandboxed directory and verifies idempotence, preservation of your
pre-existing hooks, pattern-tuning survival across upgrades, a real lint of a
Claudese transcript through the installed hook, and clean uninstall. CI runs
both on Ubuntu and macOS.

## License

MIT

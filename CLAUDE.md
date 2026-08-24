# ban-claudese: agent instructions

This repo installs writing rules and an enforcement hook into a user's Claude
Code config. If the user asked you to install it, follow the install flow. If
you're developing it, follow the development flow.

## Installing for a user

1. Ask which components they want (use AskUserQuestion if available). The
   three components, with recommended defaults:
   - writing rules -> global CLAUDE.md (recommend yes)
   - enforcement hook, a Stop-hook linter that forces plain rewrites
     (recommend yes)
   - per-prompt style reminder, one context line per prompt (default no)
2. Run the installer non-interactively with exactly what they chose:
   - rules + enforcement: `./install.sh -y` (these are the defaults)
   - rules only: `./install.sh --rules-only`
   - everything: `./install.sh -y --all`
   - custom: combine `--rules`, `--lint-hook`, `--reminder-hook` with `-y`
3. Verify: `./install.sh --status` should report each chosen component as
   installed.
4. Tell the user: hooks load next session, so restart Claude Code or run
   `/hooks`; the kill switch phrase is `talk straight`; enforcement patterns
   are tunable in `<claude-dir>/hooks/claudese-patterns.txt`.

Notes:
- The installer is idempotent and self-contained: markered block in CLAUDE.md,
  tagged entries in settings.json (backed up first), two files in hooks/.
  Don't edit those files by hand; re-run the installer instead.
- `--claude-dir DIR` overrides the target (default `$CLAUDE_CONFIG_DIR`, else
  `~/.claude`). Only needed for non-standard setups.
- Uninstall with `./uninstall.sh` (add `--purge` to also drop a user-modified
  patterns file).

## Developing

- `make test` must pass before any commit. It runs the linter matrix
  (`tests/test_lint.py`) and a sandboxed end-to-end install test
  (`tests/test_install.sh`). Both need only bash + python3.
- Keep `rules/how-to-talk-to-me.md` and `hooks/claudese-patterns.txt` in sync:
  a banned move added to the rules should get a regex if one can be written
  with high precision; broad or ambiguous words go in commented-out form.
- Hook mode in `hooks/claudese-lint.py` must always fail open. Never let a
  parse error or missing file block a user's session. Text mode (`--text`)
  fails closed on purpose, because it runs in CI where a silent pass is worse
  than no check; keep that asymmetry.
- The rules lead with how to draft, not how to fix. Enforcement is a backstop.
  Keep new guidance in that order: what to write, then what never to produce.
- On release, bump the pinned tag in `examples/github/claudese-pr.yml` to the
  tag you are cutting, or teams copying it will clone an older linter.
- `rules/enforcement-note.md` is appended to the installed block only when the
  lint hook is selected; keep `{{CLAUDE_DIR}}` placeholders intact.
- Bump `VERSION` on any change to what gets installed; the version is stamped
  into the CLAUDE.md marker so `--status` can report it.

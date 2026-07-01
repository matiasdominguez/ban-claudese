Enforcement (Claude Code): a Stop hook runs {{CLAUDE_DIR}}/hooks/claudese-lint.py
on every reply; a match forces a rewrite in the same turn. The enforceable
patterns live in {{CLAUDE_DIR}}/hooks/claudese-patterns.txt; edit that file to
tune. Judgment-call bans (triads, closers) are steering-only.

Enforcement (Claude Code): a Stop hook runs {{CLAUDE_DIR}}/hooks/claudese-lint.py
on every reply. It is a backstop, not the rule. A block means you already wrote
the bad sentence and are now spending a turn undoing it, so draft to the rules
above and the hook stays quiet. Enforceable patterns live in
{{CLAUDE_DIR}}/hooks/claudese-patterns.txt; edit that file to tune. Judgment-call
bans (triads, closers, compressed shorthand) are steering-only, which means
nothing catches them but me.

---
name: dumb
description: Show a one-screen gauge of how full the current Claude Code context window is, where the tokens went, and whether the session has entered the quality-degradation zone (past 40%). Use when the user types /dumb, asks how full the context is, asks if the session is degrading, asks where context went, or asks whether to run /compact.
tools: Bash
---

# /dumb — context-pressure gauge

Run the bundled renderer and emit its output verbatim. Do not summarize, paraphrase, comment on, or add anything before or after.

```bash
!`python3 ~/.claude/skills/dumb/scripts/render.py "${CLAUDE_SESSION_ID}" $1`
```

## Argument

- (none) — default 4-row attribution + recommendation
- `minimal` — just the gauge bar and the recommendation
- `honest` — drop heuristic estimates, show only counts that come straight from the API

## Rules

- The script's stdout IS the response. Print it as-is.
- Do not add a preamble like "Here is your context gauge:". Do not add a postamble like "Let me know if you'd like to compact."
- If the script prints a warning (e.g., session JSONL not found), print that warning and stop.
- Never speculate about token counts. If the script didn't compute it, don't invent it.

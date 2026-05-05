# dumb-zone — `/dumb`

> Your Claude Code session gets dumber after ~40% context.
> `/dumb` tells you when, why, and what to do about it. One skill, zero install ceremony.

## What it looks like

**Green zone — early in a session, you're fine.**

```
🟩 GREEN ZONE — 10% context used (20,001 / 200,000) · claude-sonnet-4-6
[████                                    ]  (as of last turn)

Where your context went:
  System + tools + skills (initial)         12,000 tok    60%
  Your messages                                 15 tok     0%
  My text responses                             12 tok     0%
  Tool I/O (calls + results)                 7,974 tok    40%

→ You're fine. Keep going.
```

**Dumb zone — past the threshold, quality drops, cost stays full.**

```
🟧 DUMB ZONE — 45% context used (90,003 / 200,000) · claude-sonnet-4-6
[██████████████████                      ]  (as of last turn)
Quality typically drops past 40% on Sonnet-class models.
10,003 tokens past the line. The drift has started.

Where your context went:
  System + tools + skills (initial)         18,000 tok    20%
  Your messages                                 38 tok     0%
  My text responses                             33 tok     0%
  Tool I/O (calls + results)                71,932 tok    80%

Tools called (2 total): Read ×1, mcp__github__search_code ×1
⚠ MCP audit: only github (1 tool) earned its keep. The rest are tax.

→ You're past the line. Quality drift starts here. /compact at a natural pause. Each turn now costs ~$0.07.
```

**Red zone — auto-compact is imminent, every turn is expensive and degraded.**

```
🟥 RED ZONE — 78% context used (156,003 / 200,000) · claude-opus-4-7
[███████████████████████████████▏        ]  (as of last turn)
Quality typically drops past 40% on Sonnet-class models.
76,003 tokens past the line. The drift has started.

Where your context went:
  System + tools + skills (initial)         35,000 tok    22%
  Your messages                                 35 tok     0%
  My text responses                             55 tok     0%
  Tool I/O (calls + results)               120,913 tok    78%

Tools called (5 total): Read ×2, mcp__sentry__list_issues ×1, mcp__sentry__get_issue ×1, Bash ×1
⚠ MCP audit: only sentry (2 tools) earned its keep. The rest are tax.

→ /compact or /clear. You're paying full price for a tired Claude. Each turn costs ~$0.15.
```

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dumb-zone/dumb-zone/main/install.sh | bash
```

Then in any Claude Code session, type `/dumb`.

Stdlib Python 3.8+. No npm install. No API keys. No telemetry.

## Why this exists

Claude Code doesn't tell you when your session has crossed into the band where output quality starts dropping. By the time you notice the answers feel off, you've already spent several turns at degraded quality at full price.

`/dumb` is a single-screen gauge — context %, where the tokens went, what to do about it — that you can summon any time without breaking flow. It reads your session's transcript locally and computes everything from `usage` fields the API already returns. No estimates of estimates.

## Why 40%?

Two effects compound past ~40% context on Sonnet-class models:

1. **Quality degradation.** Long-context recall and reasoning fall off well before the window is "full." This is broadly reported across r/ClaudeAI and corroborated by Anthropic engineering write-ups on long-context behavior. The 40% number is a working threshold, not a hard cliff — you'll see it as answers getting sloppier, instructions getting dropped, tool calls getting redundant.
2. **Cost-per-turn climbs.** Every turn re-reads the entire cached context. At 80% on Opus 4.7 that's ~$0.15/turn for the cache alone, regardless of how much new work actually got done that turn.

On 1M-context models the threshold starts earlier (~30%) — `/dumb` flags this separately as `CONTEXT ROT`.

The "Dumb Zone" framing comes from **Dex Horthy** (HumanLayer)'s "No Vibes Allowed" talk. This skill ports the framing to Claude Code as a single command.

## What it sees

`/dumb` reads the current session's JSONL transcript at `~/.claude/projects/<cwd>/<sessionId>.jsonl` and computes:

- **Window fill** from the latest assistant turn's `usage` (input + cache_creation + cache_read).
- **Attribution** — initial cached prefix, your messages, my text responses, and tool I/O as the residual (so the four rows always sum to the total).
- **Tools called** — counts by name; flags MCP servers actually used (vs. just loaded into the system prompt).
- **Cost-per-turn estimate** — current context × per-model cache-read rate + a fixed 3000-output-tokens-per-turn assumption.

It does **not** read file contents, send anything off-machine, or talk to any API. Stdlib Python only.

## Modes

- `/dumb` — default, full attribution
- `/dumb minimal` — gauge bar and recommendation only
- `/dumb honest` — drop heuristic estimates; show only counts that come straight from the API

## Customization

v0.1 ships with opinionated thresholds (40% DUMB, 75% RED, 30% CONTEXT ROT on 1M models) and per-model pricing accurate as of release. Thresholds are not user-configurable in v0.1 — that's the product. Cost figures will drift when Anthropic changes rates: re-install for fresh numbers, or wait for v0.2.

## Roadmap

- **v0.2** — `~/.claude/dumb/pricing.json` override for custom enterprise contracts; cost formula derives output-tokens-per-turn from session history instead of a fixed 3000.
- **v0.3** — optional sparkline showing context growth across the last N turns.
- Anything else: open an issue.

## Credits

The "Dumb Zone" framing for the post-40% context-degradation band is due to **Dex Horthy / HumanLayer** ("No Vibes Allowed" talk). This skill ports the framing to Claude Code as an on-demand single-screen gauge. Related prior art for a different agent: [arpagon/pi-context-zone](https://github.com/arpagon/pi-context-zone).

## License

MIT.

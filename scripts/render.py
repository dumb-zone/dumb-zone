#!/usr/bin/env python3
"""dumb-zone renderer — single-screen context-pressure gauge for Claude Code.

Reads the current session's JSONL transcript, computes how full the context
window is, attributes tokens by source, and prints a single recommendation.
Stdlib only.

Usage:  render.py <session_id> [default|minimal|honest] [--cwd <path>]
        cwd defaults to the process's current working directory.
"""
import json
import os
import sys
from pathlib import Path

# --- opinionated thresholds (the product) -----------------------------------
DUMB = 0.40   # past this, quality typically degrades on Sonnet-class models
RED  = 0.75   # past this, auto-compact is imminent
ROT  = 0.30   # context-rot threshold on 1M-context models

# --- pricing (USD per million tokens, source: anthropic.com 2026-05-05) -----
PRICING = {
    "claude-opus-4-7":   {"cache_read": 0.50, "out": 25.00},
    "claude-sonnet-4-6": {"cache_read": 0.30, "out": 15.00},
    "claude-haiku-4-5":  {"cache_read": 0.10, "out":  5.00},
}
DEFAULT_PRICE = PRICING["claude-sonnet-4-6"]

WINDOWS = {
    "claude-opus-4-7":   200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5":  200_000,
}
WINDOW_1M = 1_000_000


# --- io ---------------------------------------------------------------------
def find_jsonl(session_id, cwd):
    return Path.home() / ".claude" / "projects" / cwd.replace("/", "-") / f"{session_id}.jsonl"


def load_events(path):
    out = []
    with open(path) as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


# --- math -------------------------------------------------------------------
def model_window(model):
    is_1m = "[1m]" in model
    base = model.replace("[1m]", "")
    return (WINDOW_1M if is_1m else WINDOWS.get(base, 200_000)), is_1m, base


def usage_total(u):
    return ((u.get("input_tokens") or 0)
          + (u.get("cache_creation_input_tokens") or 0)
          + (u.get("cache_read_input_tokens") or 0))


def latest_assistant(events):
    last_u, last_m = None, None
    for e in events:
        m = e.get("message") or {}
        if m.get("role") == "assistant" and isinstance(m.get("usage"), dict):
            last_u, last_m = m["usage"], m.get("model") or last_m
    return last_u, last_m


def assistant_turns(events):
    """All assistant turns with usage data, in order. Used by monitor mode for dedup."""
    out = []
    for e in events:
        m = e.get("message") or {}
        if m.get("role") == "assistant" and isinstance(m.get("usage"), dict):
            out.append((m["usage"], m.get("model")))
    return out


def first_cached_prefix(events):
    for e in events:
        m = e.get("message") or {}
        if m.get("role") == "assistant":
            cc = (m.get("usage") or {}).get("cache_creation_input_tokens") or 0
            if cc > 0:
                return cc
    return 0


CHARS_PER_TOK = 3.2  # rough English+JSON mix; underestimates by design so Tool I/O catches residual


def attribute(events, total):
    """Where tokens went. Cached prefix + user msgs + assistant text are estimated;
    Tool I/O is the residual so the rows always sum to total."""
    cached = first_cached_prefix(events)
    user_chars = asst_text_chars = 0
    tool_calls = 0
    tools_used = {}            # name -> count
    mcp_servers = {}           # server -> set of distinct tool names called

    for e in events:
        m = e.get("message") or {}
        role = m.get("role")
        c = m.get("content")
        if role == "user":
            if isinstance(c, str):
                user_chars += len(c)
        elif role == "assistant" and isinstance(c, list):
            for b in c:
                if not isinstance(b, dict):
                    continue
                bt = b.get("type")
                if bt == "text":
                    asst_text_chars += len(b.get("text", ""))
                elif bt == "tool_use":
                    name = b.get("name", "")
                    tool_calls += 1
                    tools_used[name] = tools_used.get(name, 0) + 1
                    if name.startswith("mcp__"):
                        parts = name.split("__")
                        if len(parts) >= 2:
                            mcp_servers.setdefault(parts[1], set()).add(name)

    user_tok = int(user_chars / CHARS_PER_TOK)
    asst_tok = int(asst_text_chars / CHARS_PER_TOK)
    tool_io_tok = max(0, total - cached - user_tok - asst_tok)

    rows = [
        ("System + tools + skills (initial)", cached),
        ("Your messages",                     user_tok),
        ("My text responses",                 asst_tok),
        ("Tool I/O (calls + results)",        tool_io_tok),
    ]
    return rows, mcp_servers, tools_used, tool_calls


# --- rendering --------------------------------------------------------------
def render_bar(pct, width=40):
    blocks = " ▏▎▍▌▋▊▉█"
    pct = max(0.0, min(1.0, pct))
    filled = pct * width
    full = int(filled)
    bar = "█" * full
    if full < width:
        bar += blocks[int((filled - full) * 8)] + " " * (width - full - 1)
    return bar


def zone_label(pct, is_1m):
    if pct >= RED:
        return "🟥", "RED ZONE"
    if pct >= DUMB:
        return "🟧", "DUMB ZONE"
    if is_1m and pct >= ROT:
        return "🟧", "CONTEXT ROT"
    return "🟩", "GREEN ZONE"


def turn_cost(model_base, total):
    p = PRICING.get(model_base, DEFAULT_PRICE)
    return (total * p["cache_read"] + 3000 * p["out"]) / 1_000_000


def recommendation(pct, model_base, total):
    if pct < DUMB:
        return "You're fine. Keep going."
    cost = turn_cost(model_base, total)
    if pct < 0.60:
        return f"You're past the line. Quality drift starts here. /compact at a natural pause. Each turn now costs ~${cost:.2f}."
    if pct < RED:
        return f"Getting expensive AND dumb. /compact in 1–2 turns. Each turn costs ~${cost:.2f}."
    return f"/compact or /clear. You're paying full price for a tired Claude. Each turn costs ~${cost:.2f}."


def fmt_tools_summary(tools_used):
    if not tools_used:
        return ""
    items = sorted(tools_used.items(), key=lambda x: -x[1])
    parts = [f"{n} ×{c}" for n, c in items[:6]]
    if len(items) > 6:
        parts.append(f"+{len(items)-6} more")
    return ", ".join(parts)


# --- main -------------------------------------------------------------------
EMPTY_MSG = "🟩 EMPTY — pristine context. /dumb is for mid-session reality checks."


def turn_zone(usage, model):
    """Returns (emoji, label, pct, model_base) for a given assistant turn."""
    total = usage_total(usage)
    window, is_1m, model_base = model_window(model or "")
    pct = total / window if window else 0.0
    em, label = zone_label(pct, is_1m)
    return em, label, pct, model_base, total


def monitor_message(events):
    """Stateless dedup: fire only when the latest turn's zone differs from the
    previous turn's zone. Silent in GREEN. Designed for use as a Stop hook."""
    turns = assistant_turns(events)
    if not turns:
        return None
    em, label, pct, model_base, total = turn_zone(*turns[-1])
    if label == "GREEN ZONE":
        return None
    if len(turns) >= 2:
        _, prev_label, _, _, _ = turn_zone(*turns[-2])
        if prev_label == label:
            return None  # same zone as last turn, don't re-nudge
    cost = turn_cost(model_base, total)
    pct_str = f"{pct*100:.0f}%"
    if label == "RED ZONE":
        return f"{em} /dumb: {pct_str} context — RED ZONE. /compact now — each turn costs ~${cost:.2f}."
    if label == "DUMB ZONE":
        return f"{em} /dumb: {pct_str} context — past the line. /dumb for breakdown, /compact for a fix."
    # CONTEXT ROT (1M models past 30%)
    return f"{em} /dumb: {pct_str} context — context rot territory on a 1M model. /dumb for details."


def render(events, mode="default"):
    if mode == "monitor":
        return monitor_message(events) or ""

    usage, model = latest_assistant(events)
    if not usage or not model:
        return EMPTY_MSG

    total = usage_total(usage)
    window, is_1m, model_base = model_window(model)
    pct = total / window if window else 0.0
    em, label = zone_label(pct, is_1m)

    out = [
        f"{em} {label} — {pct*100:.0f}% context used ({total:,} / {window:,}) · {model}",
        f"[{render_bar(pct)}]  (as of last turn)",
    ]
    if is_1m and ROT <= pct < DUMB:
        out.append(f"Long-context degradation (\"context rot\") begins past {int(ROT*100)}% on 1M-window models.")
    elif pct >= DUMB:
        out.append(f"Quality typically drops past {int(DUMB*100)}% on Sonnet-class models.")
        delta = total - int(DUMB * window)
        if delta > 0:
            out.append(f"{delta:,} tokens past the line. The drift has started.")

    if mode == "honest":
        cached = first_cached_prefix(events)
        accumulated = max(0, total - cached)
        out.append("")
        out.append("Where your context went (exact API counts only):")
        for lbl, tok in [("System + tools + skills (initial cache)", cached),
                          ("Accumulated this session",                 accumulated)]:
            frac = tok / total if total else 0
            out.append(f"  {lbl:<42} {tok:>9,} tok  {frac*100:>4.0f}%")
    elif mode != "minimal":
        rows, mcp_servers, tools_used, tool_calls = attribute(events, total)
        out.append("")
        out.append("Where your context went:")
        for lbl, tok in rows:
            frac = tok / total if total else 0
            out.append(f"  {lbl:<38} {tok:>9,} tok  {frac*100:>4.0f}%")
        if tool_calls:
            out.append("")
            out.append(f"Tools called ({tool_calls} total): {fmt_tools_summary(tools_used)}")
        if mcp_servers:
            srv_summary = ", ".join(f"{s} ({len(t)} tool{'s' if len(t)>1 else ''})" for s, t in sorted(mcp_servers.items()))
            out.append(f"⚠ MCP audit: only {srv_summary} earned its keep. The rest are tax.")

    out.append("")
    out.append(f"→ {recommendation(pct, model_base, total)}")
    return "\n".join(out)


def main():
    args = sys.argv[1:]
    cwd = os.getcwd()
    if "--cwd" in args:
        i = args.index("--cwd")
        cwd = args[i + 1]
        del args[i:i + 2]
    if not args:
        print("usage: render.py <session_id> [default|minimal|honest|monitor] [--cwd <path>]", file=sys.stderr)
        sys.exit(2)
    session_id = args[0]
    mode = args[1] if len(args) > 1 else "default"
    jsonl = find_jsonl(session_id, cwd)
    if not jsonl.exists():
        if mode != "monitor":  # monitor mode is silent when there's nothing to say
            print(EMPTY_MSG)
        return
    out = render(load_events(jsonl), mode)
    if out:
        print(out)


if __name__ == "__main__":
    main()

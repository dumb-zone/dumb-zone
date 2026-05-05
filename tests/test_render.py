#!/usr/bin/env python3
"""Tests for render.py — runs against synthetic JSONL fixtures.

Run:  python3 -m unittest tests.test_render  (from repo root)
   or python3 tests/test_render.py
"""
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import render  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures"


def load(name):
    return render.load_events(FIXTURES / name)


class TestZones(unittest.TestCase):
    def test_green_under_40_pct(self):
        out = render.render(load("green.jsonl"))
        self.assertIn("🟩", out)
        self.assertIn("GREEN ZONE", out)
        self.assertIn("You're fine", out)
        self.assertNotIn("DUMB", out)

    def test_dumb_between_40_and_75(self):
        out = render.render(load("dumb.jsonl"))
        self.assertIn("🟧", out)
        self.assertIn("DUMB ZONE", out)
        # 90,001 / 200,000 = 45% → "past the line" copy band
        self.assertIn("/compact", out)
        self.assertIn("past the line", out)

    def test_red_over_75(self):
        out = render.render(load("red.jsonl"))
        self.assertIn("🟥", out)
        self.assertIn("RED ZONE", out)
        self.assertIn("tired Claude", out)


class TestModes(unittest.TestCase):
    def test_minimal_drops_attribution(self):
        out = render.render(load("dumb.jsonl"), mode="minimal")
        self.assertNotIn("Where your context went", out)
        self.assertIn("DUMB ZONE", out)
        self.assertIn("→", out)

    def test_honest_two_rows_only(self):
        out = render.render(load("dumb.jsonl"), mode="honest")
        self.assertIn("exact API counts only", out)
        self.assertIn("Accumulated this session", out)
        self.assertNotIn("Tool I/O", out)
        self.assertNotIn("Your messages", out)

    def test_default_full_breakdown(self):
        out = render.render(load("dumb.jsonl"))
        self.assertIn("Where your context went", out)
        self.assertIn("System + tools + skills", out)
        self.assertIn("Tool I/O", out)
        self.assertIn("Tools called", out)


class TestMath(unittest.TestCase):
    def test_attribution_rows_sum_to_total(self):
        events = load("dumb.jsonl")
        usage, _ = render.latest_assistant(events)
        total = render.usage_total(usage)
        rows, _, _, _ = render.attribute(events, total)
        self.assertEqual(sum(t for _, t in rows), total)

    def test_window_detection_1m(self):
        w, is_1m, base = render.model_window("claude-opus-4-7[1m]")
        self.assertEqual(w, 1_000_000)
        self.assertTrue(is_1m)
        self.assertEqual(base, "claude-opus-4-7")

    def test_window_detection_standard(self):
        w, is_1m, base = render.model_window("claude-sonnet-4-6")
        self.assertEqual(w, 200_000)
        self.assertFalse(is_1m)

    def test_bar_renders_to_correct_width(self):
        bar = render.render_bar(0.5, width=20)
        self.assertEqual(len(bar), 20)
        bar = render.render_bar(0.0, width=10)
        self.assertEqual(len(bar), 10)
        bar = render.render_bar(1.0, width=10)
        self.assertEqual(len(bar), 10)

    def test_cost_increases_with_context(self):
        cheap = render.turn_cost("claude-sonnet-4-6", 10_000)
        pricey = render.turn_cost("claude-sonnet-4-6", 150_000)
        self.assertLess(cheap, pricey)

    def test_unknown_model_falls_back(self):
        # should not raise; use default sonnet pricing
        c = render.turn_cost("claude-from-the-future-9-9", 50_000)
        self.assertGreater(c, 0)


class TestEdgeCases(unittest.TestCase):
    def test_no_assistant_turns(self):
        # only user message, no assistant — should warn, not crash
        out = render.render([{"type": "user", "message": {"role": "user", "content": "hi"}}])
        self.assertIn("empty", out.lower())

    def test_empty_events(self):
        out = render.render([])
        self.assertIn("empty", out.lower())


def _asst_turn(input_t, cache_create, cache_read, model="claude-sonnet-4-6"):
    return {"type": "assistant", "message": {"role": "assistant", "model": model,
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": input_t, "cache_creation_input_tokens": cache_create,
                      "cache_read_input_tokens": cache_read, "output_tokens": 100}}}


class TestMonitor(unittest.TestCase):
    def test_silent_when_empty(self):
        self.assertEqual("", render.render([], mode="monitor"))

    def test_silent_when_green(self):
        # 20k / 200k = 10%, GREEN
        out = render.render([_asst_turn(1, 12000, 8000)], mode="monitor")
        self.assertEqual("", out)

    def test_fires_on_first_dumb_turn(self):
        # 90k / 200k = 45%, DUMB
        out = render.render([_asst_turn(1, 18000, 72000)], mode="monitor")
        self.assertIn("past the line", out)
        self.assertIn("/dumb:", out)

    def test_dedup_when_same_zone_two_turns_in_a_row(self):
        # both turns DUMB → second should be silent
        events = [_asst_turn(1, 18000, 72000), _asst_turn(1, 18000, 72000)]
        self.assertEqual("", render.render(events, mode="monitor"))

    def test_fires_on_escalation_dumb_to_red(self):
        # turn 1 DUMB (45%), turn 2 RED (78% on opus 1m? no, on standard)
        events = [_asst_turn(1, 18000, 72000),  # 45% DUMB
                  _asst_turn(1, 35000, 121000, model="claude-opus-4-7")]  # 78% RED
        out = render.render(events, mode="monitor")
        self.assertIn("RED ZONE", out)
        self.assertIn("/compact now", out)

    def test_silent_when_escalating_to_green(self):
        # impossible in practice (compact drops context), but check sanity:
        # turn 1 DUMB, turn 2 GREEN → silent (we don't celebrate)
        events = [_asst_turn(1, 18000, 72000),  # 45% DUMB
                  _asst_turn(1, 12000, 8000)]   # 10% GREEN
        self.assertEqual("", render.render(events, mode="monitor"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

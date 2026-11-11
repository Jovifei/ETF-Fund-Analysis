"""Dependency-free tests. All fixtures are synthetic, never market evidence."""

import copy
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from app.research.structure_weight_replay import (
    BASELINE_SHA,
    ReplayError,
    build_report,
    paired_block_intervals,
    write_report,
)


def fixture(days=40, codes=("510300", "510500")):
    calendar = [(date(2026, 11, 11) + timedelta(days=i)).isoformat() for i in range(days)]
    bars, signals = [], []
    for i, day in enumerate(calendar):
        for code in codes:
            bars.append(
                {
                    "date": day,
                    "code": code,
                    "open": 10.0,
                    "close": 10.0,
                    "volume": 1000,
                    "open_volume": 100,
                    "open_available_at": day + "T09:30:00+08:00",
                    "momentum_close": 10 + i / 10,
                    "available_at": day + "T15:10:00+08:00",
                }
            )
            if 5 <= i < min(16, days):
                signals.append(
                    {
                        "date": day,
                        "code": code,
                        "base_grade": "可试探",
                        "decision_at": day + "T15:30:00+08:00",
                        "available_at": day + "T15:20:00+08:00",
                        "inputs_as_of": day + "T15:00:00+08:00",
                        "structure_v1": {
                            "wyckoff_score": 0.7,
                            "dow_score": 0.7,
                            "wyckoff_confidence": 1.0,
                            "dow_confidence": 1.0,
                            "atr_risk_bucket": "low",
                        },
                    }
                )
    return {
        "schema_version": "structure-weight-input-v1",
        "universe": list(codes),
        "calendar": calendar,
        "signal_start": calendar[5],
        "signal_end": calendar[min(15, days - 1)],
        "frozen_at": "2026-11-10T23:00:00+08:00",
        "seen_through": "2026-11-10",
        "as_of": calendar[-1] + "T16:00:00+08:00",
        "source_manifest": {
            "code_sha": BASELINE_SHA,
            "config_sha256": "a" * 64,
            "signal_definition": "base_grade_before_structure",
            "price_adjustment": "raw",
            "momentum_adjustment": "consistent_total_return",
            "raw_price_evidence_ref": "synthetic",
            "signal_pit_evidence_ref": "synthetic",
            "source_kind": "synthetic",
            "execution_snapshot_evidence_ref": "synthetic",
        },
        "corporate_actions": {
            "coverage_start": calendar[0],
            "coverage_end": calendar[-1],
            "evidence_ref": "synthetic-no-actions",
            "events": [],
        },
        "signals": signals,
        "bars": bars,
    }


class ReplayTests(unittest.TestCase):
    def report(self, data=None):
        return build_report(data or fixture(), expected_config_hash="a" * 64, bootstrap_samples=100)

    def test_exact_formula_and_common_pairing(self):
        report = self.report()
        row = report["opportunities"][0]
        self.assertEqual(row["grades"], {"R0": "可试探", "R1": "可试探", "R2": "可入场"})
        self.assertEqual(set(row["targets"]), {"R0", "R1", "R2", "always_long", "momentum_5d"})
        self.assertEqual(report["manifest"]["candidates"], {"R0": 0.0, "R1": 0.3125, "R2": 0.4167})
        self.assertFalse(report["qualification"]["actionable"])
        self.assertFalse(report["qualification"]["final_oos_validated"])

    def test_missing_structure_falls_back_no_sample_drop(self):
        data = fixture()
        data["signals"][0]["structure_v1"] = None
        row = self.report(data)["opportunities"][0]
        self.assertTrue(row["included"])
        self.assertTrue(row["structure_missing"])
        self.assertEqual(len(set(row["grades"].values())), 1)

    def test_base_anomaly_cannot_add_risk_even_baselines(self):
        data = fixture()
        data["signals"][0]["base_grade"] = "数据异常"
        row = self.report(data)["opportunities"][0]
        self.assertTrue(row["included"])
        self.assertTrue(all(v == 0 for v in row["targets"].values()))

    def test_missing_momentum_excluded_jointly(self):
        data = fixture()
        data["bars"][0]["momentum_close"] = None
        row = self.report(data)["opportunities"][0]
        self.assertFalse(row["included"])
        self.assertIn("momentum_history_missing", row["exclusion_reasons"])
        self.assertEqual(row["targets"], {})

    def test_immature_not_zero_filled(self):
        data = fixture(25)
        report = self.report(data)
        rows = [r for r in report["opportunities"] if r["horizon"] == 20]
        self.assertTrue(all(not r["included"] for r in rows))
        self.assertTrue(all("forward_unmatured" in r["exclusion_reasons"] for r in rows))
        self.assertIsNone(report["experiments"]["20"]["base"]["primary"])

    def test_duplicate_keys_rejected(self):
        data = fixture()
        data["signals"].append(copy.deepcopy(data["signals"][0]))
        with self.assertRaisesRegex(ReplayError, "duplicate_signal"):
            self.report(data)

    def test_future_signal_excluded(self):
        data = fixture()
        data["signals"][0]["available_at"] = data["calendar"][6] + "T09:00:00+08:00"
        row = self.report(data)["opportunities"][0]
        self.assertIn("signal_not_point_in_time", row["exclusion_reasons"])

    def test_future_momentum_excluded(self):
        data = fixture()
        data["bars"][10]["available_at"] = data["calendar"][6] + "T09:00:00+08:00"
        self.assertIn(
            "momentum_not_point_in_time", self.report(data)["opportunities"][0]["exclusion_reasons"]
        )

    def test_wrong_source_identity_rejected(self):
        data = fixture()
        data["source_manifest"]["code_sha"] = "b" * 40
        with self.assertRaisesRegex(ReplayError, "source_code_identity_mismatch"):
            self.report(data)

    def test_adjusted_prices_and_missing_actions_signal_only(self):
        for mutate in (
            lambda d: d["source_manifest"].update(price_adjustment="qfq"),
            lambda d: d.pop("corporate_actions"),
        ):
            data = fixture()
            mutate(data)
            report = self.report(data)
            self.assertEqual(report["status"], "signal_only")
            self.assertEqual(report["experiments"], {})

    def test_seen_dates_cannot_be_final_oos(self):
        data = fixture()
        data["seen_through"] = data["calendar"][10]
        report = self.report(data)
        first = report["opportunities"][0]
        self.assertEqual(first["sample_class"], "development_seen")
        self.assertFalse(report["qualification"]["final_oos_validated"])

    def test_seen_floor_cannot_move_back(self):
        data = fixture()
        data["seen_through"] = "2026-11-09"
        with self.assertRaisesRegex(ReplayError, "seen_through_before_known_cutoff"):
            self.report(data)

    def test_entry_next_open_and_terminal_costs(self):
        report = self.report()
        run = report["experiments"]["5"]["base"]["primary"]["strategies"]["R2"]
        fills = [x for x in run["trades"] if x["status"] == "filled"]
        self.assertEqual(fills[0]["date"], fixture()["calendar"][6])
        self.assertTrue(any(x["terminal"] and x["side"] == "sell" for x in fills))
        self.assertGreater(run["metrics"]["fees"], 0)
        self.assertGreater(run["metrics"]["slippage_cost"], 0)
        self.assertLess(run["metrics"]["net_return"], 0)
        self.assertGreaterEqual(min(x["cash"] for x in run["daily_nav"]), 0)
        self.assertEqual(run["metrics"]["remaining_shares"], 0)

    def test_zero_volume_blocks_buy_and_does_not_fabricate_fill(self):
        data = fixture()
        entry = data["calendar"][6]
        for bar in data["bars"]:
            if bar["date"] == entry:
                bar["volume"] = 0
                bar["open_volume"] = 0
        run = self.report(data)["experiments"]["5"]["base"]["primary"]["strategies"]["R2"]
        trades = [x for x in run["trades"] if x["date"] == entry]
        self.assertTrue(trades)
        self.assertTrue(all(x["status"] == "blocked" for x in trades))
        self.assertEqual(run["daily_nav"][0]["exposure"], 0)

    def test_failed_terminal_sale_retains_position(self):
        data = fixture()
        terminal = data["calendar"][21]
        for bar in data["bars"]:
            if bar["date"] == terminal:
                bar["volume"] = 0
                bar["open_volume"] = 0
        run = self.report(data)["experiments"]["5"]["base"]["primary"]["strategies"]["R2"]
        self.assertGreater(run["metrics"]["remaining_shares"], 0)
        self.assertFalse(run["metrics"]["fully_liquidated"])

    def test_cost_stress_reduces_flat_market_net(self):
        exp = self.report()["experiments"]["5"]
        base = exp["base"]["primary"]["strategies"]["R2"]["metrics"]
        stress = exp["double_cost"]["primary"]["strategies"]["R2"]["metrics"]
        self.assertLess(stress["net_return"], base["net_return"])

    def test_nonfinite_invalid_structure_falls_back(self):
        data = fixture()
        data["signals"][0]["structure_v1"]["wyckoff_score"] = float("nan")
        with self.assertRaisesRegex(ReplayError, "non_finite_json"):
            self.report(data)

    def test_unsupported_action_never_silently_ignored(self):
        data = fixture()
        data["corporate_actions"]["events"] = [{"type": "rights", "date": data["calendar"][8]}]
        report = self.report(data)
        self.assertEqual(report["status"], "signal_only")
        self.assertIn("corporate_action_processing_not_supported", report["integrity"]["portfolio_blockers"])

    def test_bootstrap_deterministic_and_insufficient_blocks(self):
        arrays = {
            "R0": [0.0] * 50,
            "R1": [0.01] * 50,
            "R2": [0.02] * 50,
            "always_long": [0.0] * 50,
            "momentum_5d": [0.0] * 50,
        }
        first = paired_block_intervals(arrays, block_length=5, samples=100, seed=7)
        self.assertEqual(first, paired_block_intervals(arrays, block_length=5, samples=100, seed=7))
        self.assertAlmostEqual(first["R1-R0"]["mean_difference"], 0.01)
        self.assertEqual(first["R1-R0"]["family_comparisons"], 2)
        self.assertEqual(paired_block_intervals({k: v[:4] for k, v in arrays.items()}, block_length=5), {})

    def test_missing_future_label_does_not_cancel_causal_entry(self):
        original = self.report()
        data = fixture()
        removed = data["calendar"][11]
        data["bars"] = [b for b in data["bars"] if not (b["date"] == removed and b["code"] == "510300")]
        changed = self.report(data)
        first = changed["opportunities"][0]
        self.assertTrue(first["signal_eligible"])
        self.assertFalse(first["label_eligible"])
        for strategy in ("R0", "R1", "R2"):
            before = original["experiments"]["5"]["base"]["primary"]["strategies"][strategy]["trades"][0]
            after = changed["experiments"]["5"]["base"]["primary"]["strategies"][strategy]["trades"][0]
            self.assertEqual(before, after)
        self.assertEqual(
            original["experiments"]["5"]["base"]["primary"]["terminal_date"],
            changed["experiments"]["5"]["base"]["primary"]["terminal_date"],
        )

    def test_future_unavailable_bar_never_marks_nav(self):
        data = fixture()
        for bar in data["bars"]:
            if bar["date"] == data["calendar"][7] and bar["code"] == "510300":
                bar["close"] = 1000
                bar["available_at"] = "2040-01-01T16:00:00+08:00"
        report = self.report(data)
        run = report["experiments"]["5"]["base"]["primary"]["strategies"]["R2"]
        self.assertLess(max(row["nav"] for row in run["daily_nav"]), 1_000_001)
        self.assertGreater(run["metrics"]["stale_mark_days"], 0)
        self.assertEqual(report["experiments"]["5"]["base"]["paired_daily_intervals"], {})

    def test_invalid_exit_price_excludes_label_not_signal(self):
        data = fixture()
        for bar in data["bars"]:
            if bar["date"] == data["calendar"][11] and bar["code"] == "510300":
                bar["open"] = None
        row = self.report(data)["opportunities"][0]
        self.assertTrue(row["signal_eligible"])
        self.assertFalse(row["label_eligible"])
        self.assertIn("forward_price_invalid", row["exclusion_reasons"])

    def test_partial_fill_is_not_full_order_fill(self):
        run = self.report()["experiments"]["5"]["base"]["primary"]["strategies"]["always_long"]
        partial = [r for r in run["trades"] if r["status"] == "partially_filled"]
        self.assertTrue(partial)
        self.assertTrue(all(r["unfilled_shares"] > 0 for r in partial))
        self.assertLess(run["metrics"]["fill_rate_orders"], run["metrics"]["any_fill_rate_orders"])

    def test_open_arriving_after_event_but_before_report_cannot_fill(self):
        data = fixture()
        entry = data["calendar"][6]
        for bar in data["bars"]:
            if bar["date"] == entry and bar["code"] == "510300":
                bar["open"] = 1
                bar["open_available_at"] = data["calendar"][30] + "T09:30:00+08:00"
        run = self.report(data)["experiments"]["5"]["base"]["primary"]["strategies"]["R2"]
        self.assertFalse(
            any(
                r["date"] == entry and r["code"] == "510300" and r["status"] in {"filled", "partially_filled"}
                for r in run["trades"]
            )
        )
        self.assertEqual(run["daily_nav"][0]["shares"]["510300"], 0)

    def test_late_close_not_used_at_earlier_valuation(self):
        data = fixture()
        for bar in data["bars"]:
            if bar["date"] == data["calendar"][7] and bar["code"] == "510300":
                bar["close"] = 1000
                bar["close_available_at"] = data["calendar"][10] + "T15:10:00+08:00"
        run = self.report(data)["experiments"]["5"]["base"]["primary"]["strategies"]["R2"]
        self.assertLess(max(r["nav"] for r in run["daily_nav"]), 1_000_001)
        self.assertGreater(run["metrics"]["stale_mark_days"], 0)

    def test_daily_volume_does_not_substitute_open_snapshot(self):
        data = fixture()
        entry = data["calendar"][6]
        for bar in data["bars"]:
            if bar["date"] == entry:
                bar["open_volume"] = 0
                bar["volume"] = 1000000
        run = self.report(data)["experiments"]["5"]["base"]["primary"]["strategies"]["R2"]
        self.assertEqual(run["daily_nav"][0]["exposure"], 0)

    def test_missing_open_snapshot_evidence_blocks_portfolio(self):
        data = fixture()
        del data["source_manifest"]["execution_snapshot_evidence_ref"]
        report = self.report(data)
        self.assertEqual(report["status"], "signal_only")
        self.assertIn("opening_snapshot_provenance_missing", report["integrity"]["portfolio_blockers"])

    def test_input_unchanged_and_artifacts_atomic_no_overwrite(self):
        data = fixture()
        before = copy.deepcopy(data)
        report = self.report(data)
        self.assertEqual(data, before)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "run"
            write_report(report, target)
            self.assertTrue((target / "manifest.json").exists())
            self.assertTrue((target / "opportunities.jsonl").exists())
            with self.assertRaises(FileExistsError):
                write_report(report, target)
            json.loads((target / "report.json").read_text())


if __name__ == "__main__":
    unittest.main()

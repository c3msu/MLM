from __future__ import annotations

import unittest
from datetime import date, timedelta

from treasury_data.advice import build_portfolio_overview
from treasury_data.investment_views import build_ideas
from treasury_data.scoring_bhadial import (
    BHADIAL_CONDITION_MODULES,
    bhadial_module_ema_metrics_at,
    bhadial_raw_module_score_at,
    bhadial_usable_reliability_score,
)
from treasury_data.sources import SeriesPoint
from treasury_data.validation_build import BhadialWeeklyReplay


def funding_module() -> dict:
    return next(module for module in BHADIAL_CONDITION_MODULES if module["name"] == "Funding")


def cool_duration_indicators() -> dict:
    return {
        "cpi_yoy": 2.3,
        "pce_yoy": 2.2,
        "core_pce_yoy": 2.3,
        "trimmed_mean_pce_yoy": 2.2,
        "ppi_yoy": 1.8,
        "two_year_m1_change_bp": -32.0,
        "s5s30": 80.0,
        "two_year": 4.13,
        "sofr": 3.51,
        "dff": 3.62,
        "breakeven_10y": 2.40,
        "wti": 75.0,
        "wti_shock": 0.0,
    }


class FundingDailyEmaContractTests(unittest.TestCase):
    def test_live_and_validation_replay_use_five_daily_availability_events(self) -> None:
        start = date(2026, 1, 2)
        points = [
            SeriesPoint(start + timedelta(days=index), float(index + 1))
            for index in range(24)
        ]
        # A final reversal makes the five-observation smoother visibly differ
        # from both the latest raw score and the old month-end interpretation.
        points.append(SeriesPoint(start + timedelta(days=24), -5.0))
        series = {"corridor_sofr_iorb_deviation": points}
        module = funding_module()
        target = points[-1].date + timedelta(days=1)

        live = bhadial_module_ema_metrics_at(
            series,
            module,
            target,
            span_observations=5,
        )["legacyFixedScore"]
        replay = BhadialWeeklyReplay(series).module_ema_score_at(module, target, span=5)

        alpha = 2 / 6
        expected = None
        for point in points:
            decision_date = point.date + timedelta(days=1)
            if decision_date > target:
                continue
            raw = bhadial_raw_module_score_at(series, module, decision_date)
            assert raw is not None
            score = float(raw["rawScore"])
            expected = score if expected is None else alpha * score + (1 - alpha) * expected

        self.assertIsNotNone(live)
        self.assertAlmostEqual(float(live), float(expected), places=12)
        self.assertAlmostEqual(float(replay), float(expected), places=12)
        latest_raw = bhadial_raw_module_score_at(series, module, target)
        assert latest_raw is not None
        self.assertNotAlmostEqual(float(live), float(latest_raw["rawScore"]), places=6)

    def test_unchanged_refresh_does_not_apply_the_same_daily_observation_twice(self) -> None:
        start = date(2026, 2, 2)
        points = [
            SeriesPoint(start + timedelta(days=index), float(index))
            for index in range(25)
        ]
        series = {"corridor_sofr_iorb_deviation": points}
        module = funding_module()
        available_on = points[-1].date + timedelta(days=1)

        on_availability = bhadial_module_ema_metrics_at(
            series, module, available_on, span_observations=5
        )
        quiet_refresh = bhadial_module_ema_metrics_at(
            series, module, available_on + timedelta(days=1), span_observations=5
        )

        self.assertEqual(quiet_refresh, on_availability)


class MacroReliabilityFailClosedTests(unittest.TestCase):
    @staticmethod
    def missing_macro() -> dict:
        return {
            "score": 50.0,
            "legacyFixedScore": 50.0,
            "observedOnlyScore": 50.0,
            "reliabilityScore": 50.0,
            "effectiveWeightCoveragePct": 0,
            "scoredFactorCount": 0,
            "scoreContract": "legacy-fixed-weight-compatible",
            "regime": "中性",
        }

    def test_zero_coverage_shrunk_fifty_is_unknown_not_neutral(self) -> None:
        self.assertIsNone(bhadial_usable_reliability_score(self.missing_macro()))
        self.assertEqual(
            bhadial_usable_reliability_score(
                {
                    **self.missing_macro(),
                    "reliabilityScore": 61.0,
                    "effectiveWeightCoveragePct": 80,
                    "scoredFactorCount": 16,
                }
            ),
            61.0,
        )

    def test_missing_macro_evidence_cannot_unlock_long_duration(self) -> None:
        ideas = build_ideas(
            cool_duration_indicators(),
            macro_liquidity=self.missing_macro(),
        )

        self.assertNotEqual(ideas[0]["tag"], "LONG 久期")
        self.assertEqual(ideas[0]["tag"], "HOLD 久期")
        self.assertIn("宏观可靠性证据不足", ideas[0]["text"])
        self.assertIn("macro reliability", ideas[0]["tradeEvidence"]["missingInputs"])
        self.assertFalse(ideas[0]["tradeEvidence"]["available"])

    def test_missing_macro_score_does_not_make_portfolio_overview_available(self) -> None:
        overview = build_portfolio_overview(
            spy_early_warning={
                "score": 50.0,
                "regime": "Neutral",
                "regimeCn": "中性",
                "allocation": {"exposureBandPct": [75, 100]},
            },
            equity_short_term_risk=None,
            global_lppl_risk=None,
            macro_liquidity=self.missing_macro(),
            signal_validation=None,
        )

        macro = next(row for row in overview["layers"] if row["layer"] == "bhadialComposite")
        self.assertIsNone(macro["score"])
        self.assertEqual(macro["regime"], "数据不足")
        self.assertIn("不把收缩到50的未知值", macro["stance"])
        self.assertFalse(overview["available"])


if __name__ == "__main__":
    unittest.main()

import math
import unittest
from datetime import date, timedelta

from treasury_data.build_dashboard import (
    BhadialWeeklyReplay,
    build_bhadial_predictive_lens,
    build_equity_signal_validation_row,
    build_portfolio_overview,
    build_signal_validation,
    build_spy_warning_rule_audit,
)
from treasury_data.signal_validation import (
    SortedSeries,
    alert_breach_episodes,
    block_bootstrap_ci,
    classify_lead_lag,
    effective_weights,
    evaluate_signal,
    redundancy_clusters,
    spearman_ic,
    weekly_dates,
)
from treasury_data.sources import SeriesPoint


def daily_points(values: list[float], *, start: date = date(2021, 1, 4)) -> list[SeriesPoint]:
    points = []
    current = start
    for value in values:
        while current.weekday() >= 5:
            current += timedelta(days=1)
        points.append(SeriesPoint(date=current, value=value))
        current += timedelta(days=1)
    return points


class SpearmanIcTests(unittest.TestCase):
    def test_matches_hand_computed_value(self) -> None:
        signal = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        forward = [2.0, 1.0, 4.0, 3.0, 6.0, 5.0, 8.0, 7.0]
        # Hand-computed Spearman rho for this paired-swap pattern: 1 - 6*8 / (8*63) = 0.90476...
        ic = spearman_ic(signal, forward)
        self.assertIsNotNone(ic)
        self.assertAlmostEqual(ic, 1 - (6 * 8) / (8 * 63), places=6)

    def test_perfect_monotone_is_one(self) -> None:
        signal = [float(i) for i in range(10)]
        forward = [float(i * 2 + 1) for i in range(10)]
        self.assertAlmostEqual(spearman_ic(signal, forward), 1.0, places=9)

    def test_handles_ties_with_average_ranks(self) -> None:
        signal = [1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 4.0]
        forward = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        ic = spearman_ic(signal, forward)
        self.assertIsNotNone(ic)
        self.assertGreater(ic, 0.9)

    def test_too_few_pairs_returns_none(self) -> None:
        self.assertIsNone(spearman_ic([1.0, 2.0], [1.0, 2.0]))

    def test_ignores_none_pairs(self) -> None:
        signal = [1.0, None, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        forward = [1.0, 99.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        self.assertAlmostEqual(spearman_ic(signal, forward), 1.0, places=9)


class WeeklyDatesTests(unittest.TestCase):
    def test_picks_last_trading_day_per_week(self) -> None:
        points = daily_points([100.0 + i for i in range(15)])
        weeks = weekly_dates(points)
        self.assertTrue(all(d.weekday() == 4 for d in weeks[:-1]))
        self.assertEqual(weeks, sorted(weeks))

    def test_empty_input(self) -> None:
        self.assertEqual(weekly_dates([]), [])


class SortedSeriesTests(unittest.TestCase):
    def test_percentile_matches_rank_semantics(self) -> None:
        points = daily_points([1.0, 2.0, 3.0, 4.0, 5.0])
        series = SortedSeries(points)
        self.assertEqual(series.percentile_at(points[-1].date), 100)
        self.assertEqual(series.percentile_at(points[0].date), None)

    def test_forward_return_and_drawdown(self) -> None:
        points = daily_points([100.0, 95.0, 90.0, 99.0, 110.0])
        series = SortedSeries(points)
        drawdown = series.forward_max_drawdown_pct(points[0].date, days=30)
        self.assertAlmostEqual(drawdown, -10.0, places=6)
        forward = series.forward_return_pct(points[0].date, days=4)
        self.assertIsNotNone(forward)

    def test_forward_trough_date(self) -> None:
        points = daily_points([100.0, 95.0, 90.0, 99.0, 110.0])
        series = SortedSeries(points)
        trough = series.forward_trough_date(points[0].date, days=30)
        self.assertEqual(trough, points[2].date)


class EvaluateSignalTests(unittest.TestCase):
    def build_predictive_fixture(self) -> tuple[list[SeriesPoint], list[SeriesPoint]]:
        # Price path: repeated cycles where a drop is preceded by a high signal.
        prices: list[float] = []
        signal_values: list[float] = []
        level = 100.0
        for cycle in range(20):
            crash_cycle = cycle % 4 == 3
            for day in range(10):
                if crash_cycle and day >= 5:
                    level *= 0.985
                else:
                    level *= 1.002
                prices.append(level)
                signal_values.append(90.0 if (crash_cycle and day < 5) else 20.0)
        price_points = daily_points(prices)
        signal_points = [SeriesPoint(date=point.date, value=value) for point, value in zip(price_points, signal_values)]
        return signal_points, price_points

    def test_predictive_signal_gets_positive_oos_ic_and_lift(self) -> None:
        signal_points, price_points = self.build_predictive_fixture()
        result = evaluate_signal(
            signal_points,
            price_points,
            horizons=(7,),
            direction="higher_risk",
            drawdown_threshold_pct=-2.0,
            drawdown_horizon_days=7,
            bootstrap_horizon_days=7,
        )
        self.assertTrue(result["available"])
        horizon = result["horizons"][0]
        self.assertIsNotNone(horizon["icOos"])
        self.assertGreater(horizon["icOos"], 0.3)
        alert = result["alert"]
        self.assertTrue(alert["available"])
        self.assertIsNotNone(alert["lift"])
        self.assertGreater(alert["lift"], 1.5)
        self.assertIsNotNone(alert["leadTimeDays"])

    def test_random_walk_signal_shows_no_skill(self) -> None:
        import random

        rng = random.Random(7)
        prices = [100.0]
        for _ in range(399):
            prices.append(prices[-1] * (1 + rng.uniform(-0.01, 0.01)))
        price_points = daily_points(prices)
        signal_points = [SeriesPoint(date=point.date, value=rng.uniform(0, 100)) for point in price_points]
        result = evaluate_signal(signal_points, price_points, horizons=(7, 30), direction="higher_risk")
        self.assertTrue(result["available"])
        for horizon in result["horizons"]:
            if horizon["icOos"] is not None:
                self.assertLess(abs(horizon["icOos"]), 0.25)

    def test_threshold_uses_only_calibration_slice(self) -> None:
        # Calibration slice signals span 0-50; evaluation slice jumps to 100-150.
        # If the threshold leaked OOS data it would exceed 50.
        values = [float(i % 50) for i in range(130)] + [100.0 + float(i % 50) for i in range(70)]
        price_points = daily_points([100.0 * (1.001**i) for i in range(200)])
        signal_points = [SeriesPoint(date=point.date, value=value) for point, value in zip(price_points, values)]
        result = evaluate_signal(signal_points, price_points, horizons=(7,), oos_split=0.65, direction="higher_risk")
        alert = result["alert"]
        self.assertTrue(alert["available"])
        self.assertLessEqual(alert["thresholdValue"], 50.0)

    def test_unavailable_for_tiny_sample(self) -> None:
        points = daily_points([100.0, 101.0])
        self.assertFalse(evaluate_signal(points, points)["available"])


class BlockBootstrapTests(unittest.TestCase):
    def test_deterministic_with_seed(self) -> None:
        pairs = [(float(i), float(i) + (1.0 if i % 3 else -2.0)) for i in range(40)]
        first = block_bootstrap_ci(pairs, block_len=4, n_boot=200, seed=99)
        second = block_bootstrap_ci(pairs, block_len=4, n_boot=200, seed=99)
        self.assertEqual(first, second)
        self.assertIsNotNone(first)
        self.assertLess(first[0], first[1])

    def test_small_sample_returns_none(self) -> None:
        self.assertIsNone(block_bootstrap_ci([(1.0, 1.0)] * 5, block_len=2))


class AlertBreachEpisodeTests(unittest.TestCase):
    def test_collapses_consecutive_alerts_into_episodes_with_outcome(self) -> None:
        def event(row):
            return row.get("forwardDrawdown") is not None and row["forwardDrawdown"] <= -5.0
        alerts = [
            {"date": date(2025, 1, 6), "forwardDrawdown": -2.0},
            {"date": date(2025, 1, 13), "forwardDrawdown": -8.0},   # same episode (≤14d gap)
            {"date": date(2025, 6, 2), "forwardDrawdown": -1.0},    # new episode (no drawdown)
        ]
        episodes = alert_breach_episodes(alerts, event)
        self.assertEqual(len(episodes), 2)
        self.assertEqual(episodes[0]["date"], "2025-01-06")
        self.assertEqual(episodes[0]["drawdownPct"], -8.0)  # worst in episode
        self.assertTrue(episodes[0]["hit"])
        self.assertEqual(episodes[1]["date"], "2025-06-02")
        self.assertFalse(episodes[1]["hit"])

    def test_empty_alerts(self) -> None:
        self.assertEqual(alert_breach_episodes([], lambda r: False), [])


class ClassifyLeadLagTests(unittest.TestCase):
    def test_shifted_signal_is_leading(self) -> None:
        self.assertEqual(
            classify_lead_lag(forward_ic=0.30, contemporaneous_corr=0.10, trailing_ic=0.05),
            "leading",
        )

    def test_contemporaneous_dominant_is_coincident(self) -> None:
        self.assertEqual(
            classify_lead_lag(forward_ic=0.05, contemporaneous_corr=0.40, trailing_ic=0.10),
            "coincident",
        )

    def test_trailing_dominant_is_lagging(self) -> None:
        self.assertEqual(
            classify_lead_lag(forward_ic=0.05, contemporaneous_corr=0.10, trailing_ic=0.45),
            "lagging",
        )

    def test_weak_everything_is_none(self) -> None:
        self.assertEqual(
            classify_lead_lag(forward_ic=0.02, contemporaneous_corr=0.03, trailing_ic=0.01),
            "none",
        )


class RedundancyClusterTests(unittest.TestCase):
    def test_groups_duplicated_series(self) -> None:
        base = daily_points([float(i % 17) + (i % 5) * 0.3 for i in range(120)])
        shifted = [SeriesPoint(date=point.date, value=point.value * 2 + 1) for point in base]
        independent = daily_points([((i * 7919) % 101) * 1.0 for i in range(120)])
        clusters = redundancy_clusters({"a": base, "b": shifted, "c": independent}, corr_threshold=0.8)
        self.assertEqual(clusters, [["a", "b"]])

    def test_no_clusters_when_uncorrelated(self) -> None:
        first = daily_points([((i * 7919) % 101) * 1.0 for i in range(120)])
        second = daily_points([((i * 104729) % 97) * 1.0 for i in range(120)])
        self.assertEqual(redundancy_clusters({"x": first, "y": second}, corr_threshold=0.8), [])


class EffectiveWeightTests(unittest.TestCase):
    def test_downweights_redundant_clusters(self) -> None:
        modules = [
            {
                "name": "Funding",
                "factors": [
                    {"id": "f1", "weight": 0.5},
                    {"id": "f2", "weight": 0.5},
                ],
            },
            {
                "name": "Risk",
                "factors": [{"id": "r1", "weight": 1.0}],
            },
        ]
        weights = {"Funding": 0.5, "Risk": 0.5}
        rows = effective_weights(modules, weights, [["f1", "f2"]])
        by_id = {row["id"]: row for row in rows}
        self.assertAlmostEqual(sum(row["effectiveWeight"] for row in rows), 1.0, places=3)
        self.assertEqual(by_id["f1"]["clusterId"], "c1")
        self.assertIsNone(by_id["r1"]["clusterId"])
        self.assertLess(by_id["f1"]["effectiveWeight"], by_id["f1"]["configWeight"])
        self.assertGreater(by_id["r1"]["effectiveWeight"], by_id["r1"]["configWeight"])


def long_daily_points(seed: int, *, count: int = 1320, start: date = date(2021, 3, 1), base: float = 100.0) -> list[SeriesPoint]:
    points = []
    current = start
    level = base
    state = seed
    for _ in range(count):
        while current.weekday() >= 5:
            current += timedelta(days=1)
        state = (state * 1103515245 + 12345) % (2**31)
        level *= 1 + ((state / (2**31)) - 0.5) * 0.01
        points.append(SeriesPoint(date=current, value=level))
        current += timedelta(days=1)
    return points


class BuildSignalValidationTests(unittest.TestCase):
    def build_indicators(self) -> dict:
        series = {
            "sp500": long_daily_points(3),
            "net_liquidity": long_daily_points(5, base=6000.0),
            "bank_reserves": long_daily_points(7, base=3000.0),
            "net_liquidity_13w_momentum": long_daily_points(11, base=10.0),
            "tga_deviation": long_daily_points(13, base=1.0),
            "onrrp_buffer_risk": [
                SeriesPoint(date=point.date, value=max(0.0, min(1.0, point.value / 200.0)))
                for point in long_daily_points(17)
            ],
            "vix": long_daily_points(19, base=20.0),
            "nfci": long_daily_points(23, base=-0.3),
        }
        return {"percentile_series": series}

    def test_emits_contract_fields(self) -> None:
        payload = build_signal_validation(self.build_indicators())
        self.assertTrue(payload["available"])
        self.assertGreaterEqual(payload["weeklyObservationCount"], 60)
        self.assertEqual(payload["oosSplitPct"], 65)
        self.assertTrue(payload["factors"])
        factor_ids = {row["id"] for row in payload["factors"]}
        self.assertIn("fed_net_liquidity", factor_ids)
        self.assertIn("vix", factor_ids)
        sample = payload["factors"][0]
        for field in (
            "id", "module", "ic1w", "ic1m", "ic3m", "oosIc1m", "oosIc3m",
            "hitRateOos", "baseRate", "lift", "leadTimeDays", "falseAlarmDays",
            "classification", "clusterId", "observationCount",
        ):
            self.assertIn(field, sample)
        composite_ids = {row["id"] for row in payload["composites"]}
        self.assertIn("bhadialComposite", composite_ids)
        self.assertIn("bhadialChange13w", composite_ids)
        self.assertIn("spyEarlyWarning", composite_ids)
        self.assertTrue(any(row["id"].startswith("sleeve:") for row in payload["composites"]))
        self.assertTrue(payload["effectiveWeights"])
        weight_sum = sum(row["effectiveWeight"] for row in payload["effectiveWeights"])
        self.assertAlmostEqual(weight_sum, 1.0, places=2)

    def test_unavailable_without_price_history(self) -> None:
        payload = build_signal_validation({"percentile_series": {"sp500": []}})
        self.assertFalse(payload["available"])
        self.assertIn("factors", payload)

    def test_duplicated_factor_series_share_cluster(self) -> None:
        indicators = self.build_indicators()
        # Make VIX series an affine copy of NFCI so they should cluster together.
        indicators["percentile_series"]["vix"] = [
            SeriesPoint(date=point.date, value=point.value * 3 + 7)
            for point in indicators["percentile_series"]["nfci"]
        ]
        payload = build_signal_validation(indicators)
        rows = {row["id"]: row for row in payload["factors"]}
        self.assertIsNotNone(rows["vix"]["clusterId"])
        self.assertEqual(rows["vix"]["clusterId"], rows["nfci"]["clusterId"])


class PredictiveLensTests(unittest.TestCase):
    def build_driver_indicators(self) -> dict:
        count = 1320
        driver = [math.sin(2 * math.pi * index / 200.0) for index in range(count)]
        price_points: list[SeriesPoint] = []
        level = 100.0
        current = date(2021, 3, 1)
        state = 11
        dates: list[date] = []
        for index in range(count):
            while current.weekday() >= 5:
                current += timedelta(days=1)
            lagged = driver[max(0, index - 21)]
            state = (state * 1103515245 + 12345) % (2**31)
            noise = ((state / (2**31)) - 0.5) * 0.0004
            level *= 1 + 0.0009 * lagged + noise
            price_points.append(SeriesPoint(date=current, value=level))
            dates.append(current)
            current += timedelta(days=1)
        split = int(count * 0.65)
        series = {
            "sp500": price_points,
            # Three genuinely leading factors (driver-correlated for the full sample).
            "net_liquidity": [SeriesPoint(date=dates[i], value=driver[i] * 100 + 500) for i in range(count)],
            "hy_credit_preference": [SeriesPoint(date=dates[i], value=driver[i] * 0.8 + 30) for i in range(count)],
            "nfci": [SeriesPoint(date=dates[i], value=-driver[i] * 0.4 - 0.3) for i in range(count)],
            # OOS-only factor: random during calibration, predictive only afterwards —
            # calibration-only selection must EXCLUDE it.
            "vix": self.oos_only_vix(driver, dates, split),
        }
        return {"percentile_series": series}

    @staticmethod
    def oos_only_vix(driver: list[float], dates: list[date], split: int) -> list[SeriesPoint]:
        points = []
        state = 31
        for i in range(len(dates)):
            state = (state * 1103515245 + 12345) % (2**31)
            if i < split:
                value = 20.0 + (state / (2**31)) * 10.0
            else:
                value = 20.0 - driver[i] * 8.0
            points.append(SeriesPoint(date=dates[i], value=value))
        return points

    def test_lens_selects_calibration_leading_factors_and_excludes_oos_only(self) -> None:
        payload = build_signal_validation(self.build_driver_indicators())
        self.assertTrue(payload["available"])
        lens = payload["predictiveLens"]
        self.assertTrue(lens["available"])
        selected_ids = {item["id"] for item in lens["selectedFactors"]}
        self.assertIn("fed_net_liquidity", selected_ids)
        self.assertIn("hy_credit", selected_ids)
        self.assertIn("nfci", selected_ids)
        self.assertNotIn("vix", selected_ids)
        self.assertIsNotNone(lens["latestScore"])
        composite_ids = {row["id"] for row in payload["composites"]}
        self.assertIn("bhadialPredictive", composite_ids)
        predictive_row = next(row for row in payload["composites"] if row["id"] == "bhadialPredictive")
        self.assertIsNotNone(predictive_row["oosIc3m"])

    def test_lens_applies_publication_lag_when_replaying(self) -> None:
        requests: list[tuple[str, date]] = []

        class StubReplay:
            def factor_score_at(self, spec, target):
                requests.append((str(spec["id"]), target))
                return 60.0, True

        prices = daily_points([100.0 * (1.002**i) for i in range(300)])
        week = date(2024, 6, 7)
        factor_points = [SeriesPoint(date=point.date, value=float(i)) for i, point in enumerate(prices[:60])]
        factor_series = {"nfci": factor_points, "fed_net_liquidity": factor_points, "vix": factor_points}
        weight_rows = [
            {"id": "nfci", "effectiveWeight": 0.4},
            {"id": "fed_net_liquidity", "effectiveWeight": 0.4},
            {"id": "vix", "effectiveWeight": 0.2},
        ]

        lens = build_bhadial_predictive_lens(
            StubReplay(),
            [week],
            factor_series,
            weight_rows,
            SortedSeries(prices),
            min_calibration_ic=-1.0,
        )

        self.assertTrue(lens["available"])
        requested = {factor_id: target for factor_id, target in requests}
        self.assertEqual(requested["nfci"], week - timedelta(days=7))
        self.assertEqual(requested["fed_net_liquidity"], week - timedelta(days=2))
        self.assertEqual(requested["vix"], week - timedelta(days=1))


class SpyWarningRuleAuditTests(unittest.TestCase):
    def build_weekly_market(self) -> tuple[list[date], list[SeriesPoint]]:
        weeks: list[date] = []
        prices: list[SeriesPoint] = []
        current = date(2023, 1, 6)
        level = 100.0
        for index in range(130):
            if 86 <= index <= 89 or 106 <= index <= 109:
                level *= 0.975
            else:
                level *= 1.003
            weeks.append(current)
            prices.append(SeriesPoint(date=current, value=level))
            current += timedelta(days=7)
        return weeks, prices

    def test_audit_reports_lift_lead_time_and_verdicts(self) -> None:
        weeks, prices = self.build_weekly_market()
        good_fire_weeks = [84, 85, 103, 104]
        rule_fires = {
            "goodAmplifier": [{"date": weeks[i], "trailing3m": 4.0} for i in good_fire_weeks],
            "badDampener": [{"date": weeks[i], "trailing3m": -1.0} for i in (85, 104, 105)],
        }
        rule_meta = {
            "goodAmplifier": {"label": "提前预警", "kind": "amplifier", "scoreEffect": 10.0},
            "badDampener": {"label": "误降噪", "kind": "dampener", "scoreEffect": -10.0},
        }

        audit = build_spy_warning_rule_audit(rule_fires, rule_meta, weeks, SortedSeries(prices))

        self.assertTrue(audit["available"])
        self.assertIsNotNone(audit["baseRate"])
        rules = {row["key"]: row for row in audit["rules"]}
        good = rules["goodAmplifier"]
        self.assertGreaterEqual(good["oosFireCount"], 3)
        self.assertIsNotNone(good["lift"])
        self.assertGreater(good["lift"], 1.15)
        self.assertEqual(good["verdict"], "additive")
        self.assertIsNotNone(good["leadTimeDays"])
        bad = rules["badDampener"]
        self.assertEqual(bad["kind"], "dampener")
        self.assertEqual(bad["verdict"], "counterproductive")

    def test_audit_marks_sparse_rules_insufficient(self) -> None:
        weeks, prices = self.build_weekly_market()
        rule_fires = {"rare": [{"date": weeks[100], "trailing3m": 0.0}]}
        rule_meta = {"rare": {"label": "罕见规则", "kind": "amplifier", "scoreEffect": 3.0}}

        audit = build_spy_warning_rule_audit(rule_fires, rule_meta, weeks, SortedSeries(prices))

        rules = {row["key"]: row for row in audit["rules"]}
        self.assertEqual(rules["rare"]["verdict"], "insufficient")


class PortfolioOverviewTests(unittest.TestCase):
    def build_inputs(self, *, sew_score: float, est_score: float, lppl_status: str = "quiet") -> dict:
        sew_alloc = {
            "horizon": "1-3M",
            "horizonCn": "1-3个月",
            "regime": "Caution" if sew_score >= 60 else "Neutral",
            "regimeCn": "谨慎" if sew_score >= 60 else "中性",
            "stance": "降权/对冲",
            "hedgeAction": "回撤保护优先",
            "exposureBandPct": [50, 75] if sew_score >= 60 else [75, 100],
        }
        est_alloc = {
            "horizon": "1-10d",
            "horizonCn": "1-10个交易日",
            "regime": "Strong Alert" if est_score >= 75 else "Normal",
            "regimeCn": "强告警" if est_score >= 75 else "正常",
            "stance": "短线降风险",
            "hedgeAction": "买入1-2周保护",
            "exposureBandPct": [50, 80] if est_score >= 75 else [100, 100],
        }
        lppl = {
            "indices": [
                {
                    "available": True,
                    "symbol": "QQQ",
                    "status": lppl_status,
                    "score": 70.0 if lppl_status == "risk" else 30.0,
                    "daysToCritical": 45,
                }
            ],
            "indexValidation": {"rows": []},
        }
        signal_validation = {
            "available": True,
            "composites": [
                {
                    "id": "spyEarlyWarning",
                    "hitRateOos": 0.4,
                    "baseRate": 0.3,
                    "lift": 1.33,
                    "leadTimeDays": 40.0,
                    "observationCount": 260,
                    "classification": "lagging",
                },
                {
                    "id": "equityShortTermRisk",
                    "hitRateOos": 0.33,
                    "baseRate": 0.23,
                    "lift": 1.42,
                    "leadTimeDays": 7.0,
                    "observationCount": 600,
                    "classification": "coincident",
                },
            ],
        }
        return {
            "spy_early_warning": {"available": True, "score": sew_score, "regime": sew_alloc["regime"], "regimeCn": sew_alloc["regimeCn"], "asOf": "2026-06-11", "allocation": sew_alloc},
            "equity_short_term_risk": {"available": True, "score": est_score, "asOf": "2026-06-11", "allocation": est_alloc},
            "global_lppl_risk": lppl,
            "macro_liquidity": {"score": 55.0, "regime": "Neutral"},
            "signal_validation": signal_validation,
        }

    def test_combines_three_horizons_into_conservative_band(self) -> None:
        overview = build_portfolio_overview(**self.build_inputs(sew_score=65.0, est_score=80.0))
        self.assertTrue(overview["available"])
        layer_ids = [layer["layer"] for layer in overview["layers"]]
        self.assertIn("equityShortTermRisk", layer_ids)
        self.assertIn("spyEarlyWarning", layer_ids)
        self.assertIn("globalLppl", layer_ids)
        self.assertIn("bhadialComposite", layer_ids)
        # SPY EW Caution [50,75] and short-term Strong Alert [50,80] → element-wise min = [50,75]
        self.assertEqual(overview["suggestedEquityExposureBand"], [50.0, 75.0])
        evidence = next(layer for layer in overview["layers"] if layer["layer"] == "spyEarlyWarning")["evidence"]
        self.assertTrue(evidence["available"])
        self.assertAlmostEqual(evidence["oosHitRate"], 0.4)
        self.assertAlmostEqual(evidence["baseRate"], 0.3)

    def test_flags_macro_calm_vs_short_term_alert_conflict(self) -> None:
        overview = build_portfolio_overview(**self.build_inputs(sew_score=45.0, est_score=80.0))
        self.assertTrue(overview["available"])
        self.assertTrue(overview["conflicts"])
        conflict = overview["conflicts"][0]
        self.assertIn("equityShortTermRisk", conflict["layers"])
        self.assertIn("spyEarlyWarning", conflict["layers"])
        self.assertIn("对冲", conflict["resolution"])

    def test_lppl_risk_with_constructive_macro_yields_options_conflict(self) -> None:
        overview = build_portfolio_overview(**self.build_inputs(sew_score=35.0, est_score=30.0, lppl_status="risk"))
        self.assertTrue(overview["available"])
        lppl_layer = next(layer for layer in overview["layers"] if layer["layer"] == "globalLppl")
        self.assertEqual(lppl_layer["exposureBandPct"], [60.0, 85.0])
        self.assertTrue(any("globalLppl" in conflict["layers"] for conflict in overview["conflicts"]))
        # Binding layer is the LPPL bubble band: [60,85] vs neutral [75,100] and normal [100,100]
        self.assertEqual(overview["suggestedEquityExposureBand"], [60.0, 85.0])

    def test_unavailable_with_fewer_than_two_layers(self) -> None:
        overview = build_portfolio_overview(
            spy_early_warning=None,
            equity_short_term_risk={"available": True, "score": 50.0, "allocation": {}},
            global_lppl_risk=None,
            macro_liquidity=None,
            signal_validation=None,
        )
        self.assertFalse(overview["available"])

    def test_missing_evidence_marked_insufficient(self) -> None:
        inputs = self.build_inputs(sew_score=65.0, est_score=30.0)
        inputs["signal_validation"] = {"available": False}
        overview = build_portfolio_overview(**inputs)
        evidence = next(layer for layer in overview["layers"] if layer["layer"] == "spyEarlyWarning")["evidence"]
        self.assertFalse(evidence["available"])
        self.assertIn("证据不足", evidence["note"])

    def test_regional_tilt_surfaces_rotation_and_breaches(self) -> None:
        regional_monitor = {
            "available": True,
            "rotation": {"available": True, "favorRegions": [], "reduceRegions": ["korea", "taiwan"]},
            "regions": [
                {"key": "korea", "nameCn": "韩国",
                 "factorAlert": {"available": True, "state": "breached", "factorLabelCn": "已实现波动", "current": 43.0, "threshold": 12.0}},
                {"key": "taiwan", "nameCn": "台湾",
                 "factorAlert": {"available": True, "state": "approaching", "factorLabelCn": "已实现波动", "current": 11.0, "threshold": 12.0}},
                {"key": "us", "nameCn": "美国", "factorAlert": {"available": False}},
            ],
        }
        inputs = self.build_inputs(sew_score=45.0, est_score=30.0)
        overview = build_portfolio_overview(**inputs, regional_monitor=regional_monitor)
        tilt = overview["regionalTilt"]
        self.assertTrue(tilt["available"])
        self.assertEqual(tilt["reduceRegions"], ["korea", "taiwan"])
        # Only the BREACHED region is listed as an active breach (approaching is not).
        self.assertEqual([b["key"] for b in tilt["breachedRegions"]], ["korea"])
        self.assertIn("减持 韩国、台湾", tilt["summary"])
        self.assertIn("突破验证阈值", tilt["summary"])

    def test_regional_tilt_highlights_composite_driven_breaches(self) -> None:
        regional_monitor = {
            "available": True,
            "rotation": {"available": True, "favorRegions": [], "reduceRegions": ["japan", "korea"]},
            "regions": [
                {"key": "japan", "nameCn": "日本",
                 "factorAlert": {"available": True, "state": "breached", "source": "composite",
                                 "factorLabelCn": "证据加权综合信号", "current": 1.8, "threshold": 0.9,
                                 "trackRecord": "历史共突破25次, 命中48%"}},
                {"key": "korea", "nameCn": "韩国",
                 "factorAlert": {"available": True, "state": "breached", "source": "factor",
                                 "factorLabelCn": "已实现波动", "current": 43.0, "threshold": 12.0}},
            ],
        }
        inputs = self.build_inputs(sew_score=45.0, est_score=30.0)
        overview = build_portfolio_overview(**inputs, regional_monitor=regional_monitor)
        tilt = overview["regionalTilt"]
        self.assertEqual(tilt["compositeBreachCount"], 1)
        japan = next(b for b in tilt["breachedRegions"] if b["key"] == "japan")
        self.assertEqual(japan["source"], "composite")
        self.assertIn("历史共突破", japan["trackRecord"])
        self.assertIn("已验证综合信号驱动", tilt["summary"])
        self.assertIn("日本", tilt["summary"])

    def test_regional_tilt_unavailable_without_regional_monitor(self) -> None:
        overview = build_portfolio_overview(**self.build_inputs(sew_score=45.0, est_score=30.0))
        self.assertFalse(overview["regionalTilt"]["available"])

    def test_us_internal_tilt_surfaced_in_overview(self) -> None:
        regional_monitor = {
            "available": True,
            "rotation": {"available": True, "favorRegions": [], "reduceRegions": []},
            "regions": [
                {"key": "us", "nameCn": "美国",
                 "internalRotation": {"available": True, "tilt": "broad", "tiltCn": "偏宽基(SPY)、减科技(QQQ)",
                                      "rationale": "美股内部: 科技风险更高 → 偏宽基"}},
            ],
        }
        inputs = self.build_inputs(sew_score=45.0, est_score=30.0)
        overview = build_portfolio_overview(**inputs, regional_monitor=regional_monitor)
        tilt = overview["usInternalTilt"]
        self.assertTrue(tilt["available"])
        self.assertEqual(tilt["tilt"], "broad")
        self.assertIn("偏宽基", tilt["tiltCn"])

    def test_us_internal_tilt_unavailable_without_internal_rotation(self) -> None:
        overview = build_portfolio_overview(**self.build_inputs(sew_score=45.0, est_score=30.0))
        self.assertFalse(overview["usInternalTilt"]["available"])


class EquitySignalValidationRowTests(unittest.TestCase):
    def test_builds_row_from_trend_points(self) -> None:
        points = []
        level = 500.0
        current = date(2024, 1, 2)
        state = 9
        for index in range(220):
            while current.weekday() >= 5:
                current += timedelta(days=1)
            state = (state * 1103515245 + 12345) % (2**31)
            level *= 1 + ((state / (2**31)) - 0.5) * 0.012
            points.append({"date": current.isoformat(), "score": (index * 37) % 100, "spyClose": round(level, 2)})
            current += timedelta(days=1)
        row = build_equity_signal_validation_row({"trend": {"available": True, "points": points}})
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], "equityShortTermRisk")
        self.assertEqual(row["direction"], "higher_risk")

    def test_returns_none_without_trend(self) -> None:
        self.assertIsNone(build_equity_signal_validation_row({"trend": {"available": False, "points": []}}))
        self.assertIsNone(build_equity_signal_validation_row(None))


if __name__ == "__main__":
    unittest.main()

import unittest
import math
from datetime import date, timedelta
from statistics import median

from treasury_data.indicators import compute_indicators, target_range_from_effective_rate, yoy, yoy_or_none
from treasury_data.scoring_bhadial import (
    BHADIAL_CONDITION_MODULES,
    bhadial_conditions_snapshot,
    bhadial_conditions_score_at,
    bhadial_factor_score_at,
    bhadial_module_ema_metrics_at,
    bhadial_raw_module_score_at,
    prepare_bhadial_series,
)
from treasury_data.series_math import (
    build_net_liquidity_points,
    change_points,
    compute_tenor_realized_volatility,
    historical_percentile_at,
    historical_percentile_at_ordered,
    historical_percentile_with_sample_count_at_ordered,
    historical_percentile,
    historical_percentile_points,
    funding_fragmentation_points,
    forward_max_drawdown_pct,
    high_to_low_drawdown_in_window,
    iter_asof_aligned_points,
    median_absolute_deviation_from_sorted,
    onrrp_buffer_risk_points,
    point_change,
    point_change_optional,
    curve_realized_volatility_points,
    realized_volatility_points,
    rolling_median_deviation_points_from_points,
    spread_points,
    treasury_curve_curvature_abs_bp,
    treasury_curve_curvature_abs_points,
    trailing_return,
    volume_percentile_at,
)
from treasury_data.sources import MarketDailyBar, SeriesPoint, TimeSeries, YieldCurveRecord


class TimeAlignmentTests(unittest.TestCase):
    def test_time_series_canonicalizes_unsorted_duplicate_and_nonfinite_dates(self) -> None:
        series = TimeSeries(
            "TEST",
            [
                SeriesPoint(date(2026, 1, 2), 20.0),
                SeriesPoint(date(2026, 1, 1), 10.0),
                SeriesPoint(date(2026, 1, 2), 21.0),
                SeriesPoint(date(2026, 1, 3), math.inf),
            ],
        )

        self.assertEqual(
            series.points,
            [
                SeriesPoint(date(2026, 1, 1), 10.0),
                SeriesPoint(date(2026, 1, 2), 21.0),
            ],
        )
        self.assertEqual(series.value_at_or_before(date(2026, 1, 2)).value, 21.0)

    def test_optional_change_distinguishes_missing_history_from_zero_change(self) -> None:
        unchanged = [
            SeriesPoint(date(2026, 1, 1), 2.0),
            SeriesPoint(date(2026, 2, 1), 2.0),
        ]
        too_short = [SeriesPoint(date(2026, 2, 1), 2.0)]

        self.assertEqual(point_change_optional(unchanged, 30), 0.0)
        self.assertIsNone(point_change_optional(too_short, 30))
        self.assertEqual(point_change(too_short, 30), 0.0)

    def test_asof_lookup_does_not_borrow_first_future_observation(self) -> None:
        series = TimeSeries(
            "TEST",
            [
                SeriesPoint(date(2026, 1, 5), 10.0),
                SeriesPoint(date(2026, 1, 6), 11.0),
            ],
        )

        self.assertIsNone(series.value_at_or_before(date(2026, 1, 4)))
        self.assertEqual(series.value_at_or_before(date(2026, 1, 5)), series.points[0])

    def test_derived_series_starts_only_after_all_legs_are_observable(self) -> None:
        walcl = TimeSeries(
            "WALCL",
            [
                SeriesPoint(date(2026, 1, 5), 10_000.0),
                SeriesPoint(date(2026, 1, 6), 11_000.0),
            ],
        )
        tga = TimeSeries("WTREGEN", [SeriesPoint(date(2026, 1, 6), 2_000.0)])
        rrp = TimeSeries("RRPONTSYD", [SeriesPoint(date(2026, 1, 5), 5.0)])

        net_liquidity = build_net_liquidity_points(
            {"WALCL": walcl, "WTREGEN": tga, "RRPONTSYD": rrp}
        )
        spread = spread_points(walcl, tga)

        self.assertEqual(net_liquidity, [SeriesPoint(date(2026, 1, 6), 4_000.0)])
        self.assertEqual(spread, [SeriesPoint(date(2026, 1, 6), 9_000.0)])

    def test_daily_derived_series_rejects_a_leg_older_than_seven_days(self) -> None:
        left = TimeSeries(
            "LEFT",
            [
                SeriesPoint(date(2026, 1, 8), 10.0),
                SeriesPoint(date(2026, 1, 9), 11.0),
            ],
        )
        right = TimeSeries("RIGHT", [SeriesPoint(date(2026, 1, 1), 3.0)])

        self.assertEqual(spread_points(left, right), [SeriesPoint(date(2026, 1, 8), 7.0)])

    def test_weekly_net_liquidity_rejects_a_leg_older_than_fourteen_days(self) -> None:
        walcl = TimeSeries(
            "WALCL",
            [
                SeriesPoint(date(2026, 1, 15), 10_000.0),
                SeriesPoint(date(2026, 1, 16), 10_100.0),
            ],
        )
        tga = TimeSeries("WTREGEN", [SeriesPoint(date(2026, 1, 1), 2_000.0)])
        rrp = TimeSeries("RRPONTSYD", [SeriesPoint(date(2026, 1, 1), 5.0)])

        self.assertEqual(
            build_net_liquidity_points({"WALCL": walcl, "WTREGEN": tga, "RRPONTSYD": rrp}),
            [SeriesPoint(date(2026, 1, 15), 3_000.0)],
        )

    def test_onrrp_risk_uses_the_official_billions_unit(self) -> None:
        series = TimeSeries(
            "RRPONTSYD",
            [
                SeriesPoint(date(2026, 1, 1), 100.0),
                SeriesPoint(date(2026, 1, 2), 50.0),
                SeriesPoint(date(2026, 1, 3), 0.0),
            ],
        )

        self.assertEqual(
            onrrp_buffer_risk_points(series),
            [
                SeriesPoint(date(2026, 1, 1), 0.0),
                SeriesPoint(date(2026, 1, 2), 0.25),
                SeriesPoint(date(2026, 1, 3), 1.0),
            ],
        )

    def test_curve_curvature_uses_the_uneven_tenor_chord(self) -> None:
        records = [
            YieldCurveRecord(date(2026, 1, 1), {"2Y": 4.0, "10Y": 4.4, "30Y": 5.4}),
            YieldCurveRecord(date(2026, 1, 2), {"2Y": 4.0, "10Y": 4.5, "30Y": 5.4}),
        ]

        self.assertAlmostEqual(treasury_curve_curvature_abs_bp(4.0, 4.4, 5.4), 0.0)
        curvature = treasury_curve_curvature_abs_points(records)
        self.assertEqual([point.date for point in curvature], [date(2026, 1, 1), date(2026, 1, 2)])
        self.assertAlmostEqual(curvature[0].value, 0.0)
        self.assertAlmostEqual(curvature[1].value, 10.0)

    def test_indicator_units_match_official_rrp_and_million_dollar_net_liquidity(self) -> None:
        record = YieldCurveRecord(
            date(2026, 1, 15),
            {"3M": 3.8, "2Y": 4.0, "5Y": 4.2, "10Y": 4.5, "30Y": 5.4},
        )
        fred = {
            "WALCL": TimeSeries("WALCL", [SeriesPoint(record.date, 10_000.0)]),
            "WTREGEN": TimeSeries("WTREGEN", [SeriesPoint(record.date, 2_000.0)]),
            "RRPONTSYD": TimeSeries("RRPONTSYD", [SeriesPoint(record.date, 5.0)]),
            "T10YIE": TimeSeries("T10YIE", [SeriesPoint(record.date, 2.35)]),
        }

        indicators = compute_indicators(
            today=record,
            one_week=record,
            one_month=record,
            curve_records=[record],
            fred=fred,
        )

        self.assertEqual(indicators["rrp_trillions"], 0.005)
        self.assertEqual(indicators["net_liquidity_trillions"], 0.003)
        self.assertEqual(
            indicators["percentile_series"]["breakeven_10y"],
            [SeriesPoint(record.date, 2.35)],
        )
        self.assertAlmostEqual(indicators["curve_curvature_abs_bp"], 10.0)

    def test_linear_asof_join_rewinds_safely_for_regressing_primary_dates(self) -> None:
        primary = [
            SeriesPoint(date(2026, 1, 3), 30.0),
            SeriesPoint(date(2026, 1, 1), 10.0),
            SeriesPoint(date(2026, 1, 4), 40.0),
        ]
        secondary = [
            SeriesPoint(date(2026, 1, 2), 20.0),
            SeriesPoint(date(2026, 1, 4), 40.0),
        ]

        aligned = list(iter_asof_aligned_points(primary, secondary))

        self.assertEqual([row[1][0] for row in aligned], [secondary[0], None, secondary[1]])

    def test_asof_join_canonicalizes_an_unsorted_duplicate_lookup_leg(self) -> None:
        primary = [SeriesPoint(date(2026, 1, 2), 30.0)]
        secondary = [
            SeriesPoint(date(2026, 1, 2), 20.0),
            SeriesPoint(date(2026, 1, 1), 10.0),
            SeriesPoint(date(2026, 1, 2), 21.0),
        ]

        aligned = list(iter_asof_aligned_points(primary, secondary))

        self.assertEqual(aligned[0][1][0], SeriesPoint(date(2026, 1, 2), 21.0))

    def test_fixed_horizon_changes_require_a_full_calendar_lookback(self) -> None:
        points = [
            SeriesPoint(date(2026, 1, 10), 100.0),
            SeriesPoint(date(2026, 1, 20), 110.0),
        ]

        self.assertEqual(point_change(points, days=30), 0.0)
        self.assertEqual(change_points(points, days=30), [])

    def test_fixed_horizon_change_rejects_a_stale_anchor_for_known_cadence(self) -> None:
        points = [
            SeriesPoint(date(2026, 1, 1), 100.0),
            SeriesPoint(date(2026, 3, 1), 110.0),
        ]

        self.assertEqual(point_change_optional(points, days=30), 10.0)
        self.assertIsNone(
            point_change_optional(points, days=30, max_target_gap_days=14)
        )
        self.assertEqual(
            change_points(points, days=30, max_target_gap_days=14),
            [],
        )

    def test_forward_drawdown_requires_a_complete_calendar_horizon(self) -> None:
        points = [
            SeriesPoint(date(2026, 1, 1) + timedelta(days=index), value=value)
            for index, value in enumerate((100.0, 95.0, 90.0, 99.0, 110.0))
        ]

        self.assertAlmostEqual(forward_max_drawdown_pct(points, points[0].date, days=4), -10.0)
        self.assertIsNone(forward_max_drawdown_pct(points, points[0].date, days=30))

    def test_yoy_handles_leap_day_and_rejects_short_history(self) -> None:
        leap_series = TimeSeries(
            "CPI",
            [
                SeriesPoint(date(2023, 2, 28), 100.0),
                SeriesPoint(date(2024, 2, 29), 110.0),
            ],
        )
        short_series = TimeSeries(
            "CPI",
            [
                SeriesPoint(date(2024, 1, 1), 100.0),
                SeriesPoint(date(2024, 2, 1), 110.0),
            ],
        )

        self.assertAlmostEqual(yoy(leap_series), 10.0)
        self.assertEqual(yoy(short_series), 0.0)

    def test_yoy_rejects_a_multi_year_comparison_mislabeled_as_one_year(self) -> None:
        stale = TimeSeries(
            "CPI",
            [
                SeriesPoint(date(2022, 1, 1), 100.0),
                SeriesPoint(date(2026, 1, 1), 120.0),
            ],
        )

        self.assertIsNone(yoy_or_none(stale))

    def test_negative_policy_rate_target_range_uses_floor_not_truncation(self) -> None:
        self.assertEqual(target_range_from_effective_rate(-0.10), "-0.25-0.00%")

    def test_percentile_rejects_a_nonfinite_current_value(self) -> None:
        self.assertIsNone(historical_percentile(math.nan, [1.0, 2.0, 3.0]))

    def test_ordered_percentile_helper_matches_public_unsorted_path(self) -> None:
        points = [
            SeriesPoint(date(2024, 1, 1), 30.0),
            SeriesPoint(date(2022, 1, 1), 10.0),
            SeriesPoint(date(2023, 1, 1), 20.0),
            SeriesPoint(date(2025, 1, 1), 40.0),
        ]
        ordered = sorted(points, key=lambda point: point.date)

        self.assertEqual(
            historical_percentile_at(points, date(2024, 6, 1)),
            historical_percentile_at_ordered(ordered, date(2024, 6, 1)),
        )
        self.assertIsNone(historical_percentile_at_ordered(ordered, date(2021, 12, 31)))

    def test_percentile_trend_uses_only_the_trailing_window_and_no_future_values(self) -> None:
        points = [
            SeriesPoint(date(2020, 1, 1), 1.0),
            SeriesPoint(date(2021, 1, 1), 2.0),
            SeriesPoint(date(2022, 1, 1), 3.0),
            SeriesPoint(date(2023, 1, 1), 4.0),
            SeriesPoint(date(2024, 1, 1), 5.0),
            SeriesPoint(date(2025, 1, 1), 1_000.0),
            SeriesPoint(date(2026, 1, 1), 2_000.0),
        ]
        rows = historical_percentile_points(
            points,
            years=3,
            display_years=6,
            max_points=20,
        )

        by_date = {row["date"]: row for row in rows}
        self.assertEqual(by_date["2024-01-01"]["percentile"], 100)
        self.assertEqual(by_date["2024-01-01"]["value"], 5.0)


class MarketFactorWindowTests(unittest.TestCase):
    @staticmethod
    def bars(count: int) -> list[MarketDailyBar]:
        start = date(2026, 1, 5)
        return [
            MarketDailyBar(
                symbol="SPY",
                date=start + timedelta(days=index),
                open=100.0 + index,
                high=101.0 + index,
                low=99.0 + index,
                close=100.0 + index,
                volume=1_000_000 + index,
                source="test",
            )
            for index in range(count)
        ]

    def test_trailing_return_requires_the_named_number_of_observations(self) -> None:
        bars = self.bars(4)

        self.assertIsNone(trailing_return(bars[:3], bars[2].date, 3))
        self.assertAlmostEqual(trailing_return(bars, bars[3].date, 3), 0.03)

    def test_high_to_low_drawdown_requires_the_high_to_occur_first(self) -> None:
        bars = [
            MarketDailyBar("SPY", date(2026, 1, 5), 90.0, 100.0, 80.0, 90.0, 1_000, "test"),
            MarketDailyBar("SPY", date(2026, 1, 6), 119.0, 120.0, 119.0, 120.0, 1_000, "test"),
            MarketDailyBar("SPY", date(2026, 1, 7), 100.0, 110.0, 90.0, 95.0, 1_000, "test"),
        ]

        self.assertAlmostEqual(high_to_low_drawdown_in_window(bars, bars[1].date, 20), -0.20)
        self.assertAlmostEqual(high_to_low_drawdown_in_window(bars, bars[2].date, 20), -0.25)

    def test_volume_percentile_uses_midrank_for_ties(self) -> None:
        bars = self.bars(10)
        tied = [
            MarketDailyBar(
                bar.symbol,
                bar.date,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                1_000_000,
                bar.source,
            )
            for bar in bars
        ]

        self.assertEqual(volume_percentile_at(tied, tied[-1].date, window=60), 50.0)

    def test_volume_percentile_window_includes_exactly_requested_sessions(self) -> None:
        bars = [
            MarketDailyBar(
                symbol="SPY",
                date=date(2026, 1, 1) + timedelta(days=index),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=10_000 if index == 0 else 105 if index == 10 else 100 + index,
                source="unit-test",
            )
            for index in range(11)
        ]

        # The first (extreme) observation sits just outside the requested ten
        # sessions and must not affect the percentile.
        self.assertEqual(volume_percentile_at(bars, bars[-1].date, window=10), 50.0)


class BhadialPreparationTests(unittest.TestCase):
    def test_prepared_series_is_reusable_and_score_equivalent(self) -> None:
        raw = {
            "net_liquidity": [
                SeriesPoint(date(2025, 1, 1), 20.0),
                SeriesPoint(date(2024, 1, 1), 10.0),
                SeriesPoint(date(2026, 1, 1), 30.0),
            ]
        }
        prepared = prepare_bhadial_series(raw)

        self.assertIs(prepare_bhadial_series(prepared), prepared)
        self.assertEqual(
            [point.date for point in prepared["net_liquidity"]],
            [date(2024, 1, 1), date(2025, 1, 1), date(2026, 1, 1)],
        )
        self.assertEqual(
            bhadial_conditions_score_at(raw, date(2026, 1, 1)),
            bhadial_conditions_score_at(prepared, date(2026, 1, 1)),
        )

    @staticmethod
    def factor_spec(**overrides: object) -> dict[str, object]:
        spec: dict[str, object] = {
            "id": "test_factor",
            "scoreKey": "test_factor",
            "weight": 1.0,
            "direction": "higher_better",
            "method": "level_percentile",
            "cadence": "business_daily",
            "maxAgeDays": 7,
            "minSampleCount": 3,
            "publicationLagDays": 0,
        }
        spec.update(overrides)
        return spec

    def test_factor_warmup_suppresses_two_point_extreme_percentile(self) -> None:
        points = [
            SeriesPoint(date(2026, 1, 1), 10.0),
            SeriesPoint(date(2026, 1, 2), 20.0),
        ]

        warming = bhadial_factor_score_at(
            {"test_factor": points},
            self.factor_spec(),
            date(2026, 1, 2),
        )

        self.assertTrue(warming["observed"])
        self.assertFalse(warming["scoreEligible"])
        self.assertEqual(warming["score"], 50.0)
        self.assertIsNone(warming["percentile"])
        self.assertEqual(warming["effectiveSampleCount"], 2)
        self.assertEqual(warming["scoringStatus"], "warming")

        scored = bhadial_factor_score_at(
            {"test_factor": points + [SeriesPoint(date(2026, 1, 3), 30.0)]},
            self.factor_spec(),
            date(2026, 1, 3),
        )
        self.assertTrue(scored["scoreEligible"])
        self.assertEqual(scored["percentile"], 100)
        self.assertEqual(scored["effectiveSampleCount"], 3)

    def test_factor_freshness_marks_stale_observation_unscorable(self) -> None:
        points = [
            SeriesPoint(date(2025, 12, 1) + timedelta(days=index), float(index))
            for index in range(12)
        ]
        target = date(2026, 1, 1)

        stale = bhadial_factor_score_at(
            {"test_factor": points},
            self.factor_spec(maxAgeDays=7),
            target,
        )

        self.assertFalse(stale["observed"])
        self.assertFalse(stale["scoreEligible"])
        self.assertEqual(stale["score"], 50.0)
        self.assertEqual(stale["observationDate"], "2025-12-12")
        self.assertEqual(stale["ageDays"], 20)
        self.assertEqual(stale["freshnessStatus"], "stale")
        self.assertEqual(stale["scoringStatus"], "stale")

    def test_live_factor_scoring_applies_publication_lag_once(self) -> None:
        points = [
            SeriesPoint(date(2026, 1, 1), 10.0),
            SeriesPoint(date(2026, 1, 2), 20.0),
            SeriesPoint(date(2026, 1, 3), 30.0),
            SeriesPoint(date(2026, 1, 4), -100.0),
        ]
        spec = self.factor_spec(publicationLagDays=2, maxAgeDays=10)

        before_release = bhadial_factor_score_at({"test_factor": points}, spec, date(2026, 1, 5))
        after_release = bhadial_factor_score_at({"test_factor": points}, spec, date(2026, 1, 6))

        self.assertEqual(before_release["observationDate"], "2026-01-03")
        self.assertEqual(before_release["score"], 100.0)
        self.assertEqual(before_release["availabilityCutoff"], "2026-01-03")
        self.assertEqual(after_release["observationDate"], "2026-01-04")
        self.assertEqual(after_release["score"], 0.0)

    def test_snapshot_display_values_match_the_lagged_score_observation(self) -> None:
        indicators = {
            "percentile_series": {
                "net_liquidity": [
                    SeriesPoint(date(2026, 1, 1), 1_000_000.0),
                    SeriesPoint(date(2026, 1, 3), 2_000_000.0),
                    SeriesPoint(date(2026, 1, 4), 9_000_000.0),
                ],
                "breakeven_target_distance": [
                    SeriesPoint(date(2026, 1, 3), 0.1),
                    SeriesPoint(date(2026, 1, 4), 0.2),
                    SeriesPoint(date(2026, 1, 5), 7.6),
                ],
                "breakeven_10y": [
                    SeriesPoint(date(2026, 1, 3), 2.2),
                    SeriesPoint(date(2026, 1, 4), 2.5),
                    SeriesPoint(date(2026, 1, 5), 9.9),
                ],
            },
            # Deliberately conflicting latest values: the snapshot must not
            # pair them with scores computed from the lagged observations.
            "net_liquidity_trillions": 9.0,
            "breakeven_10y": 9.9,
        }

        snapshot = bhadial_conditions_snapshot(indicators, as_of=date(2026, 1, 5))
        components = {component["id"]: component for component in snapshot["components"]}

        liquidity = components["fed_net_liquidity"]
        self.assertEqual(liquidity["observationDate"], "2026-01-03")
        self.assertEqual(liquidity["displayObservationDate"], "2026-01-03")
        self.assertEqual(liquidity["value"], "$2.00T")

        breakeven = components["t10yie"]
        self.assertEqual(breakeven["observationDate"], "2026-01-04")
        self.assertEqual(breakeven["displayObservationDate"], "2026-01-04")
        self.assertEqual(breakeven["value"], "2.50%")

    def test_shock_only_factor_can_penalize_but_never_reward_above_neutral(self) -> None:
        quiet_points = [
            SeriesPoint(date(2026, 1, 1), 10.0),
            SeriesPoint(date(2026, 1, 2), 20.0),
            SeriesPoint(date(2026, 1, 3), 1.0),
        ]
        stressed_points = [*quiet_points, SeriesPoint(date(2026, 1, 4), 30.0)]
        spec = self.factor_spec(method="shock_only", direction="lower_better")

        quiet = bhadial_factor_score_at({"test_factor": quiet_points}, spec, date(2026, 1, 3))
        stressed = bhadial_factor_score_at({"test_factor": stressed_points}, spec, date(2026, 1, 4))

        self.assertEqual(quiet["percentile"], 0)
        self.assertEqual(quiet["score"], 50.0)
        self.assertEqual(stressed["percentile"], 100)
        self.assertEqual(stressed["score"], 0.0)

    def test_monthly_ema_does_not_double_count_an_unchanged_current_month(self) -> None:
        spec = self.factor_spec(
            cadence="monthly",
            maxAgeDays=45,
            minSampleCount=2,
        )
        module = {"name": "Synthetic", "factors": [spec]}
        points = [
            SeriesPoint(date(2026, month, 9), float(month))
            for month in range(1, 8)
        ]

        on_observation = bhadial_module_ema_metrics_at(
            {"test_factor": points}, module, date(2026, 7, 9), span_months=5
        )
        next_day = bhadial_module_ema_metrics_at(
            {"test_factor": points}, module, date(2026, 7, 10), span_months=5
        )

        self.assertEqual(next_day, on_observation)

    def test_dropout_exposes_observed_only_and_coverage_shrunk_scores(self) -> None:
        primary = self.factor_spec(id="primary", scoreKey="primary", weight=0.75)
        missing = self.factor_spec(id="missing", scoreKey="missing", weight=0.25)
        module = {"name": "Test", "factors": [primary, missing]}
        series = {
            "primary": [
                SeriesPoint(date(2026, 1, 1), 1.0),
                SeriesPoint(date(2026, 1, 2), 2.0),
                SeriesPoint(date(2026, 1, 3), 3.0),
            ]
        }

        row = bhadial_raw_module_score_at(series, module, date(2026, 1, 3))

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["rawScore"], 87.5)
        self.assertEqual(row["legacyFixedScore"], 87.5)
        self.assertEqual(row["observedOnlyScore"], 100.0)
        self.assertEqual(row["effectiveWeightCoverage"], 0.75)
        self.assertEqual(row["reliabilityScore"], 87.5)
        self.assertEqual(row["scoredFactorCount"], 1)

    def test_conditions_score_keeps_legacy_key_and_labels_funding_daily_ema(self) -> None:
        liquidity = [
            SeriesPoint(date(2025, 10, 1) + timedelta(days=index * 7), float(index))
            for index in range(12)
        ]
        # Net liquidity declares a two-day publication lag, so score it on the
        # first decision date when the final observation is actually available.
        target = liquidity[-1].date + timedelta(days=2)

        row = bhadial_conditions_score_at(
            {"net_liquidity": liquidity},
            target,
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["score"], row["legacyFixedScore"])
        self.assertEqual(row["observedOnlyScore"], 100.0)
        self.assertAlmostEqual(row["effectiveWeightCoverage"], 0.17 * 0.60)
        self.assertAlmostEqual(
            row["reliabilityScore"],
            50.0 + 50.0 * row["effectiveWeightCoverage"],
        )
        funding = next(module for module in row["modules"] if module["name"] == "Funding")
        self.assertIsNone(funding["emaSpanMonths"])
        self.assertIsNone(funding["ema5MonthScore"])
        self.assertEqual(funding["emaSpanObservations"], 5)
        self.assertEqual(funding["emaSpanUnit"], "daily_availability_observations")
        self.assertEqual(funding["ema5ObservationScore"], funding["ema5Score"])
        self.assertIn("EMA(5 daily availability observations)", funding["method"])

    def test_all_active_factor_specs_declare_freshness_contract(self) -> None:
        factors = [factor for module in BHADIAL_CONDITION_MODULES for factor in module["factors"]]

        self.assertEqual(len(factors), 21)
        self.assertTrue(all(factor.get("cadence") for factor in factors))
        self.assertTrue(all(int(factor.get("maxAgeDays", 0)) > 0 for factor in factors))
        self.assertTrue(all(int(factor.get("minSampleCount", 0)) >= 3 for factor in factors))

    def test_percentile_details_report_effective_window_count(self) -> None:
        points = [
            SeriesPoint(date(2020, 1, 1), 1.0),
            SeriesPoint(date(2025, 1, 1), 2.0),
            SeriesPoint(date(2026, 1, 1), 3.0),
        ]

        percentile, count = historical_percentile_with_sample_count_at_ordered(
            points,
            date(2026, 1, 1),
        )

        self.assertEqual(percentile, 100)
        self.assertEqual(count, 2)


class RollingMedianWindowTests(unittest.TestCase):
    @staticmethod
    def reference(
        points: list[SeriesPoint],
        *,
        window_days: int,
        positive_only: bool = False,
    ) -> list[SeriesPoint]:
        ordered = sorted(points, key=lambda point: point.date)
        rows: list[SeriesPoint] = []
        for index, point in enumerate(ordered):
            start = point.date - timedelta(days=window_days)
            values = [
                candidate.value
                for candidate in ordered[: index + 1]
                if start <= candidate.date <= point.date and math.isfinite(candidate.value)
            ]
            if len(values) < 2:
                continue
            deviation = point.value - median(values)
            rows.append(SeriesPoint(point.date, max(0.0, deviation) if positive_only else deviation))
        return rows

    def test_sliding_window_matches_reference_for_irregular_dates_and_duplicates(self) -> None:
        points = [
            SeriesPoint(date(2026, 1, 1), 10.0),
            SeriesPoint(date(2026, 1, 2), 12.0),
            SeriesPoint(date(2026, 1, 8), 12.0),
            SeriesPoint(date(2026, 1, 10), 8.0),
            SeriesPoint(date(2026, 1, 22), 15.0),
        ]

        self.assertEqual(
            rolling_median_deviation_points_from_points(points, window_days=10),
            self.reference(points, window_days=10),
        )
        self.assertEqual(
            rolling_median_deviation_points_from_points(points, window_days=10, positive_only=True),
            self.reference(points, window_days=10, positive_only=True),
        )

    def test_sorted_mad_matches_statistics_median_for_odd_even_and_duplicate_samples(self) -> None:
        samples = [
            [1.0, 2.0, 3.0],
            [1.0, 2.0, 4.0, 8.0],
            [1.0, 1.0, 1.0, 5.0, 9.0],
            [-3.0, -1.0, 2.0, 2.0, 7.0, 11.0],
        ]
        for sample in samples:
            ordered = sorted(sample)
            center = median(ordered)
            expected = median(abs(value - center) for value in ordered)
            self.assertEqual(median_absolute_deviation_from_sorted(ordered, center), expected)


class RollingVolatilityTests(unittest.TestCase):
    def test_curve_volatility_treats_duplicate_dates_as_revisions_not_returns(self) -> None:
        records = [
            YieldCurveRecord(date(2026, 1, 1), {"10Y": 4.00}),
            YieldCurveRecord(date(2026, 1, 2), {"10Y": 4.10}),
            # The later row for Jan 2 is the revised official value.
            YieldCurveRecord(date(2026, 1, 2), {"10Y": 4.20}),
            YieldCurveRecord(date(2026, 1, 3), {"10Y": 4.50}),
        ]

        actual = curve_realized_volatility_points(records, "10Y", window=2)
        changes = [20.0, 30.0]
        mean = sum(changes) / 2
        expected = math.sqrt(sum((value - mean) ** 2 for value in changes)) * math.sqrt(252)

        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0].date, date(2026, 1, 3))
        self.assertAlmostEqual(actual[0].value, expected)

    def test_sliding_variance_matches_two_pass_reference(self) -> None:
        start = date(2025, 1, 1)
        values = [100.0 + index * 0.07 + ((index * 13) % 19) / 10 for index in range(400)]
        points = [SeriesPoint(start + timedelta(days=index), value) for index, value in enumerate(values)]
        series = TimeSeries("TEST", points)
        actual = realized_volatility_points(series, window=63)

        returns = [math.log(current / prior) for prior, current in zip(values, values[1:])]
        expected: list[float] = []
        for index in range(62, len(returns)):
            sample = returns[index - 62 : index + 1]
            sample_mean = sum(sample) / len(sample)
            variance = sum((value - sample_mean) ** 2 for value in sample) / (len(sample) - 1)
            expected.append(math.sqrt(variance) * math.sqrt(252) * 100)

        self.assertEqual(len(actual), len(expected))
        for point, expected_value in zip(actual, expected):
            self.assertAlmostEqual(point.value, expected_value, places=10)

    def test_realized_volatility_requires_full_window(self) -> None:
        start = date(2026, 1, 1)
        short = TimeSeries(
            "SHORT",
            [SeriesPoint(start + timedelta(days=index), 100.0 + index) for index in range(63)],
        )
        complete = TimeSeries(
            "COMPLETE",
            [SeriesPoint(start + timedelta(days=index), 100.0 + index) for index in range(64)],
        )

        self.assertEqual(realized_volatility_points(short, window=63), [])
        self.assertEqual(len(realized_volatility_points(complete, window=63)), 1)

    def test_curve_volatility_resets_after_long_source_gap(self) -> None:
        records = [
            YieldCurveRecord(date(2026, 1, 1), {"10Y": 4.00}),
            YieldCurveRecord(date(2026, 1, 2), {"10Y": 4.10}),
            YieldCurveRecord(date(2026, 1, 3), {"10Y": 4.00}),
            YieldCurveRecord(date(2026, 1, 20), {"10Y": 5.00}),
            YieldCurveRecord(date(2026, 1, 21), {"10Y": 5.10}),
            YieldCurveRecord(date(2026, 1, 22), {"10Y": 5.00}),
        ]

        points = curve_realized_volatility_points(records, "10Y", window=2)

        self.assertEqual([point.date for point in points], [date(2026, 1, 3), date(2026, 1, 22)])
        expected = math.sqrt(200.0) * math.sqrt(252)
        self.assertAlmostEqual(points[-1].value, expected)
        self.assertAlmostEqual(compute_tenor_realized_volatility(records, "10Y", window=2), expected)

    def test_price_volatility_resets_after_long_source_gap(self) -> None:
        series = TimeSeries(
            "TEST",
            [
                SeriesPoint(date(2026, 1, 1), 100.0),
                SeriesPoint(date(2026, 1, 2), 101.0),
                SeriesPoint(date(2026, 1, 3), 100.0),
                SeriesPoint(date(2026, 1, 20), 150.0),
                SeriesPoint(date(2026, 1, 21), 151.5),
                SeriesPoint(date(2026, 1, 22), 150.0),
            ],
        )

        points = realized_volatility_points(series, window=2)

        self.assertEqual([point.date for point in points], [date(2026, 1, 3), date(2026, 1, 22)])
        self.assertLess(points[-1].value, 30.0)

    def test_funding_fragmentation_matches_naive_rolling_median_and_mad(self) -> None:
        start = date(2025, 1, 1)

        def make_series(name: str, offset: float, multiplier: int) -> TimeSeries:
            return TimeSeries(
                name,
                [
                    SeriesPoint(
                        start + timedelta(days=index),
                        4.0 + offset + ((index * multiplier) % 29) / 1_000,
                    )
                    for index in range(120)
                ],
            )

        sofr = make_series("SOFR", 0.00, 13)
        obfr = make_series("OBFR", 0.01, 17)
        iorb = make_series("IORB", 0.02, 19)
        rrp = make_series("RRP", 0.03, 23)
        actual = funding_fragmentation_points(sofr, obfr, iorb, rrp, z_window=30, smooth_window=7)

        legs = [
            (
                (sofr.points[index].value - obfr.points[index].value) * 100,
                (sofr.points[index].value - iorb.points[index].value) * 100,
                (sofr.points[index].value - rrp.points[index].value) * 100,
            )
            for index in range(len(sofr.points))
        ]
        alpha = 2 / 8
        ema: float | None = None
        expected: list[float] = []
        for index, values in enumerate(legs):
            z_scores: list[float] = []
            for leg_index, value in enumerate(values):
                # The current observation is the value being normalized, not
                # part of its own robust reference distribution.
                sample = [row[leg_index] for row in legs[max(0, index - 30) : index]]
                if len(sample) < 3:
                    z_scores.append(0.0)
                    continue
                center = median(sample)
                mad = median(abs(item - center) for item in sample)
                z_scores.append((value - center) / max(mad * 1.4826, 1.0))
            mean_z = sum(z_scores) / len(z_scores)
            dispersion = math.sqrt(sum((value - mean_z) ** 2 for value in z_scores) / len(z_scores))
            ema = dispersion if ema is None else alpha * dispersion + (1 - alpha) * ema
            expected.append(ema)

        self.assertEqual(len(actual), len(expected))
        for point, expected_value in zip(actual, expected):
            self.assertAlmostEqual(point.value, expected_value, places=12)

    def test_funding_fragmentation_resets_rolling_state_after_long_gap(self) -> None:
        dates = [date(2026, 1, day) for day in (1, 2, 3, 4, 20)]
        sofr = TimeSeries("SOFR", [SeriesPoint(point_date, 5.0) for point_date in dates])

        def leg(name: str, offsets_bp: list[float]) -> TimeSeries:
            return TimeSeries(
                name,
                [
                    SeriesPoint(point_date, 5.0 - offset / 100)
                    for point_date, offset in zip(dates, offsets_bp)
                ],
            )

        points = funding_fragmentation_points(
            sofr,
            leg("OBFR", [0, 1, 2, 3, 0]),
            leg("IORB", [0, 0, 0, 0, 0]),
            leg("RRP", [0, -1, -2, -3, 0]),
            z_window=252,
            smooth_window=3,
            max_alignment_gap_days=7,
        )

        self.assertGreater(points[-2].value, 0.0)
        self.assertEqual(points[-1], SeriesPoint(date(2026, 1, 20), 0.0))

    def test_curve_volatility_uses_the_same_fixed_window_contract(self) -> None:
        start = date(2025, 1, 1)
        records = [
            YieldCurveRecord(
                start + timedelta(days=index),
                {"10Y": 2.0 + index * 0.001 + ((index * 7) % 11) / 100},
            )
            for index in range(90)
        ]
        actual = curve_realized_volatility_points(records, "10Y", window=21)
        changes = [
            (current.values["10Y"] - prior.values["10Y"]) * 100
            for prior, current in zip(records, records[1:])
        ]
        expected: list[float] = []
        for index in range(20, len(changes)):
            sample = changes[index - 20 : index + 1]
            sample_mean = sum(sample) / len(sample)
            variance = sum((value - sample_mean) ** 2 for value in sample) / (len(sample) - 1)
            expected.append(math.sqrt(variance) * math.sqrt(252))

        self.assertEqual(len(actual), len(expected))
        for point, expected_value in zip(actual, expected):
            self.assertAlmostEqual(point.value, expected_value, places=10)


if __name__ == "__main__":
    unittest.main()

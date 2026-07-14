import unittest
from datetime import date, timedelta

from treasury_data.series_math import blended_relative_return_points, rolling_relative_return_points
from treasury_data.sources import SeriesPoint, TimeSeries


def compounded_series(series_id: str, growth: float, count: int = 12) -> TimeSeries:
    value = 100.0
    points = []
    current = date(2026, 1, 1)
    for _ in range(count):
        value *= growth
        points.append(SeriesPoint(current, value))
        current += timedelta(days=1)
    return TimeSeries(series_id, points)


class RelativeReturnTests(unittest.TestCase):
    def test_rolling_relative_return_compares_changes_not_index_levels(self):
        numerator = compounded_series("risk", 1.02)
        denominator = compounded_series("safe", 1.01)

        points = rolling_relative_return_points(numerator, denominator, window=3)

        expected = ((1.02**3) / (1.01**3) - 1) * 100
        self.assertEqual(len(points), 9)
        self.assertAlmostEqual(points[-1].value, expected, places=9)

    def test_blend_requires_both_horizons_and_averages_them(self):
        numerator = compounded_series("risk", 1.02)
        denominator = compounded_series("safe", 1.01)

        points = blended_relative_return_points(numerator, denominator, windows=(2, 4))

        expected_2 = ((1.02**2) / (1.01**2) - 1) * 100
        expected_4 = ((1.02**4) / (1.01**4) - 1) * 100
        self.assertEqual(points[0].date, numerator.points[4].date)
        self.assertAlmostEqual(points[-1].value, (expected_2 + expected_4) / 2, places=9)

    def test_alignment_never_uses_a_future_denominator_point(self):
        numerator = compounded_series("risk", 1.01, count=6)
        denominator = TimeSeries(
            "safe",
            [
                SeriesPoint(date(2026, 1, 3), 100.0),
                SeriesPoint(date(2026, 1, 6), 101.0),
            ],
        )

        points = rolling_relative_return_points(numerator, denominator, window=2)

        self.assertTrue(points)
        self.assertGreaterEqual(points[0].date, date(2026, 1, 5))


if __name__ == "__main__":
    unittest.main()

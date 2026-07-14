import unittest

from treasury_data.dashboard_contract import (
    CURRENT_SCHEMA_VERSION,
    dashboard_contract_issues,
    require_dashboard_contract,
    stamp_dashboard_contract,
)


class DashboardContractTests(unittest.TestCase):
    def test_stamp_adds_current_version_without_overwriting_existing_version(self):
        payload = {"asOf": "2026-07-10", "generatedAt": "2026-07-13T00:00:00+00:00"}

        self.assertIs(stamp_dashboard_contract(payload), payload)
        self.assertEqual(payload["schemaVersion"], CURRENT_SCHEMA_VERSION)

        payload["schemaVersion"] = "future"
        stamp_dashboard_contract(payload)
        self.assertEqual(payload["schemaVersion"], "future")

    def test_contract_accepts_versioned_envelope(self):
        payload = {
            "schemaVersion": CURRENT_SCHEMA_VERSION,
            "asOf": "2026-07-10",
            "generatedAt": "2026-07-13T00:00:00+00:00",
            "sourceStatus": [],
            "curve": {"tenors": ["2Y", "10Y"]},
        }

        self.assertEqual(dashboard_contract_issues(payload), [])
        self.assertIs(require_dashboard_contract(payload), payload)

    def test_contract_rejects_unknown_version_and_wrong_nested_type(self):
        issues = dashboard_contract_issues(
            {
                "schemaVersion": "2.0.0",
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-13T00:00:00+00:00",
                "curve": {"tenors": "10Y"},
            }
        )

        self.assertIn("unsupported schemaVersion: 2.0.0", issues)
        self.assertIn("curve.tenors must be an array", issues)

    def test_contract_rejects_malformed_or_naive_snapshot_dates(self):
        malformed = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "07/10/2026",
                "generatedAt": "2026-07-13 00:00:00",
            }
        )
        self.assertIn("asOf must be an ISO date", malformed)
        self.assertIn("generatedAt must include a timezone", malformed)

        future_as_of = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-14",
                "generatedAt": "2026-07-13T23:00:00+00:00",
            }
        )
        self.assertIn("asOf must not be after generatedAt date", future_as_of)

    def test_contract_rejects_non_finite_json_numbers(self):
        issues = dashboard_contract_issues(
            {
                "schemaVersion": CURRENT_SCHEMA_VERSION,
                "asOf": "2026-07-10",
                "generatedAt": "2026-07-13T00:00:00+00:00",
                "macroLiquidity": {"score": float("nan")},
            }
        )

        self.assertTrue(any("strict JSON serializable" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from treasury_data.api import build_health_payload
from treasury_data.dashboard_contract import CURRENT_SCHEMA_VERSION


class HealthContractIntegrityTests(unittest.TestCase):
    @staticmethod
    def dashboard(**overrides):
        payload = {
            "schemaVersion": CURRENT_SCHEMA_VERSION,
            "asOf": "2026-07-17",
            "generatedAt": "2026-07-19T14:34:26+00:00",
            "sourceStatus": [],
        }
        payload.update(overrides)
        return payload

    def test_health_is_ok_when_current_dashboard_contract_passes(self) -> None:
        payload = build_health_payload(self.dashboard())

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(
            payload["dashboardContract"],
            {"valid": True, "scope": "full", "issues": []},
        )

    def test_legacy_numeric_action_band_degrades_health(self) -> None:
        payload = build_health_payload(
            self.dashboard(
                equityShortTermRisk={
                    "available": True,
                    "score": 39.7,
                    "allocation": {"exposureBandPct": [100, 100]},
                }
            )
        )

        self.assertEqual(payload["status"], "degraded")
        self.assertFalse(payload["dashboardContract"]["valid"])
        self.assertTrue(
            any(
                "numeric allocation requires" in issue
                for issue in payload["dashboardContract"]["issues"]
            )
        )

    def test_legacy_envelope_still_runs_decision_only_health_gate(self) -> None:
        payload = build_health_payload(
            {
                "sourceStatus": [],
                "equityShortTermRisk": {
                    "available": True,
                    "allocation": {"exposureBandPct": [100, 100]},
                },
            }
        )

        self.assertEqual(payload["dashboardContract"]["scope"], "decision-only")
        self.assertEqual(payload["status"], "degraded")


if __name__ == "__main__":
    unittest.main()

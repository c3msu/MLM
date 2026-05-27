import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_service import DataService


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        self.data_dir = os.path.join(self.tmpdir.name, "data")
        self.service = DataService(self.db_path, self.data_dir)
        self.service.init_database()
        self.service.bootstrap_defaults()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_dashboard_contract(self):
        dashboard = self.service.get_dashboard_data()
        self.assertIn("overall", dashboard)
        self.assertIn("modules", dashboard)
        self.assertIn("history", dashboard)
        self.assertIn("data_freshness", dashboard)

    def test_module_detail_contract(self):
        module = self.service.get_module_detail("liquidity")
        self.assertIsNotNone(module)
        self.assertIn("factors_count", module)
        self.assertIn("scored_factors_count", module)
        self.assertIn("factors", module)
        self.assertEqual(len(module["factors"]), 8)

    def test_factor_history_contract(self):
        data = self.service.get_factor_history("liquidity", "liq_fed_balance_sheet", days=30)
        self.assertEqual(data["module_id"], "liquidity")
        self.assertEqual(data["factor_id"], "liq_fed_balance_sheet")
        self.assertIn("dates", data)
        self.assertIn("values", data)


if __name__ == "__main__":
    unittest.main()

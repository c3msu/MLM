import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_service import DataService


class FormulaTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        self.data_dir = os.path.join(self.tmpdir.name, "data")
        self.service = DataService(self.db_path, self.data_dir)
        self.service.init_database()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_spread_formula(self):
        value = self.service._formula_value("spread", [5.0, 3.0], [[5.0], [3.0]], 0, {})
        self.assertEqual(value, 2.0)

    def test_relative_return_formula(self):
        dep_arrays = [
            [100.0, 110.0],
            [100.0, 105.0],
        ]
        value = self.service._formula_value(
            "relative_return",
            [110.0, 105.0],
            dep_arrays,
            1,
            {"window": 1},
        )
        self.assertAlmostEqual(value, 5.0, places=6)

    def test_drawdown_formula(self):
        dep_arrays = [[100.0, 120.0, 90.0]]
        value = self.service._formula_value("drawdown", [90.0], dep_arrays, 2, {"window": 3})
        self.assertAlmostEqual(value, -25.0, places=6)


if __name__ == "__main__":
    unittest.main()

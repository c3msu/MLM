import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from factor_catalog import FACTOR_CATALOG, MODULE_META


class FactorCatalogTests(unittest.TestCase):
    def test_catalog_counts(self):
        self.assertEqual(len(FACTOR_CATALOG), 47)

        scored = [factor for factor in FACTOR_CATALOG if not factor.display_only]
        display = [factor for factor in FACTOR_CATALOG if factor.display_only]
        self.assertEqual(len(scored), 30)
        self.assertEqual(len(display), 17)

    def test_module_distribution(self):
        expected = {module: cfg["target_factors"] for module, cfg in MODULE_META.items()}
        actual = {module: 0 for module in MODULE_META.keys()}

        for factor in FACTOR_CATALOG:
            actual[factor.module] += 1

        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()

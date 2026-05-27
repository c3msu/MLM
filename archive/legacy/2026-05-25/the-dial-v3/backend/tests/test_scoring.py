import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_service import DataService


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        self.data_dir = os.path.join(self.tmpdir.name, "data")
        self.service = DataService(self.db_path, self.data_dir)
        self.service.init_database()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_score_mapping_higher_better(self):
        self.assertEqual(self.service._score_from_percentile(80, "higher_better"), 80)

    def test_score_mapping_lower_better(self):
        self.assertEqual(self.service._score_from_percentile(80, "lower_better"), 20)

    def test_score_mapping_neutral(self):
        self.assertEqual(self.service._score_from_percentile(50, "neutral"), 100)
        self.assertEqual(self.service._score_from_percentile(0, "neutral"), 0)


if __name__ == "__main__":
    unittest.main()

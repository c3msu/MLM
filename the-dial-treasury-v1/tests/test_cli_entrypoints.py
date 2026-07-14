import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CliEntrypointTests(unittest.TestCase):
    def test_smoke_check_help_runs_without_pythonpath(self):
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)

        completed = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "smoke_check.py"), "--help"],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("usage:", completed.stdout.lower())


if __name__ == "__main__":
    unittest.main()

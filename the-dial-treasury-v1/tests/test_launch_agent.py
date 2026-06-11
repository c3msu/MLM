import plistlib
import unittest
from pathlib import Path

from scripts.install_launch_agent import build_launch_agent_plist
from scripts.install_health_agent import build_health_agent_plist


class LaunchAgentTests(unittest.TestCase):
    def test_plist_runs_server_as_persistent_background_agent(self):
        raw = build_launch_agent_plist(
            label="com.example.treasury",
            python_path=Path("/usr/bin/python3"),
            daily_at="16:30",
            port=8451,
            log_dir=Path("/tmp/treasury-logs"),
        )
        payload = plistlib.loads(raw)

        self.assertEqual(payload["Label"], "com.example.treasury")
        self.assertTrue(payload["RunAtLoad"])
        self.assertTrue(payload["KeepAlive"])
        self.assertEqual(payload["ProgramArguments"][:2], ["/bin/zsh", "-lc"])
        command = payload["ProgramArguments"][2]
        self.assertIn("serve.py", command)
        self.assertIn("--daily-at", command)
        self.assertIn("16:30", command)
        self.assertIn("--equity-interval-minutes 30", command)
        self.assertIn("--equity-catchup-interval-minutes 5", command)
        self.assertIn("--equity-after-close-lag-minutes 20", command)
        self.assertIn("launchd.out.log", payload["StandardOutPath"])

    def test_health_plist_runs_daily_health_check_with_notification(self):
        raw = build_health_agent_plist(
            label="com.example.treasury-health",
            python_path=Path("/usr/bin/python3"),
            daily_at="16:45",
            port=8451,
            log_dir=Path("/tmp/treasury-logs"),
            notify=True,
        )
        payload = plistlib.loads(raw)

        self.assertEqual(payload["Label"], "com.example.treasury-health")
        self.assertTrue(payload["RunAtLoad"])
        self.assertNotIn("KeepAlive", payload)
        self.assertEqual(payload["StartCalendarInterval"], {"Hour": 16, "Minute": 45})
        self.assertEqual(payload["ProgramArguments"][:2], ["/bin/zsh", "-lc"])
        command = payload["ProgramArguments"][2]
        self.assertIn("check_health.py", command)
        self.assertIn("http://127.0.0.1:8451/api/health", command)
        self.assertIn("--notify", command)
        self.assertIn("health.out.log", payload["StandardOutPath"])


if __name__ == "__main__":
    unittest.main()

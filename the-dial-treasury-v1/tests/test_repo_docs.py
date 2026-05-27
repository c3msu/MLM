import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "the-dial-treasury-v1"


class RepoDocsTests(unittest.TestCase):
    def test_project_status_reflects_git_published_repository(self):
        status = (REPO_ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("root is not a git repository", status)
        self.assertIn("https://github.com/c3msu/MLM", status)
        self.assertIn("https://github.com/c3msu/MLM", readme)
        self.assertIn("SQLite", status)
        self.assertIn("not tracked", status)

    def test_ignore_rules_protect_runtime_artifacts(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

        for pattern in (
            ".playwright-cli/",
            "output/",
            "test-results/",
            "playwright-report/",
            "*.sqlite3",
            "*.db",
            "the-dial-treasury-v1/data/dashboard.failed.json",
            "the-dial-treasury-v1/content/overrides.json",
        ):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, gitignore)

    def test_archive_readme_marks_output_as_historical_only(self):
        archive_readme = (REPO_ROOT / "archive" / "legacy" / "2026-05-25" / "README.md").read_text(encoding="utf-8")

        self.assertIn("historical QA artifacts", archive_readme)
        self.assertIn("Do not append new runtime artifacts", archive_readme)

    def test_readme_api_list_matches_server_contract(self):
        api_py = APP_ROOT / "treasury_data" / "api.py"
        serve_py = APP_ROOT / "scripts" / "serve.py"
        readme = (APP_ROOT / "README.md").read_text(encoding="utf-8")

        expected_routes = [
            "/api/dashboard",
            "/api/health",
            "/api/curve",
            "/api/decomposition",
            "/api/fed_path",
            "/api/scorecard",
            "/api/policy",
            "/api/auctions",
            "/api/positioning",
            "/api/cross",
            "/api/percentiles",
            "/api/events",
            "/api/news",
            "/api/ideas",
            "/api/source_status",
            "/api/source-status",
            "/api/history",
            "/api/history/snapshots",
            "/api/history/stats",
            "/api/history/series",
            "POST /api/update",
        ]

        api_source = api_py.read_text(encoding="utf-8")
        serve_source = serve_py.read_text(encoding="utf-8")
        for route in expected_routes:
            with self.subTest(route=route):
                self.assertIn(route, readme)
                if route.startswith("/api/history") or route == "POST /api/update":
                    self.assertIn(route.replace("POST ", ""), serve_source)
                else:
                    self.assertIn(route, api_source)

    def test_docs_describe_runtime_boundaries_precisely(self):
        root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        project_status = (REPO_ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")
        app_readme = (APP_ROOT / "README.md").read_text(encoding="utf-8")
        deployment = (REPO_ROOT / "docs" / "treasury-deployment.md").read_text(encoding="utf-8")
        authoring = (REPO_ROOT / "docs" / "treasury-authoring-guide.md").read_text(encoding="utf-8")

        combined = "\n".join([root_readme, project_status, app_readme, deployment, authoring])
        self.assertIn("Direct `file://`", combined)
        self.assertIn("embedded static fallback", combined)
        self.assertNotIn("direct file fallback and smoke checks", combined)
        self.assertIn("CSV export does not apply to `/api/health`,", deployment)
        self.assertIn("warning-severity source errors remain", combined)
        self.assertIn("candidate with core curve, scorecard, and Conditions Score trend content", deployment)


if __name__ == "__main__":
    unittest.main()

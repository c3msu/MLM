import subprocess
import textwrap
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class I18nJsTests(unittest.TestCase):
    def test_translate_and_normalize_language_in_node(self):
        script = textwrap.dedent(
            """
            const i18n = require('./i18n.js');
            if (i18n.normalizeLanguage('en-US') !== 'en') throw new Error('expected en');
            if (i18n.normalizeLanguage('zh-CN') !== 'zh') throw new Error('expected zh');
            if (i18n.translate('en', 'nav.scorecard') !== 'Scorecard') throw new Error('scorecard translation failed');
            if (i18n.translate('zh', 'nav.scorecard') !== '因子计分卡') throw new Error('zh translation failed');
            if (i18n.translate('en', 'missing.key') !== 'missing.key') throw new Error('fallback failed');
            if (i18n.format('en', 'status.live', {asOf: '2026-05-19', generatedAt: 'now', okCount: 36}).indexOf('36 sources') === -1) throw new Error('format failed');
            """
        )

        result = subprocess.run(["node", "-e", script], cwd=PROJECT_ROOT, capture_output=True, text=True)

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

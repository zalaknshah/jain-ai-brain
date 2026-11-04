import shutil
import subprocess
import unittest
from pathlib import Path


class BrowserConsentTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js required for browser script harness")
    def test_learning_consent_is_consumed_once_even_on_failed_request(self):
        harness = Path(__file__).with_name("web_console_harness.js")
        result = subprocess.run(["node", str(harness), "consent"], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

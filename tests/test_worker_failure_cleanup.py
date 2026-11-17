"""Real bounded synthetic subprocess cleanup; no physics/model/corpus access."""
import os
import signal
import subprocess
import sys
import unittest
from unittest.mock import patch

from jace.worker_accounting import run_accounted_worker


@unittest.skipUnless(sys.platform == 'linux' and hasattr(os, 'wait4'), 'Linux wait4 required')
class WorkerFailureCleanupTests(unittest.TestCase):
    def assert_failure_reaped(self, code, expected, patches=()):
        from contextlib import ExitStack
        children = []
        real_popen = subprocess.Popen
        def record(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child
        with ExitStack() as stack:
            stack.enter_context(patch('jace.worker_accounting.subprocess.Popen', side_effect=record))
            for replacement in patches:
                stack.enter_context(replacement)
            with self.assertRaises(expected):
                run_accounted_worker([sys.executable, '-c', code], env={'PATH': os.defpath}, timeout=2)
        self.assertEqual(len(children), 1, 'failure must not retry')
        child = children[0]
        self.assertIsNotNone(child.returncode)
        self.assertTrue(child.stdout.closed)
        self.assertTrue(child.stderr.closed)
        with self.assertRaises(ChildProcessError):
            os.waitpid(child.pid, os.WNOHANG)
        return child.returncode

    def test_capture_overflow_kills_live_writer_and_reaps(self):
        result = self.assert_failure_reaped(
            "import os,time; os.write(1,b'x'*4096); time.sleep(10)", RuntimeError,
            [patch('jace.worker_accounting.MAX_CAPTURE_BYTES', 128)])
        self.assertEqual(result, -signal.SIGKILL)

    def test_selector_setup_failure_cleans_up_started_child(self):
        result = self.assert_failure_reaped('import time; time.sleep(10)', OSError,
            [patch('jace.worker_accounting.os.set_blocking', side_effect=OSError('synthetic setup failure'))])
        self.assertEqual(result, -signal.SIGKILL)

    def test_selector_poll_failure_cleans_up_started_child(self):
        result = self.assert_failure_reaped('import time; time.sleep(10)', OSError,
            [patch('jace.worker_accounting.selectors.EpollSelector.select', side_effect=OSError('synthetic select failure'))])
        self.assertEqual(result, -signal.SIGKILL)

    def test_invalid_utf8_never_becomes_success_and_child_stays_reaped(self):
        self.assertEqual(self.assert_failure_reaped("import os; os.write(1,b'\\xff')", UnicodeDecodeError), 0)

if __name__ == '__main__':
    unittest.main()

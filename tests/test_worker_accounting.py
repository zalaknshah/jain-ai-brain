"""Real synthetic child processes only; no simulator or model dependencies."""
import json
import os
import signal
import subprocess
import sys
import unittest
from unittest.mock import patch

from jace.worker_accounting import run_accounted_worker


@unittest.skipUnless(sys.platform == 'linux' and hasattr(os, 'wait4'), 'Linux wait4 required')
class WorkerAccountingTests(unittest.TestCase):
    def run_child(self, code, timeout=5):
        return run_accounted_worker([sys.executable, '-c', code],
                                    env={'PATH': os.defpath}, timeout=timeout)

    def test_final_cpu_includes_work_after_reporting_sample(self):
        result = self.run_child('''import json, resource, time
usage = resource.getrusage(resource.RUSAGE_SELF)
print(json.dumps({'sample': usage.ru_utime + usage.ru_stime}), flush=True)
start = time.process_time()
while time.process_time() - start < .15: pass
''')
        self.assertEqual(result.returncode, 0)
        self.assertGreater(result.lifetime_cpu_seconds, json.loads(result.stdout)['sample'] + .1)

    def test_both_pipes_are_drained_beyond_pipe_capacity(self):
        result = self.run_child("import os; os.write(1, b'a' * 200000); os.write(2, b'b' * 200000)")
        self.assertEqual(result.stdout, 'a' * 200000)
        self.assertEqual(result.stderr, 'b' * 200000)
        self.assertEqual(result.returncode, 0)

    def test_closed_streams_do_not_skip_waiting_for_child_exit(self):
        result = self.run_child('''import os, time
os.close(1); os.close(2)
start = time.process_time()
while time.process_time() - start < .1: pass
''')
        self.assertEqual(result.returncode, 0)
        self.assertGreater(result.lifetime_cpu_seconds, .09)

    def test_nonzero_and_signal_exit_are_preserved(self):
        self.assertEqual(self.run_child('raise SystemExit(7)').returncode, 7)
        self.assertEqual(self.run_child('import os, signal; os.kill(os.getpid(), signal.SIGKILL)').returncode,
                         -signal.SIGKILL)

    def test_sibling_cpu_is_not_added_and_only_owned_pid_is_waited(self):
        with subprocess.Popen([sys.executable, '-c',
                'import time; start=time.process_time()\nwhile time.process_time()-start < .4: pass']) as sibling:
            with patch('jace.worker_accounting.os.wait4', wraps=os.wait4) as waited:
                result = self.run_child("print('own child')")
            sibling.wait()
        self.assertEqual(result.stdout, 'own child\n')
        self.assertLess(result.lifetime_cpu_seconds, .25)
        pids = {call.args[0] for call in waited.call_args_list}
        self.assertEqual(len(pids), 1)
        self.assertNotIn(sibling.pid, pids)
        self.assertTrue(all(pid > 0 for pid in pids))

    def test_timeout_kills_and_reaps_without_retry_even_after_pipe_close(self):
        real_popen = subprocess.Popen
        for code in ('import time; time.sleep(10)',
                     'import os, time; os.close(1); os.close(2); time.sleep(10)'):
            children = []
            def record(*args, **kwargs):
                process = real_popen(*args, **kwargs)
                children.append(process)
                return process
            with patch('jace.worker_accounting.subprocess.Popen', side_effect=record):
                with self.assertRaises(subprocess.TimeoutExpired):
                    self.run_child(code, timeout=.1)
            self.assertEqual(len(children), 1)
            self.assertEqual(children[0].returncode, -signal.SIGKILL)
            with self.assertRaises(ChildProcessError):
                os.waitpid(children[0].pid, os.WNOHANG)

    def test_output_overflow_is_not_partial_success(self):
        with patch('jace.worker_accounting.MAX_CAPTURE_BYTES', 128):
            with self.assertRaisesRegex(RuntimeError, 'capture limit'):
                self.run_child("import os; os.write(1, b'x' * 1000)")

    def test_unavailable_accounting_and_invalid_timeout_never_spawn(self):
        with patch('jace.worker_accounting.subprocess.Popen') as launch:
            with patch('jace.worker_accounting.os.wait4', None), self.assertRaises(RuntimeError):
                self.run_child('pass')
            for timeout in (0, -1, True, float('nan'), float('inf'), '1'):
                with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                    self.run_child('pass', timeout=timeout)
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()

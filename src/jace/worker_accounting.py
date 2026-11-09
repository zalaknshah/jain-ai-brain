"""Linux direct-child capture with per-PID, post-exit CPU accounting.

Internal launcher utility, not a sandbox or descendant/process-tree accounting.
Only the fixed packaged simulation worker is exposed by the public launcher.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
import selectors
import signal
import subprocess
import sys
import time

MAX_CAPTURE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class AccountedWorker:
    returncode: int
    stdout: str
    stderr: str
    lifetime_cpu_seconds: float


def run_accounted_worker(command: list[str], *, env: dict[str, str], timeout: float) -> AccountedWorker:
    """Drain both pipes and reap exactly this child via wait4, never global usage.

    Do not use Popen.poll/wait/communicate: those may reap the child before its
    final usage can be retrieved. This function exclusively owns the child.
    Timeout, output overflow and accounting errors stop it without a retry.
    """
    if (sys.platform != 'linux' or not callable(getattr(os, 'wait4', None))):
        raise RuntimeError('Linux per-child wait4 accounting is required; no unmeasured fallback is run')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('worker timeout must be finite and positive')
    started = time.monotonic()
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env) as process:
        buffers = {'stdout': bytearray(), 'stderr': bytearray()}
        usage = None
        captured = 0

        def reap(flags: int) -> None:
            nonlocal usage
            try:
                pid, status, observed = os.wait4(process.pid, flags)
            except ChildProcessError:
                # Another reaper makes this result unusable. Never infer success.
                process.returncode = 255
                raise RuntimeError('worker accounting unavailable: child was already reaped') from None
            if pid:
                process.returncode = os.waitstatus_to_exitcode(status)
                usage = observed

        try:
            with selectors.DefaultSelector() as selector:
                for name, stream in (('stdout', process.stdout), ('stderr', process.stderr)):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, name)
                while selector.get_map() or process.returncode is None:
                    if process.returncode is None:
                        reap(os.WNOHANG)
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(command, timeout)
                    if not selector.get_map():
                        if process.returncode is None:
                            time.sleep(min(.01, remaining))
                        continue
                    for key, _ in selector.select(min(.01, remaining)):
                        try:
                            chunk = os.read(key.fd, 65536)
                        except BlockingIOError:
                            continue
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        captured += len(chunk)
                        if captured > MAX_CAPTURE_BYTES:
                            raise RuntimeError('worker output exceeded the 64 MiB capture limit; no success claimed')
                        buffers[key.data].extend(chunk)
            if usage is None:
                raise RuntimeError('worker final CPU accounting is absent; no success claimed')
            return AccountedWorker(process.returncode,
                                   buffers['stdout'].decode('utf-8'), buffers['stderr'].decode('utf-8'),
                                   usage.ru_utime + usage.ru_stime)
        finally:
            # The unreaped direct child's PID cannot be reused. No parent,
            # unrelated child or process group is signalled. Worker code does
            # not create subprocesses; descendant cleanup is not promised.
            if process.returncode is None:
                try:
                    os.kill(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                reap(0)

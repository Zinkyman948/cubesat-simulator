"""Smoke-test a built engine sidecar the way the desktop app drives it.

Starts it with a random port and a token, checks the API (including that a
wrong token is rejected), runs the demo scenario and a lifetime estimate,
then terminates it (what the app does before an update). A second launch,
from an intermediate process that then exits, checks that the engine notices
its parent (the app) is gone and exits by itself.

Usage: python scripts/test_sidecar.py <path-to-simcore-server executable>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

TOKEN = "sidecar-smoke-test"


def process_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie (exited, not yet reaped) still "exists"; check its state.
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


# Run by the parent-watchdog check: start the engine, report its PID, exit.
LAUNCHER = """
import subprocess, sys
p = subprocess.Popen([sys.argv[1], "serve", "--port", "0", "--exit-with-parent"],
                     stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True)
print(p.stdout.readline().strip(), p.pid, flush=True)
"""


def launch(exe: str) -> tuple[subprocess.Popen, int]:
    start = time.time()
    proc = subprocess.Popen(
        [exe, "serve", "--port", "0", "--exit-with-parent"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        # Stack dumps if the engine gets stuck, so CI logs show where.
        env={**os.environ, "SIMCORE_TOKEN": TOKEN, "SIMCORE_DEBUG_HANG_S": "45"},
    )
    line = proc.stdout.readline().strip()
    assert line.startswith("SIMCORE_READY port="), f"unexpected first line: {line!r}"
    port = int(line.split("=", 1)[1])
    print(f"ready on port {port} after {time.time() - start:.1f} s")

    # Keep draining stdout like the desktop app does: an unread pipe fills up
    # (4 KB on Windows) and then blocks the engine on its next write.
    def echo():
        for out in proc.stdout:
            print(f"[engine] {out.rstrip()}", flush=True)

    threading.Thread(target=echo, daemon=True).start()
    return proc, port


def main() -> None:
    exe = sys.argv[1]
    # Native-model checks first, on the main thread, with their output visible.
    check = subprocess.run([exe, "selftest"], capture_output=True, text=True, timeout=180)
    print(check.stdout + check.stderr)
    assert check.returncode == 0, "selftest failed"

    proc, port = launch(exe)

    def call(path: str, body: dict | None = None, token: str = TOKEN):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"X-Simcore-Token": token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None

    assert call("/api/health")[0] == 200
    assert call("/api/health", token="wrong")[0] == 401
    examples = [e["id"] for e in call("/api/examples")[1]]
    assert "sso_3u_demo" in examples, examples

    scenario = call("/api/examples/sso_3u_demo")[1]["yaml"]
    t = time.time()
    status, result = call("/api/simulate", {"yaml": scenario})
    assert status == 200, status
    passes = {name: len(p) for name, p in result["passes"].items()}
    assert passes["Svalbard"] > 0, passes
    print(f"simulated in {time.time() - t:.1f} s: {passes}, {len(result['link_passes'])} link passes")

    t = time.time()
    status, life = call("/api/lifetime", {"yaml": scenario, "max_years": 25})
    assert status == 200 and life["reentered"], (status, life and life.get("notes"))
    print(f"lifetime in {time.time() - t:.1f} s: re-entry after {life['lifetime_days'] / 365.25:.2f} years")

    t = time.time()
    proc.terminate()
    proc.wait(timeout=30)
    print(f"stopped {time.time() - t:.1f} s after terminate")

    # Parent watchdog: the launcher exits right after the engine is ready.
    launcher = subprocess.run([sys.executable, "-c", LAUNCHER, exe], capture_output=True, text=True, timeout=120)
    words = launcher.stdout.split()  # "SIMCORE_READY port=<n> <pid>"
    assert words and words[0] == "SIMCORE_READY", launcher.stdout + launcher.stderr
    pid = int(words[-1])
    deadline = time.time() + 15
    while process_alive(pid) and time.time() < deadline:
        time.sleep(0.2)
    assert not process_alive(pid), "engine kept running after its parent exited"
    print("exited by itself after its parent exited")
    print("sidecar OK")


if __name__ == "__main__":
    main()

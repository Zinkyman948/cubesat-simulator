"""Smoke-test a built engine sidecar the way the desktop app drives it.

Starts it with a random port and a token, checks the API (including that a
wrong token is rejected), runs the demo scenario, then closes stdin and
expects the process to exit.

Usage: python scripts/test_sidecar.py <path-to-simcore-server executable>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

TOKEN = "sidecar-smoke-test"


def main() -> None:
    exe = sys.argv[1]
    start = time.time()
    proc = subprocess.Popen(
        [exe, "serve", "--port", "0", "--exit-on-stdin-close"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        env={**os.environ, "SIMCORE_TOKEN": TOKEN},
    )
    line = proc.stdout.readline().strip()
    assert line.startswith("SIMCORE_READY port="), f"unexpected first line: {line!r}"
    port = int(line.split("=", 1)[1])
    print(f"ready on port {port} after {time.time() - start:.1f} s")

    def call(path: str, body: dict | None = None, token: str = TOKEN):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"X-Simcore-Token": token, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
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

    proc.stdin.close()
    proc.wait(timeout=30)
    print(f"exited with code {proc.returncode} after stdin closed")
    assert proc.returncode == 0
    print("sidecar OK")


if __name__ == "__main__":
    main()

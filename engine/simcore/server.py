"""Local HTTP API used by the desktop app (and a future web demo).

The desktop shell launches `simcore serve --port 0`, reads the
`SIMCORE_READY port=<n>` line from stdout, and sends every request with the
per-launch token from the SIMCORE_TOKEN environment variable.
"""

from __future__ import annotations

import hmac
import json
import os
import sys
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from simcore import __version__, simulation
from simcore.scenario import Scenario

TOKEN_HEADER = "X-Simcore-Token"

# Tauri serves the frontend from these origins (Windows uses http(s)://tauri.localhost);
# 1420 is the Vite dev server.
ALLOWED_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
]


def default_examples_dir() -> Path:
    """Example scenarios: bundled next to the frozen executable, else the repo copy."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "scenarios"
    return Path(__file__).resolve().parents[2] / "scenarios"


class SimulateRequest(BaseModel):
    yaml: str


# Tags pydantic inserts into error locations for discriminated unions
# (orbit -> keplerian/tle); they are not keys in the scenario document.
_UNION_TAGS = {"keplerian", "tle"}


def _issue(err: dict) -> dict:
    """A validation error with its location as a document path, e.g.
    ["ground_stations", 0, "latitude_deg"], for matching to form fields."""
    path = [p for p in err["loc"] if p not in _UNION_TAGS]
    msg = err["msg"].removeprefix("Value error, ")
    return {"loc": ".".join(str(p) for p in path) or "scenario", "path": path, "msg": msg}


def _validation_error(errors: list[dict]) -> JSONResponse:
    return JSONResponse(status_code=422, content={"errors": errors})


def create_app(token: str | None = None, examples_dir: Path | None = None) -> FastAPI:
    examples = examples_dir or default_examples_dir()
    app = FastAPI(title="simcore", version=__version__)

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        if token and request.method != "OPTIONS":
            supplied = request.headers.get(TOKEN_HEADER, "")
            if not hmac.compare_digest(supplied, token):
                return JSONResponse(status_code=401, content={"detail": "invalid token"})
        return await call_next(request)

    # Added last so it wraps the token check and answers CORS preflights itself.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", TOKEN_HEADER],
    )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    @app.get("/api/examples")
    def list_examples():
        out = []
        for path in sorted(examples.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            out.append({"id": path.stem, "name": data.get("name", path.stem),
                        "description": data.get("description", "")})
        return out

    @app.get("/api/examples/{example_id}")
    def get_example(example_id: str):
        path = examples / f"{example_id}.yaml"
        # Only plain names that resolve inside the examples directory.
        if path.parent.resolve() != examples.resolve() or not path.is_file():
            raise HTTPException(status_code=404, detail="unknown example")
        return {"id": example_id, "yaml": path.read_text(encoding="utf-8")}

    def parse_scenario(text: str) -> Scenario | JSONResponse:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            return _validation_error([{"loc": "yaml", "path": [], "msg": str(e)}])
        if not isinstance(data, dict):
            return _validation_error(
                [{"loc": "yaml", "path": [], "msg": "scenario must be a YAML mapping"}]
            )
        try:
            return Scenario.model_validate(data)
        except ValidationError as e:
            return _validation_error([_issue(err) for err in e.errors()])

    @app.post("/api/validate")
    def validate(req: SimulateRequest):
        """Check a scenario without running it (live form feedback).

        Always 200: problems in the scenario are the answer, not a failure.
        """
        parsed = parse_scenario(req.yaml)
        if isinstance(parsed, JSONResponse):
            return JSONResponse(content=json.loads(parsed.body))
        return {"errors": []}

    @app.post("/api/simulate")
    def simulate(req: SimulateRequest):
        parsed = parse_scenario(req.yaml)
        if isinstance(parsed, JSONResponse):
            return parsed
        result = simulation.run(parsed)
        out = result.to_dict(include_ephemeris=True)
        # The app only needs the ground track; drop the inertial state vectors.
        for key in ("r_gcrs_km", "v_gcrs_km_s"):
            out["ephemeris"].pop(key)
        return out

    return app


def serve(host: str = "127.0.0.1", port: int = 0, exit_on_stdin_close: bool = False) -> None:
    """Run the API, announcing the bound port on stdout once listening."""
    import socket
    import threading

    import uvicorn

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform != "win32":
        # Allow an immediate restart on the same port while old connections
        # sit in TIME_WAIT. (On Windows this option would let other processes
        # take over the port, and isn't needed for restarts.)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(128)  # accept (queue) connections before uvicorn starts serving
    bound_port = sock.getsockname()[1]

    if exit_on_stdin_close:
        # The desktop shell holds our stdin open. EOF means it is gone, so
        # don't linger as an orphan; an "exit" line is a deliberate stop
        # (e.g. before an update replaces this executable).
        def watch_stdin():
            for line in sys.stdin:
                if line.strip() == "exit":
                    break
            os._exit(0)

        threading.Thread(target=watch_stdin, daemon=True).start()

    token = os.environ.get("SIMCORE_TOKEN") or None
    config = uvicorn.Config(create_app(token=token), log_level="warning")
    server = uvicorn.Server(config)

    print(f"SIMCORE_READY port={bound_port}", flush=True)
    server.run(sockets=[sock])

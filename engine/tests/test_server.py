import pytest
from fastapi.testclient import TestClient

from simcore.server import TOKEN_HEADER, create_app


@pytest.fixture
def client(scenarios_dir):
    return TestClient(create_app(examples_dir=scenarios_dir))


def _example(client, example_id):
    return client.get(f"/api/examples/{example_id}").json()["yaml"]


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_list_and_fetch_examples(client):
    ids = {e["id"] for e in client.get("/api/examples").json()}
    assert {"sso_3u_demo", "iss_tle_sgp4"} <= ids
    assert "propagator: j2" in _example(client, "sso_3u_demo")


@pytest.mark.parametrize("bad", ["nope", "..%2Fpyproject", "..%2F..%2FREADME"])
def test_unknown_or_escaping_example_is_404(client, bad):
    assert client.get(f"/api/examples/{bad}").status_code == 404


def test_simulate_returns_passes_links_and_ground_track(client):
    text = _example(client, "sso_3u_demo").replace("duration_hours: 24", "duration_hours: 3")
    r = client.post("/api/simulate", json={"yaml": text})
    assert r.status_code == 200
    out = r.json()
    assert set(out["passes"]) == {"Svalbard", "Boulder", "Singapore"}
    eph = out["ephemeris"]
    assert len(eph["latitude_deg"]) == len(eph["utc"]) > 100
    assert "r_gcrs_km" not in eph
    assert out["link_passes"] and "margin_db" in out["link_passes"][0]["series"]


def test_simulate_reports_validation_errors(client):
    text = _example(client, "sso_3u_demo").replace("inclination_deg: 97.4", "inclination_deg: 200")
    r = client.post("/api/simulate", json={"yaml": text})
    assert r.status_code == 422
    assert any("inclination_deg" in e["loc"] for e in r.json()["errors"])


@pytest.mark.parametrize("text", ["name: [unclosed", "just a string"])
def test_simulate_rejects_bad_yaml(client, text):
    r = client.post("/api/simulate", json={"yaml": text})
    assert r.status_code == 422 and r.json()["errors"][0]["loc"] == "yaml"


def test_token_required_when_configured(scenarios_dir):
    client = TestClient(create_app(token="s3cret", examples_dir=scenarios_dir))
    assert client.get("/api/health").status_code == 401
    assert client.get("/api/health", headers={TOKEN_HEADER: "wrong"}).status_code == 401
    assert client.get("/api/health", headers={TOKEN_HEADER: "s3cret"}).status_code == 200


def test_cors_preflight_from_tauri_origin(scenarios_dir):
    client = TestClient(create_app(token="s3cret", examples_dir=scenarios_dir))
    r = client.options("/api/simulate", headers={
        "Origin": "http://tauri.localhost",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": f"content-type,{TOKEN_HEADER.lower()}",
    })
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://tauri.localhost"

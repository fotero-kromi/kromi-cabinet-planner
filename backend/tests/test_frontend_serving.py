"""The back end serves the built front end (frontend/dist) next to the API, so
one server on one port is the whole app (the Docker image, port 8080)."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from kromi_api import config
from kromi_api.main import create_app

INDEX = "<!doctype html><title>planner page</title>"


@pytest.fixture
def dist(tmp_path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX, encoding="utf-8")
    (tmp_path / "assets" / "index-abc.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    return tmp_path


def _client(session_factory, frontend_dir):
    return TestClient(create_app(session_factory=session_factory, frontend_dir=frontend_dir))


def test_the_page_and_its_files_are_served(session_factory, dist):
    with _client(session_factory, dist) as c:
        page = c.get("/")
        assert page.status_code == 200 and "planner page" in page.text
        assert page.headers["content-type"].startswith("text/html")
        js = c.get("/assets/index-abc.js")
        assert js.status_code == 200 and "javascript" in js.headers["content-type"]
        assert c.get("/favicon.svg").status_code == 200


def test_the_api_keeps_its_answers(session_factory, dist):
    with _client(session_factory, dist) as c:
        assert c.get("/api/v1/health").json()["status"] == "ok"
        missing = c.get("/api/v1/no-such-endpoint")
        assert missing.status_code == 404 and missing.json() == {"detail": "Not Found"}


def test_no_file_outside_the_build_is_served(session_factory, dist):
    (dist.parent / "secret.txt").write_text("secret", encoding="utf-8")
    with _client(session_factory, dist) as c:
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
            r = c.get(path)
            assert "secret" not in r.text, path


def test_without_a_build_only_the_api_runs(session_factory, tmp_path):
    with _client(session_factory, tmp_path / "missing") as c:
        assert c.get("/").status_code == 404
        assert c.get("/api/v1/health").status_code == 200


def test_the_build_folder_is_configurable(monkeypatch, tmp_path):
    monkeypatch.setenv("KROMI_FRONTEND_DIR", str(tmp_path))
    assert config.frontend_dir() == tmp_path
    monkeypatch.delenv("KROMI_FRONTEND_DIR")
    assert config.frontend_dir() == Path(config.__file__).resolve().parents[2] / "frontend" / "dist"

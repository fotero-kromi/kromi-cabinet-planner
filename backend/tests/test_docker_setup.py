"""The Docker setup the owner starts with one command (docs/New_App_Docker.md):
the owner decisions of 2026-09-23 as checks on compose.yaml, the image recipe
and what may enter the image."""
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def _compose() -> dict:
    return yaml.safe_load((REPO / "compose.yaml").read_text(encoding="utf-8"))


def _dockerfile() -> str:
    return (REPO / "docker" / "Dockerfile").read_text(encoding="utf-8")


def test_a_fixed_project_name_keeps_the_data_wherever_the_folder_is():
    assert _compose()["name"] == "kromi-planner"


def test_postgresql_18_keeps_its_data_in_a_named_volume_and_is_not_published():
    db = _compose()["services"]["db"]
    assert db["image"] == "postgres:18"  # major 18, its newest minor release
    assert "ports" not in db
    # postgres:18 keeps its data below /var/lib/postgresql (in a folder per major).
    assert db["volumes"] == ["db-data:/var/lib/postgresql"]
    assert "db-data" in _compose()["volumes"]
    assert "pg_isready" in str(db["healthcheck"]["test"])


def test_the_app_is_reachable_from_this_pc_only_on_port_8080():
    app = _compose()["services"]["app"]
    assert app["ports"] == ["127.0.0.1:8080:8080"]
    assert app["depends_on"] == {"db": {"condition": "service_healthy"}}
    assert app["build"] == {"context": ".", "dockerfile": "docker/Dockerfile"}
    assert "@db:5432/" in app["environment"]["KROMI_DATABASE_URL"]
    assert "/api/v1/health" in str(app["healthcheck"]["test"])


def test_both_services_restart_with_docker():
    for service in _compose()["services"].values():
        assert service["restart"] == "unless-stopped"


def test_the_image_builds_the_front_end_and_runs_python_3_12():
    text = _dockerfile()
    stages = re.findall(r"^FROM\s+(\S+)(?:\s+AS\s+(\w+))?", text, flags=re.M)
    assert stages[0] == ("node:22-slim", "frontend")
    assert stages[-1][0] == "python:3.12-slim"
    assert "npm ci" in text and "npm run build" in text
    assert "COPY --from=frontend /build/frontend/dist" in text


def test_the_image_carries_only_the_new_app():
    final = _dockerfile().rsplit("FROM ", 1)[1]
    sources = {line.split()[1] for line in final.splitlines()
               if line.startswith("COPY") and "--from" not in line}
    assert sources <= {"backend/requirements.txt", "engine/", "backend/", "docker/entrypoint.sh"}
    assert re.search(r"^USER\s+(?!root)\w+", final, flags=re.M), "runs as a non-root user"
    assert re.search(r"^EXPOSE\s+8080$", final, flags=re.M)


def test_the_start_migrates_the_database_first():
    script = (REPO / "docker" / "entrypoint.sh").read_text(encoding="utf-8")
    assert script.index("alembic") < script.index("uvicorn")
    assert "upgrade head" in script and "exec " in script and "--port 8080" in script
    assert "set -e" in script


def test_no_customer_file_or_secret_enters_the_build():
    ignored = (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for pattern in ("**/*.xlsx", "**/*.xls", "**/*.csv", "**/.env", "runs/", "**/node_modules",
                    ".git"):
        assert pattern in ignored, pattern


def test_scripts_keep_unix_line_endings_on_windows():
    attributes = (REPO / ".gitattributes").read_text(encoding="utf-8").splitlines()
    for rule in ("*.sh text eol=lf", "Dockerfile text eol=lf"):
        assert rule in attributes, rule

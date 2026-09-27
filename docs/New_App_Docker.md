# The new app with Docker on a Windows PC

The new app (branch `rewrite/fastapi-react`) runs in two containers: the app
itself and its PostgreSQL database. One command starts both; the browser opens
it at http://localhost:8080. The Streamlit app is not affected and can run at
the same time.

## What it is, and what it is not

- A prototype: upload, column mapping, the Standard operation mode, results and
  the result workbook. The other operation modes, AI, corrections and reopening
  an earlier run are not in it yet (`docs/Rewrite_Decision.md`).
- Reachable from this PC only (address 127.0.0.1). There is no login yet, so
  never change `127.0.0.1` in `compose.yaml` to make it reachable from the
  network.
- Uploaded workbooks and results are stored in the database volume on this PC.
  There is no backup yet; `docker compose down -v` deletes them for good.

## One-time setup

You need Windows 10 or 11 with WSL2 (Windows Subsystem for Linux, version 2)
and administrator rights for the installation. Install one of the two:

**Docker Desktop.** Free only for companies below 250 employees and 10 million
USD revenue; check the licence with IT first. Install it with the WSL2 option,
start it once and wait until it shows "Engine running".

**Rancher Desktop.** Free (Apache 2.0 licence). Install it, then open
Preferences:

- Container Engine: choose **dockerd (moby)**. The commands below need it.
- Kubernetes: switch it off; the app does not need it and it uses memory.

Check in PowerShell that it works:

```powershell
docker compose version
```

## Get the app

With git:

```powershell
git clone https://github.com/fotero-kromi/kromi-cabinet-planner.git kromi-new-app
cd kromi-new-app
git checkout rewrite/fastapi-react
```

Without git: on GitHub, switch to the branch `rewrite/fastapi-react`, choose
Code, then Download ZIP, and unpack it. Open PowerShell in the unpacked folder
(the one that contains `compose.yaml`).

## Everyday commands

Run them in PowerShell, in the folder that contains `compose.yaml`.

| What | Command |
|---|---|
| Start (the first start builds the app and downloads about 1.5 GB; later starts take seconds) | `docker compose up -d --build` |
| Open the app | http://localhost:8080 |
| See whether it runs | `docker compose ps` (both lines should say "healthy") |
| See the app's messages | `docker compose logs app` |
| Stop (data kept) | `docker compose down` |
| Update | `git pull` (or unpack the newer ZIP into the same folder), then `docker compose up -d --build`. The database is updated automatically on start; your data is kept. |
| Delete everything, data included | `docker compose down -v` (only when you mean it) |

Both containers restart with Docker: after a PC restart the app is back once
Docker Desktop or Rancher Desktop has started.

The data belongs to the project name `kromi-planner` (fixed in `compose.yaml`),
not to the folder: unpacking a newer ZIP into another folder and starting it
there uses the same database.

## When something does not work

- **"port is already allocated"**: another program uses port 8080. Stop it, or
  change the first number in `compose.yaml` (`"127.0.0.1:8081:8080"`) and open
  http://localhost:8081.
- **"Cannot connect to the Docker daemon" or "docker: command not found"**:
  Docker Desktop or Rancher Desktop is not running; start it and wait until the
  engine is ready. With Rancher Desktop, check that the container engine is
  dockerd (moby).
- **The page says "Server not reachable"**: run `docker compose ps`. If the
  app is not "healthy", `docker compose logs app` shows why; send that text
  when asking for help.
- **The first start stops with a download error**: the company network may
  block the download servers. Ask IT to allow Docker Hub
  (`registry-1.docker.io`, `auth.docker.io`, `production.cloudflare.docker.com`),
  the Python packages (`pypi.org`, `files.pythonhosted.org`) and the front-end
  packages (`registry.npmjs.org`).

## For the record

- The database is PostgreSQL 18 (image `postgres:18`, its newest minor
  release). It is not reachable from outside Docker; its password matters only
  for a central server later. To choose another one, set `KROMI_DB_PASSWORD`
  (letters and digits) before the very first start.
- The image is built from `docker/Dockerfile`: the front end is built with
  Node 22, the app runs on Python 3.12 as a non-root user. Customer files
  (`.xlsx`, `.xls`, `.csv`), `.env` and runtime folders never enter the image
  (`.dockerignore`).
- CI builds and starts exactly this setup on every change and runs a browser
  through the synthetic standard scenario; the downloaded workbook must be
  identical to the Streamlit app's (`e2e/test_new_app.py`).

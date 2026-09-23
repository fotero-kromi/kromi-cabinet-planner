# Rewrite without Streamlit - decision record

Date: 2026-09-23. Status: the owner decided to prototype a rewrite on a branch
(`rewrite/fastapi-react`) and confirmed the stack, the database and where it
runs (owner decisions below). The vertical slice is in progress.

## Why

Streamlit reruns the whole page on every click. That model is why the planner
page grew to one 4,700-line script with 647 shared names, why state lives in
module globals, session keys and caches at once, and why every extraction
produced functions with dozens of parameters
(`docs/Code_Professionalization_Plan.md`). Trimming inside Streamlit has been
tried several times without changing the pattern.

## Recommendation

**FastAPI back end + React/TypeScript front end, API-first, around the existing
engine.** Streamlit stays in production on `main` until the new app gives the
same results.

| Option | Verdict |
|---|---|
| FastAPI + React/TS | Recommended. The network boundary between UI and logic makes a new big block structurally impossible; the TypeScript client is generated from the OpenAPI schema, so the two sides cannot drift; largest ecosystem, any developer or IT department can take it over. |
| NiceGUI | Fallback if speed matters most: Python only, event-driven, runs on FastAPI, about 60 % of the effort. UI state lives in the server process per browser tab (lost on restart, one server only), and UI and logic tend to merge again. |
| Reflex | Reported build and state problems; not for a business tool yet. |
| Dash, Panel, Shiny | Built for dashboards. This app is a workflow (mapping wizard, about 60 controls, corrections, run restore); their callback or reactive models get tangled with that much state. |
| HTMX / FastHTML, Taipy, Solara, Mesop, Flet | Editable grids are awkward, or the community is small. |

## Target architecture

- `engine/` shared by both apps, with its tests. Page logic the new app needs
  moves into the engine through releases on `main` first; nothing is copied.
- Service layer: a typed settings object replaces about 100 session-state keys;
  restoring a run becomes "load the stored settings"; the orchestration now in
  the page moves here.
- API: FastAPI + Pydantic v2. Upload and column inspection, runs, corrections
  (sizes, overrides, programs), exports (workbook, takeover, article setup), run
  history.
- Plan runs execute in the background with their status in the database (the
  job table); the browser polls it. A separate worker process can take over
  later.
- Front end: React, TypeScript, Vite; AG Grid Community for editable tables;
  Mantine for forms; TanStack Query; client generated from the OpenAPI schema.
- Database: PostgreSQL only (the Streamlit app keeps SQLite until it is
  replaced). Microsoft sign-in when central.
- Docker: the app image and PostgreSQL started by one `docker compose` command;
  CI runs pytest, front-end tests, browser end-to-end tests and the parity
  oracle.

## Parity oracle

The synthetic scenarios (`tools/synthetic_golden.py`) sent through the new app
must give exactly what the Streamlit app gives, as recorded in
`tests/golden/synthetic_manifest.json`:

- `workbook`: every cell of every sheet of the exported workbook (the build,
  timestamp and AI model rows left out);
- `plan_result`: the planner's own result (article rows, bucket plans, grand
  totals, restock, bulk routing, overrides, validation, consolidation log),
  recorded from the Streamlit run. Unlike the older plan-table digests it does
  not depend on the SQLite archive's layout. The new app must match it straight
  from the service and again after storing the result in PostgreSQL and
  reading it back.

Each scenario joins the new app's parity tests when its screen is built; the
rewrite is at parity when all four match. A change on `main` that changes
results updates the manifest there (`--update`); after the merge into this
branch, the new app's parity tests fail until the new app gives the same
result, and `plan_result` is regenerated with `--update` on this branch.

## Plan

1. Vertical slice: upload, mapping, standard run, results grid, workbook
   download, matching the `standard` scenario. Go / no-go point.
   - Preparation on `main`: v34.61 (tool list, export tables, setting
     defaults) and v34.62 (column suggestions, run settings) moved the page
     logic the slice needs into the engine, byte-identical.
   - PR A: back end (service layer, PostgreSQL, API) and the parity oracle.
   - PR B: front end (screens, generated client, unit tests).
   - PR C: Docker setup and browser end-to-end tests.
2. Screen by screen to parity. Engine fixes ship from `main` and reach the branch
   by merge.

Page logic still to move into the engine with the next release on `main`:
which sheet is preselected as the Tools sheet (the first sheet whose name
contains tool, werkzeug, outil or herramienta). Until then the new app
preselects no sheet; the user picks it, and results do not depend on it.

Effort (AI-assisted working days): service layer and typed settings 5 to 7 (needed
by either stack); FastAPI + React about 28 to 37 in total; NiceGUI about 19 to 25.

## Owner decisions (2026-09-23)

1. Stack: FastAPI + React/TypeScript (Vite), API-first; the TypeScript client
   is generated from the OpenAPI schema.
2. Database: PostgreSQL for the new app (SQLAlchemy 2, Alembic, psycopg 3). No
   SQLite in the new app; the Streamlit app on main keeps SQLite until it is
   replaced. Major version 18, pinned by the image tag `postgres:18` (it
   follows 18's newest minor release, never a fresh .0 of a new major).
3. Tests run against a real PostgreSQL, never a SQLite stand-in: a PostgreSQL
   18 service container in CI (the reference) and the PostgreSQL installed in
   cloud sessions (16 is acceptable there).
4. Hosting direction: a central server (app + PostgreSQL). Microsoft login
   later; the slice runs without login, reachable from the PC it runs on only.
   The owner tries the prototype with Docker on a Windows PC: one
   `docker compose` command starts everything, the browser opens port 8080.
   The instructions work with Docker Desktop and Rancher Desktop (the licence
   is being checked with IT).
5. No import of the old SQLite history: the new app starts with an empty
   database.
6. The engine is reused and stays pure. No page logic is copied into the new
   app: what it needs moves into the engine by a release on `main` first
   (byte-identical, with the real-file check before merging).
7. Parity: the new plan-result fingerprint is added to the manifest,
   generated from the Streamlit app.
8. The slice is delivered in three PRs into `rewrite/fastapi-react`: A back
   end and parity, B front end, C Docker and end-to-end tests.

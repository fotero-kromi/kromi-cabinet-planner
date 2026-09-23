# Rewrite without Streamlit - decision record

Date: 2026-09-23. Status: the owner decided to prototype a rewrite on a branch
(`rewrite/fastapi-react`). The stack below is the recommendation; the owner
confirms it, and where the app runs, before the vertical slice starts.

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

- `engine/` unchanged, with its tests.
- Service layer: a typed settings object replaces about 100 session-state keys;
  restoring a run becomes "load the stored settings"; the orchestration now in
  the page moves here.
- API: FastAPI + Pydantic v2. Upload and column inspection, runs, corrections
  (sizes, overrides, programs), exports (workbook, takeover, article setup), run
  history.
- Plan runs execute in a worker process with progress reported to the browser; a
  small job table in the database is enough at this user count.
- Front end: React, TypeScript, Vite; AG Grid Community for editable tables;
  TanStack Query; client generated from the OpenAPI schema.
- Database: SQLite locally, Postgres on a server. Microsoft sign-in if central.
- One Docker image; CI runs pytest, front-end tests, browser end-to-end tests and
  the synthetic golden gate.

## Parity oracle

The four synthetic scenarios (`tools/synthetic_golden.py`) sent through the new
API must produce the same digests as `tests/golden/synthetic_manifest.json`. That
proves the rewrite changes no result.

## Plan

1. Vertical slice (4 to 5 days): upload, mapping, standard run, results grid,
   workbook download, matching the `standard` scenario. Go / no-go point.
2. Screen by screen to parity. Engine fixes ship from `main` and reach the branch
   by merge.

Effort (AI-assisted working days): service layer and typed settings 5 to 7 (needed
by either stack); FastAPI + React about 28 to 37 in total; NiceGUI about 19 to 25.

## Open decisions (owner)

1. Stack: FastAPI + React (recommended) or NiceGUI.
2. Where it runs: a central server with Microsoft sign-in (recommended when more
   than one planner uses it) or on each user's PC.

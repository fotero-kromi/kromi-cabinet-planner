# New app: front end

React + TypeScript (Vite), Mantine for forms, AG Grid Community for tables,
TanStack Query for server data. The API client's types are generated from the
back end's OpenAPI schema. Background and decisions: `docs/Rewrite_Decision.md`.

## Run it (development)

Needs Node 22 and the back end with its PostgreSQL (see `CLAUDE.md`).

```bash
python -m uvicorn --app-dir backend kromi_api.main:app   # API on port 8000 (repository root)
cd frontend
npm ci                                                   # packages from the lock file
npm run dev                                              # http://127.0.0.1:5173, forwards /api to port 8000
```

## Checks

```bash
npm run lint        # ESLint
npm run typecheck   # TypeScript
npm test            # Vitest (happy-dom, API stand-in with MSW)
npm run build       # production build into dist/
```

`python tools/check_new_app.py` runs these and the back-end checks, as CI does.

## After an API change

```bash
python tools/export_openapi.py   # repository root: writes frontend/openapi.json
cd frontend && npm run gen:api   # regenerates src/api/schema.d.ts
```

Commit both files. A back-end test fails while `openapi.json` is stale, and
the CI front-end job fails while `schema.d.ts` differs from it.

## Layout

- `src/api/`: the generated schema types and the client (`client.ts`).
- `src/lib/`: plain functions with tests.
  - `settingFields.ts`: one description per setting (kind, label, help, group,
    advanced or not, the operation modes that hide it, when it shows). The
    settings form is rendered from it; `NOT_ON_FORM` lists the settings it
    leaves out, with the reason.
  - `settings.ts`, `mapping.ts`, `run.ts`, `upload.ts`: defaults, checks and
    the run request.
- `src/components/`: small reusable pieces, each for one job.
  - `settings/`: `SettingsForm` renders any list of setting descriptions;
    `SettingInput` renders one by its kind.
  - `upload/FileDrop`, `mapping/` (`SheetPicker`, `DataPreview`, `MappingGrid`,
    `MappingProblems`), `results/` (`Totals`, `IssueList`, `BucketTable`,
    `ArticleTable`, `RunStatus`), `DataGrid`, `ErrorAlert`.
- `src/steps/`: the four screens; each wires its components to the API.
- `src/test/`: test setup, API stand-in and fixtures.

To add a setting to the form: add its description to `SETTING_FIELDS` (the
tests check that it names a real setting of the right type), or list it in
`NOT_ON_FORM` with the reason.

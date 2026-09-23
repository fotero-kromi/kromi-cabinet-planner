# Kromi Cabinet Planner

A Streamlit application that sizes vending/storage cabinets (Helix spiral
machines, Carousel slot machines, and Lockers A/B/C) for industrial tooling
catalogs. Given a customer's article list and consumption data, it classifies
each article, decides how it should be stored, and reports how many cabinets of
each type are required — per supply point. It exports a multi-sheet Excel
workbook (clean by default, with optional technical/audit sheets and a cabinet
planogram) and a KROMI-branded PowerPoint deck.

## Architecture

The codebase is split into a thin UI layer and a independently testable engine.

```
kromi_app/
├── Home.py                  # Streamlit entry point (picker)
├── run.bat                  # Windows launcher (dependency sync + start)
├── presentation.py          # KROMI .pptx deck renderer (python-pptx; consumes engine/deck)
├── styling.py               # shared theming
├── optimization.py          # experimental PuLP comparison (diagnostics only)
├── pages/
│   ├── 1_Kromi_Planner.py   # main planner page (input, mapping, run, results)
│   └── 2_EGC_Planner.py     # specification preview page
├── ui/                      # Streamlit panels: exports, technician review, AI calls
├── engine/                  # pure logic: no Streamlit imports (guarded by a test)
├── db/                      # SQLite store, migrations, run persistence, override sets
├── tools/                   # golden/export capture, release packager, dependency sync
├── assets/                  # logo + machine renders used by the presentation deck
├── tests/                   # pytest suite
├── requirements.txt         # runtime dependencies
├── requirements-dev.txt     # + test, lint and type tools
└── pyproject.toml           # pytest, ruff and mypy configuration
```

### Design principles

- **Engine / UI separation.** All planning math and classification lives in
  `engine/`. The Streamlit pages orchestrate input, call the engine, and render
  output (tables, charts, Excel workbook). Engine functions never import Streamlit.
- **No global state in the engine.** Functions that need a working directory or
  a runtime-adjustable factor take it as an argument. The UI passes current
  values in through thin wrappers, which keeps every engine function pure and
  unit-testable.
- **Deterministic classifier first, AI as fallback.** Article classification is
  driven by a multilingual keyword/pattern engine aligned to the Kromi product
  taxonomy. The optional LLM call is only reached for the small remainder the
  deterministic path can't resolve, which keeps cost and latency low. On
  representative catalogs the deterministic path resolves ~96–100% of rows.
- **Every output declares its build.** `engine/build_info.BUILD` is the single
  source of truth for the build label, stamped onto the Streamlit sidebar, the
  Excel `Run_Metadata` sheet and every deck slide's
  date footer. A guard test fails if any source file outside `build_info.py`
  hard-codes a `"vNN"` literal, so two outputs can never disagree on which
  build produced them.
- **Output filenames are meaningful.** Exports are named
  `CPlanner_<source>_<type>_<date>.<ext>` (e.g. `CPlanner_<catalog>_Result_<YYYY-MM-DD>.xlsx`)
  so a file announces what it is and when it was produced without opening it.
- **Every plan self-verifies.** `engine/invariants.py` runs conservation and
  consistency checks on the final plan (routing partition, pack/coverage/sizing
  validity, the Target_packs and Monthly_packs arithmetic identities,
  consumption conservation through filtering/dedup and supply-point assignment,
  KROMI-number uniqueness, and export-sheet reconciliation). A violation is
  surfaced to the user before the workbook is used, so a future change that
  breaks an invariant fails loudly on the next run instead of shipping a wrong
  plan.

## Engine module map

One line per module, taken from the module docstrings; `engine/` is pure
(no Streamlit imports), and the page composes it.

| Module | Purpose |
|---|---|
| `plan.py` | Composition layer: the deterministic `run_plan(work, overrides, params)` pipeline |
| `tool_list.py` | Building the tool list from the mapped sheets: mapping check, renaming, blank codes, supply points, classification columns |
| `planning_defaults.py` | The setting defaults and choice labels every front end reads |
| `preprocessing.py` | Planning base prep: dedup, year filter, pack units, restock flag normalization |
| `boundary.py` | Deterministic boundary heuristics between preprocessing and the plan |
| `demand.py` | Demand arithmetic and the base KTC/Kanban routing decision |
| `routing_rules.py` | Per-tool-family routing and sizing rules |
| `sizing.py` | Sizing orchestration: assigning each row to a cabinet type |
| `cabinet_math.py` | Cabinet sizing math, the carousel cap, and the rebalancer |
| `fixed_config.py` | The fixed-configuration mode: fitting the articles into machines that already exist |
| `takeover.py` | The takeover sheets: per supply point, the customer's stock split into the KTC (up to the article's maximum) and the HLO |
| `classification.py` | Product category and tool class heuristics, stored-classification application |
| `overrides.py` | The technician overrides library: validation and application |
| `invariants.py` | Plan integrity checks: the runtime invariant and reconciliation layer |
| `layout.py` | Cabinet planogram allocation, including restock buffer cells |
| `distribution.py` | Per-supply-point summary and distribution helpers |
| `export_shaping.py` | Column shaping for the export sheets, KPI/subclass frames, frame tokens |
| `deck.py` | Pure content model for the KROMI presentation deck |
| `workbook.py` | The result-workbook builder: every table, chart, and planogram sheet |
| `export_frames.py` | The Summary, Run_Metadata, audit, bucket comparison and distribution tables of the workbook |
| `kromi_numbering.py` | KROMI article number assignment |
| `kds_structure_words.py` | The official KDS structure-code vocabulary (Bezeichnung 1 words to categories) |
| `export_safety.py` | Keeps customer text from becoming live spreadsheet formulas in exports |
| `ai_batch.py` | One AI classification batch: payload, retries, response validation |
| `run_fingerprint.py` | The run fingerprint: the value that gates cached results |
| `run_restore.py` | Restoring a stored run's control settings and column mapping |
| `run_prefs.py` | Per-file run preferences, remembered across sessions |
| `plan_config.py` | The immutable sizing-factor configuration for one planning run |
| `constants.py` | Facade over the four topical constant modules below |
| `cabinet_geometry.py` / `sizing_factors.py` / `override_schema.py` / `classification_tables.py` | Machine geometry and capacities; sizing factors and routing enums; the override schema; the classification keyword taxonomy |
| `ai_classifier.py` / `ai_schema.py` / `ai_estimate.py` | AI classification plumbing, schema, and cost/ETA estimation |
| `colmap.py` | AI-assisted column-mapping helpers |
| `dimensions.py` / `fitting.py` | Package dimension extraction and dimensional fit checking |
| `evaluation.py` | Classifier-quality metrics |
| `text_utils.py` | Text and numeric utility helpers |

## Running

```bash
pip install -r requirements.txt
streamlit run Home.py
```

The planner page calls an LLM for the classification fallback; set
`OPENAI_API_KEY` in a local `.env` file (not included in this package).

### Operational modes

"Cabinet composition" on the planner page chooses how cabinets are decided:

- **Standard** sizes the cabinets each supply point needs (best fit per tool).
- **Helix only** / **Carousel only** put every vending tool in one cabinet type.
- **Helix + Carousel (capped)** limits the Carousels per supply point and moves
  the overflow into Helix coils.
- **Fixed configuration (existing machines)** (v34.52) plans for machines that
  already stand at each supply point. Enter the Helix, Carousel and Locker
  count per supply point and the headroom to keep free; articles reach a
  supply point through the Program column mapping (or the supply-point mode).
  Routing and sizing follow the normal rules; the most used articles are
  placed first; overflow may move to another machine type the article fits
  (S/M Carousel articles into a Helix, Helix articles into a Carousel, lockers
  to larger compartments; switchable). Articles that find no space are marked
  "Not placed" with the reason, never dropped. The capacity buffer, fill
  ceiling and consolidation do not apply and are hidden in this mode. The
  workbook adds `Fixed_Configuration` (capacity, usable, used, free per
  machine type) and `Not_placed`. Optional **Stock-based Helix promotion**
  (v34.58, off by default, needs the stock column): after the fit, the Helix
  space still free takes the S/M Carousel articles whose stock, spread over
  the months it is assumed to cover (default 3), means more packs a month
  than the Helix threshold and than the recorded use, highest first, each
  with the spirals the normal Helix sizing gives; the freed Carousel space
  goes to articles that found none. Status `Promoted`; the takeover maximum
  follows the spirals.
- **Only article number assignment** assigns KROMI numbers without planning.

### Takeover sheets

Map the customer's current stock ("Current stock pcs", found automatically in
a KDS onboarding list, never a minimum or maximum stock column) and the
workbook adds one `Takeover sheet SP n` per supply point, in the columns of
the KROMI takeover template: customer-property KROMI number, customer number,
Bezeichnung 1 and 2, VPE, im KTC, am HLO, Total, Schranktyp. Whole packs go
into the KTC up to the article's maximum (Carousel: compartments x VPE; Helix:
spirals x the places a spiral of the article's size holds, S 28 / M 22 / L 18 /
XL 12, x VPE); the rest stays at the HLO. Lockers, Kanban articles and
articles without space hold nothing in the KTC. The same sheets are offered
as a separate download for the technicians. The plan itself does not change.

KROMI article numbers are computed per run from the list and its settings;
they are not stored between runs (owner decision, v34.52), because an article
can move between KTC and Kanban and the parameters change the numbers.

### Network access (secure by default)

The app has no login, and the database holds every customer's stored runs and
override sets. `.streamlit/config.toml` therefore binds the server to this
computer only (`server.address = "localhost"`) and keeps error details out of
the browser (`client.showErrorDetails = "none"`). Colleagues on the network
cannot reach it. To share it deliberately on a trusted network, start it with

```bash
python -m streamlit run Home.py --server.address 0.0.0.0
```

and be aware that everyone who can reach that address sees all stored runs.

### Exports are formula-safe

Customer text is always written to Excel as text, never as a live formula
(a cell such as `=HYPERLINK(...)` in an uploaded file stays visible text), and
the CSV download quotes text that Excel would evaluate.

### Database location (important on OneDrive)

Override sets and run history live in a small SQLite database. By default it sits
in a non-synced dot-folder under the user home; `KROMI_DB_PATH` can point it
elsewhere. Keep that file **off** cloud-synced folders (OneDrive, Dropbox, Google
Drive): SQLite takes short-lived file locks while writing, and a sync client that
copies or replaces the file mid-write, or that merges writes from two machines,
can corrupt it. If the app itself must run from a synced folder, still keep the
database outside the synced tree, or at minimum run one instance on one machine
at a time and let sync settle before opening it elsewhere. Do not run two
instances against the same synced database file at once.

What the archive keeps per run (v34.53): the workbook once per content, one
tool record per article code (a later run with new codes adds them), and the
classification each run used. An identical earlier answer is shared, a new one
is added, so an AI run after a heuristic run keeps both and "Load & recompute"
reproduces the run it was asked for. A known workbook reuses the newest AI or
manual answer per code. Technician overrides are stored with the run's result,
never as the classifier's answer.

Schema changes are safe to install (v34.55): each migration runs as one
transaction, so a failure leaves the database as it was, and an existing
database is copied first to `<file>.pre-migration-v<N>-<time>.bak` next to it.
Errors the app catches on purpose (database copy skipped, deck or optimizer
failures, an unreadable override database) are written with their traceback
to the local log (see `KROMI_LOG_PATH`).

"Load & recompute" (v34.54) restores every input of the stored run: controls,
column mapping (checked at the run's header row), Tools and PPE sheets,
per-class thresholds, restockable categories, the Program to supply point map,
site, KTC-ID and customer label. The override choice is preselected with what
the run applied (its set, or none), and the banner says how many stored
settings were restored and names any the workbook no longer supports. The
duplicate-save check includes the build and the classifications, so a
recompute on a newer build is archived as a new run.

## Testing

```bash
pip install -r requirements-dev.txt
pytest
```

The suite (about 2,000 tests) runs in roughly 40 seconds and works from any
working directory. Every test gets its own temporary database and preference
store and an empty OpenAI key (see `tests/conftest.py`), so a run never writes
into the repository and never calls the network.

About 25 tests need private data and skip cleanly without it:

| Variable / location | Enables |
|---|---|
| `KROMI_RAW_INPUT_XLSX` | End-to-end page drives and differentials on a real customer workbook |
| `KROMI_GROUNDTRUTH_XLSX` | Reproduction checks against a stored planner Result workbook |
| `tests/fixtures/` or `KROMI_FIXTURE_DIR` | Classifier cross-checks against sample catalogs and the taxonomy export |

> **Note:** sample fixtures contain real customer catalog data. They are
> provided for local validation only and are never packaged into releases.

The byte-identity release gates live in `tools/`: `golden_capture.py` dumps the
plan tables and `export_capture.py` digests every exported sheet for three
scenarios, so two builds can be compared cell by cell.

The synthetic golden gate (v34.59) needs no private data and runs in every
`pytest` and in CI: `tools/synthetic_golden.py` generates an invented,
deterministic catalog, drives the page through four scenarios (standard with
consolidation, capped with two replicated supply points, fixed configuration
with Program mapping, stock and the stock-based Helix promotion, numbering
only) and compares the persisted plan tables and the exported workbook with
`tests/golden/synthetic_manifest.json`. After an intended change, run
`python tools/synthetic_golden.py --update` and say why in the CHANGELOG.

## Quality checks

One command runs every gate (v34.59):

```bash
python tools/check.py            # lint, types, customer-name scan, wording scan
python tools/check.py --tests    # the same plus the full suite (release gate)
```

The customer-name scan covers every tracked file; the names are stored only
as salted hashes, so the repository never spells them. The wording scan
checks the lines added since `origin/main` for the em dash and banned filler
words.

CI (`.github/workflows/ci.yml`, Python 3.10 to 3.12) runs the same gates:

```bash
ruff check --select F821 .                          # undefined names (gate)
ruff check --select E9,F63,F7,F82,F811 .            # correctness rules (gate)
ruff check --select F401 .                          # unused imports (gate)
mypy                                                # engine/, db/, app_log.py (gate)
pytest                                              # full suite (gate)
pip-audit -r requirements.txt                       # known vulnerabilities (report)
```

The wider rule set configured in `pyproject.toml` (bugbear, pyupgrade, import
order) and `ruff format` are not gates yet; the pages and `ui/` are outside
mypy's scope.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | (none) | Enables the AI classification fallback and AI column mapping |
| `OPENAI_MODEL` | `gpt-5-mini` | Model used for AI calls |
| `MAX_AI_ITEMS`, `AI_BATCH_SIZE` | 400, 20 | AI volume per run and per batch |
| `AI_CONCURRENCY`, `MAX_AI_CONCURRENCY` | 5, 20 | Parallel AI batches (default, upper limit) |
| `AI_CALL_TIMEOUT_SECONDS`, `AI_MAX_BACKOFF_SECONDS` | 60, 10 | Per-call timeout and retry backoff cap |
| `MAX_DESC_CHARS_FOR_AI` | 220 | Description length sent to the model |
| `EST_*` | see `engine/ai_estimate.py` | Token and time assumptions for the AI cost estimate |
| `KROMI_DB_PATH` | `~/.kromi_cabinet_planner/kromi.db` | SQLite database location (a bare file name resolves against the working folder) |
| `KROMI_LOG_PATH` | `~/.kromi_cabinet_planner/logs/planner.log` | Local log of errors the app catches (1 MB x 5 files); `off` switches it off |
| `KROMI_FILE_PREFS_PATH` | `runs/file_prefs.json` | Remembered KTC-ID and customer per file |
| `KROMI_DEFAULT_KTC_ID`, `KROMI_DEFAULT_CUSTOMER`, `KROMI_DEFAULT_SITE` | 191, empty, empty | Prefills for new files |

## Releases

Build a release zip from the explicit allow-list (secrets, runtime state,
databases and caches are refused even inside allowed folders):

```bash
python tools/package_release.py . kromi_app_vXX.YY.zip
```

On Windows, `run.bat` runs `tools/ensure_deps.py` before starting the app: it
reinstalls dependencies whenever `requirements.txt` changed since the last
successful install, and never blocks a working installation if an update fails.

## Version control and development

The code lives in a private GitHub repository. `main` is what users run; each
release is a PR merged into `main` and tagged `vXX.YY`. The rewrite prototype
without Streamlit lives on `rewrite/fastapi-react` (`docs/Rewrite_Decision.md`).

Development runs in Claude Code on the web (claude.ai/code) against this
repository. `CLAUDE.md` holds the working rules every session reads first, and
`.claude/settings.json` installs the dependencies when a cloud session starts
(`tools/cloud_setup.sh`). Background documents are in `docs/`: roadmap, audit,
professionalization plan, rewrite decision and the domain rules.

The `.gitignore` keeps secrets (`.env`), the SQLite database, runtime data
(`runs/`, `overrides/`, `catalogs/`), build zips and every customer file type
(`*.xlsx`, `*.xls`, `*.xlsm`, `*.csv`, `tests/fixtures/`) out of history.
Customer workbooks for the private golden gate stay on the owner's computer.

## Product taxonomy

Classification is aligned to the Kromi `VS_PRODUCT_CAT` hierarchy: 19 top-level
families (drills, mills, threading tools, reamers, counterbores, inserts,
holders, tool holders, grinding tools, etc.) mapped to 24 internal product
categories and 81 tool-class subtypes, with keyword tables in 10 languages
(DE/EN/FR/ES/PT/PL/CZ/SK/SL/DK). Threading tools are split into taps, thread
mills, and thread dies because they differ in physical storage requirements.

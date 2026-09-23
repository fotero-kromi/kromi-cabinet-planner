# Project knowledge (handover from the chat project)

Written 2026-09-23 at v34.59/v34.60, when development moved from the Claude chat
project to Claude Code on the web. It holds what the chat project knew that is not
in `CLAUDE.md`, `docs/Domain_Rules.md`, `docs/Roadmap_Status.md` or the CHANGELOG:
background, reasons, lessons, procedures and open points. Customer names are left
out on purpose; where a real onboarding is meant, it is called "a real onboarding".

## 1. Where the knowledge lives now

| What | Where |
|---|---|
| Working rules | `CLAUDE.md` |
| Planning arithmetic | `docs/Domain_Rules.md` |
| What shipped, owner decisions, next steps | `docs/Roadmap_Status.md` |
| Release history with reasons | `CHANGELOG.md` (v33.x to today) |
| Audit, professionalization plan, rewrite decision | `docs/` |
| Background, lessons, procedures (this file) | `docs/Project_Knowledge.md` |
| Customer workbooks, machine database dumps, real result files | Only on the owner's computer and in the chat project. Never in git. |

The repository is the source of truth from now on. The chat project stays the place
for work on real customer files: the private golden gate, onboarding analyses,
customer emails.

## 2. Personal working rules

Personal working rules come from the session environment, not from this
repository.

## 3. Working agreements (beyond CLAUDE.md)

- Staged multi-turn releases, never a big-bang refactor.
- Aim for about three times the obvious minimum of tests.
- Every pipeline change is validated on a real customer file (the private gate,
  section 7) in addition to the synthetic gate.
- A release report states: what changed, exact modifications, impact, regressions
  checked, what could not be verified, and a clear ship verdict. End with the
  remaining roadmap.
- When a session resumes from a summary, check the files on disk before acting.
  Memories and summaries go stale; re-derive from the code.
- Treat earlier work, including your own, as claims to verify. Independent audits
  have repeatedly found real bugs that implementation review missed.

## 4. Lessons that cost real time

- **Second-source drift** is the recurring bug pattern: the same value computed in
  two places drifts apart (the PDF parameters in v34.01, the sizing factors in
  v34.09). Keep one canonical object (PlanConfig, PlanParams) and tests that pin
  readers to it.
- **Structural beats cosmetic.** A UX experiment in v33.67 to v33.71 (metric cards
  via columns, sections folded into expanders, in-place override-set updates) did not
  work out and was fully reverted. The real problem was rerun latency, fixed by the
  run_plan cache in v34.10. Do not bring back the metric-card direction.
  `[class*="css"]` selectors are dead since Streamlit 1.58 (classes are
  `st-emotion-cache-*`); verify CSS against the installed front end.
- **Environment discipline.** Verify on the declared dependency majors (pandas 2).
  A drifted container once validated a world customers could not install. Fresh
  installs pull the newest allowed versions; v34.60 had to pin `numpy<2.5` for the
  type check.
- **File identity needs two models**: the byte memo identifies the upload event,
  the content hash identifies the data for mapping and state. Mixing them caused a
  regression.
- **Hash-equality collapse**: `True == 1 == 1.0` in Python, so dict keys built from
  cell values merge different values. Normalize per cell first.
- **Historical anchors are irreplaceable.** Regenerating a ground-truth result
  workbook failed (34 % of rows fell to "other") because the original held AI-refined
  categories. Keep original files; never regenerate ground truth from AI.
- **Leakage vigilance.** A customer-specific column header once shipped for weeks in
  a docstring and a test. The hashed name scan exists because of that.
- **Pipes hide failures**: `cmd | grep X` returns grep's status. Keep Error and
  Traceback visible or check the exit code separately.
- **Windows portability** (found in v34.59/60): pandas `to_csv()` uses the platform
  line ending, and `open()` without `encoding="utf-8"` reads cp1252 on Windows.

## 5. Streamlit and testing specifics

- `st.cache_data` arguments: only DataFrames, frozen dataclasses, tuples and scalars;
  no raw dicts, no callables. Frames passed with a leading underscore are not hashed,
  so the cache key must carry their token (`frame_token`).
- One fresh `AppTest` instance per scenario. A third or later run on one instance
  has a known flake that skips the archive write; never use it to reproduce
  persistence behaviour.
- The headless full-pipeline drive uses the reload path: seed `_reload_ctx` (file
  bytes, customer, site, stored classifications, override mode) and
  `_pending_restore` (from `build_seed`), run once, set `_force_run`, run again.
  AI is never called in tests.
- Optional column-mapping seeds are popped by the new-file reset; select them after
  the first run. A settings change clears the results; the new fingerprint is
  stored only on the next run.
- `.streamlit/config.toml` is load-bearing: KROMI theme (primary #006C52, secondary
  #F4F8F5, text #4A4A49), `showSidebarNavigation = false` (navigation is the Home
  picker plus Back buttons), server bound to localhost, error details off. A change
  needs a full Streamlit restart.
- Smoke-test noise filter: drop `ScriptRunContext`, `bare mode` and `Stack` lines,
  keep Error and Traceback.

## 6. AI classification facts

- OpenAI mini-class model via `OPENAI_MODEL`; batches run in parallel and are cached
  by content, so reruns never bill twice. Failed batches are not cached (v34.48).
- Cost and time model, calibrated in production: about 65 s per batch and about 164
  output tokens per item; the free-text "reason" field dominates both. Time =
  ceil(batches / workers) x seconds per batch. "Trim AI reasons" makes runs cheaper.
- The model is not deterministic between runs. A known workbook reuses the newest
  stored AI or manual answer per code (v34.53).

## 7. The private golden gate (real customer file)

Why: the synthetic gate proves nothing changed on invented data; the private gate
proves it on a real 1,075-row catalog. Required for every change to the planning
pipeline or the exports, before merging.

Where it can run: wherever the customer workbook is. Either the chat project (upload
the workbook and both builds), or a local Claude Code session on the owner's
computer (Windows works from v34.60; that session needs a GitHub login only if it
should push).

Procedure (previous build A, new build B, for example two git worktrees):

```bash
export KROMI_RAW_INPUT_XLSX=<customer workbook>      # never inside the repo
# in each worktree (A and B):
python tools/golden_capture.py <out>/golden_<X> <X>
KROMI_EXPORT_KEEP=<out>/keep_<X> python tools/export_capture.py <out>/exports_<X> <X>
```

Pass criteria:
- The golden dumps (per-tool rows, bucket plans, grand totals for three scenarios)
  are identical between A and B.
- Both exported workbooks (default and technical configuration) have the same
  sheets, and every sheet is identical except the `Build` row of `Run_Metadata`.

The comparison was a scratch script in the chat project; making it a committed
tool (`tools/compare_gates.py`, with tests) is an open item.

Environment switches for the 25 tests that skip without private data:

| Variable | Enables |
|---|---|
| `KROMI_RAW_INPUT_XLSX` | End-to-end page drives and the QA differential on a real workbook |
| `KROMI_GROUNDTRUTH_XLSX` | Reproduction against a stored result workbook (the original historical file is needed; a regenerated one does not work, see section 4) |
| `KROMI_FIXTURE_DIR` or `tests/fixtures/` | Classifier cross-checks against a sample catalog and the KROMI structure translations workbook |

The KROMI structure translations workbook is KROMI's own reference data, not customer
data. If the owner agrees, it can be committed (with a `.gitignore` exception) so
those tests run in cloud sessions. The sample catalog is customer data and stays out.

## 8. Calibration facts and ground truth

- A real 10-pack insert catalog separated Helix from Carousel correctly at about
  1.45 packs per month; the old default of 6 to 7 inverted the routing.
- A validated assignment from an August 2026 onboarding (118 Helix / 221 Carousel
  articles, 15 % buffer, a clean cut at about 1.45 packs per month) is the
  regression ground truth for calibration work. The file is on the owner's side.
- Open calibration gap: the physical spiral holds 22 packs; the engine uses 28 for
  size S.
- VPE errors dominate plan quality: in one validated takeover about 97 of 339
  articles changed rank after VPE corrections.

## 9. Onboarding recipes

- KROMI onboarding templates carry banner rows (real headers on row 4): set the
  header row. Map Description = the dimension-rich second description column,
  Product category = the structure word column; leave Description 2 and Year
  unmapped. Otherwise the dimension-based numbers overflow their variant pool.
- Number a customer's complete list in one run with one KTC-ID (numbers are not
  stored between runs).
- Stock: the "Current stock pcs" mapping is found automatically (never a min, max,
  safety level or location column). With Replicate mode the stock is one pool; with
  a Program mapping each location brings its own stock.
- Fixed configuration: enter the machines per supply point; articles that do not fit
  are listed as "Not placed", never dropped. Stock-based Helix promotion helps when
  consumption is missing but stock is high.

## 10. Open points from the last real onboarding (September 2026)

- About 38 % of the articles had no consumption; the stock-based promotion
  (v34.58) was the answer. Check its effect on the next onboarding.
- An insert whose file said VPE 1 was planned with the insert default VPE 10.
  Decide whether a file value of 1 should win over the category default.
- Holders in structure family 807 (code 20008) did not match the expected article
  setup codes for about a dozen articles. The owner said to ignore it for now.
- Three XXL articles needed a manual locker decision.
- Offered, not confirmed: a "Placed (incl. moved)" label, and a warning when a supply
  point with machines receives no articles.

## 11. Parked, dropped and known conflicts

- Parked: `controls_model.py` (a portable control-group model, tested). The v34.10
  handover said keep it for the UX track; the v34.47 audit and the professionalization
  plan list it as dead code to delete. Ask the owner before deleting it.
- Parked: EGC planner phase 2 (slot packing and bin allocation for other machine
  types); `pages/2_EGC_Planner.py` is a specification preview only.
- Parked: the solver comparison (`optimization.py`, PuLP/CBC) is a showcase: it runs
  on demand and reports the difference to the heuristic plan without claiming a win.
- Dropped by decision: an article-import page for a retired product information
  system. Do not revive without a new request.
- Dropped by decision (2026-09-22): a stored article-number registry (audit C1).

## 12. Environment facts

- Users run the app on Windows from a synced folder with system Python, started by
  `run.bat`, which reinstalls dependencies when `requirements.txt` changes. The owner's
  PC runs Python 3.14, which CI does not test yet (CI: 3.10 to 3.12).
- The database lives outside synced folders (`~/.kromi_cabinet_planner/`); SQLite and
  cloud sync do not mix.
- Repository: private, on the owner's GitHub account (`fotero-kromi`). Cloud sessions
  push through the Claude GitHub App; a local session on a PC needs its own GitHub
  login (for example `gh auth login`) to push.

## 13. Extra customer identifier for the name scan

The old handover listed one more customer identifier: a three-letter code, capitals
only, that is also a common abbreviation. It is not yet in the hashed scan. Its
digest for `BANNED_EXACT_DIGESTS` in `tools/check.py` (case-sensitive, so the
lower-case word stays allowed):

```
b10d9b161099c0f642245383b8f3e99181695e41b5dd8eaf0a583378a5ec8a1f
```

The repository does not contain it today (checked 2026-09-23).

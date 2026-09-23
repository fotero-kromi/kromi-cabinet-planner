# Code Professionalization - Analysis and Plan

Date: 2026-09-23. Baseline: v34.58. Scope: the Streamlit layer (pages/, ui/) and the repository practices around it. The engine (engine/, db/) is not the problem and is only touched where page logic moves into it.

> **Status 2026-09-23:** step 0 shipped as v34.59 and the project is in git. The owner then chose to prototype a rewrite without Streamlit on a branch (`docs/Rewrite_Decision.md`); Option A below stays the fallback if the prototype is stopped.

## Bottom line

- The engine is in professional shape: pure, typed (mypy clean), 2,124 tests, byte-identity gates. The debt is the UI layer: one 4,720-line Streamlit script plus three functions of 380 to 520 lines.
- Earlier trimming moved code out of the page but kept the pattern (a top-to-bottom script sharing hundreds of global names). That is why every extraction produced functions with dozens of parameters (the export panel takes 68).
- Recommendation: **Option A, staged decomposition inside Streamlit** into a thin orchestrator plus typed stage modules. About **16 working days in 8 releases**, each byte-identical to the one before and gated automatically.
- Step 0 (the safety net that makes the refactor safe) is independent of the option and is being built now as v34.59: a synthetic workbook with golden results that runs in the normal test suite and in CI, without the private customer file.
- Not recommended now: a rewrite on another framework (2 to 3 months, no user-visible gain for a per-user internal tool) or a multipage split as the first move.

## Where we are (measured on v34.58)

| Measure | Value |
|---|---|
| pages/1_Kromi_Planner.py | 4,720 lines (3,794 code), 480 top-level statements |
| Module-level names in the page | 647 |
| Streamlit calls / widget keys / other session keys | 399 / 82 / 22 |
| st.stop / st.rerun (control flow) | 19 / 9 |
| Functions over 300 lines | technician_panel.render 522, workbook.build_result_workbook 463, exports_panel.render 382 (68 parameters), cabinet_math.rebalance_cabinets 345, plan.run_plan 336 |
| Tests | 114 files, 2,124 cases; 27 files drive the whole page (AppTest); 32 assertions check source text |
| Version history | not in git; the release zips are the history; 192 version tags in code comments; CHANGELOG 4,289 lines |

Page sections (implicit inputs = names read from earlier sections, i.e. the parameters a section would need today):

| Lines | Section | Code lines | Implicit inputs |
|---|---|---|---|
| 1-559 | Imports, helpers, cached wrappers | 412 | 0 |
| 560-989 | Home picker, load previous run | 351 | 17 |
| 990-1529 | Sidebar controls | 442 | 24 |
| 1530-1784 | Run setup, operational mode, fixed machines | 221 | 19 |
| 1785-1929 | Listings, sheets, header row | 104 | 18 |
| 1930-2519 | Data preview, column mapping, frame build | 475 | 44 |
| 2520-2674 | Program to supply point mapping | 126 | 11 |
| 2675-3099 | Planning base and AI classification stage | 318 | 91 |
| 3100-3199 | Numbering-only mode | 70 | 25 |
| 3200-3514 | Overrides, plan parameters, run_plan | 271 | 40 |
| 3515-3899 | Result sections (classification, sizes, fit-check, fixed fit) | 331 | up to 26 |
| 3900-4319 | Cabinet summary, per-SP, distribution | 337 | 84 |
| 4320-4449 | Classifier quality, optimizer | 106 | 13 |
| 4450-4720 | Exports, technician panel, persistence | 230 | 61 |

## Why trimming did not fix it

1. **Shared globals instead of contracts.** A Streamlit page runs top to bottom, and each section reads what the sections above defined. Moving a section into a function without first defining what it receives and returns produces functions with dozens of parameters.
2. **State in three places.** Module globals, 104 session keys, and nine caches. Nobody can see at a glance what a section depends on.
3. **Control flow by st.stop.** 19 early exits mean a section can only be tested by driving the whole page.
4. **Domain logic still in the page.** Examples: the planning-frame build (rename, sanitize, scaffold, parse), the AI pack check, the Program mapping, the duplicate-save key.
5. **Tests pinned to source text.** 32 assertions check that a string exists in a file, so moving code breaks tests without changing behaviour.
6. **No version control.** Without git, history lives in comments (192 version tags) and in a 4,289-line changelog, which adds noise to every file.

## Target architecture

```
pages/1_Kromi_Planner.py        orchestrator only (< 300 lines): call stages in order, gate, render
ui/state.py                      registry of every session key with typed accessors
engine/vocab.py                  str-Enums (OpMode, CabinetType, SystemCategory, PlacementStatus, SpMode)
                                 and the column-name registry (84 literals today)
ui/sidebar.py        -> Controls        frozen dataclass of every control value
ui/intake.py         -> Intake          file picker, load previous run, sheets, header row
ui/mapping.py        -> ColumnMap       column mapping widgets
engine/intake.py                        pure frame build (rename, sanitize, scaffold, parse)
ui/program_map.py    -> ProgramMap
engine/classify_pipeline.py             planning base, heuristics, AI stage with an injected client
ui/classify_progress.py                 progress and messages of that stage
engine/plan.py                          run_plan (unchanged)
ui/results/*.py                         classification, size fixes, fit-check, fixed fit, summary,
                                        distribution: each render(ctx: RunContext)
ui/exports_panel.py                     render(ctx: ExportContext) instead of 68 parameters
ui/technician/*.py                      editor, save dialog, set management (split of the 522-line render)
ui/persistence.py                       duplicate-save key and archive
```

Rules enforced by tests (like the existing AST test that keeps Streamlit out of the engine):

- The engine stays pure.
- Every ui module takes and returns typed objects, with no module-level mutable state.
- No function over 80 lines and no function over 8 parameters in pages/ and ui/.
- Every session key is declared in ui/state.py.

## Options

| | A. Staged decomposition (recommended) | B. Multipage split first | C. Rewrite (FastAPI + React, or NiceGUI) |
|---|---|---|---|
| What | Same app and UX; the page becomes an orchestrator of typed stage modules | Separate pages for intake, plan, results, exports | New web stack, engine reused |
| Effort | ~16 days, 8 releases | ~15 days plus UX redesign | 2 to 3 months |
| Risk | Low per step (byte-identical gates) | High: state handoff between pages, cache and restore contracts | High: two apps in parallel, new failure modes |
| User impact | None visible | Navigation changes | New UI to learn |
| When it makes sense | Now | After A, if the flow should become a wizard | If the tool must run as a shared server with logins and ERP integration |

## Plan for Option A

| Step | Release | Content | Effort | Risk |
|---|---|---|---|---|
| 0 | v34.59 | Safety net: synthetic workbook and golden results (plan tables and exported workbooks) in the normal suite and CI | 1 d | low |
| 1 | v34.60 | Vocabulary: str-Enums for modes, cabinet types, statuses; column-name registry | 1.5 d | low |
| 2 | v34.61 | Sidebar into ui/sidebar.py returning Controls; session-key registry | 1.5 d | low-med |
| 3 | v34.62 | Intake, listings and column mapping into ui/; pure frame build into engine/intake.py | 3 d | med |
| 4 | v34.63 | Program map; classification stage into engine/classify_pipeline.py with an injected AI client | 3 d | med-high |
| 5 | v34.64 | Result sections into ui/results/ with a RunContext | 2.5 d | med |
| 6 | v34.65 | ExportContext; technician panel split; persistence module | 2.5 d | med |
| 7 | v34.66 | Hygiene: source-text tests become behaviour tests; history comments out of the code; changelog archive; dead code (controls_model.py) removed; lint rules for function size and parameters | 1.5 d | low |

Total about 16.5 working days. Optional afterwards: split build_result_workbook into one writer per sheet (1.5 d) and rebalance_cabinets into its phases (1.5 d).

Every step ships with the full ceremony and must be byte-identical on the golden and export gates (private file and synthetic file). The app works after every step, so the plan can pause between releases for feature requests.

## Definition of done

- Page under 300 lines, orchestration only; st.stop only at the orchestrator's gates.
- No function over 80 lines or 8 parameters in pages/ and ui/ (checked by a test).
- Zero tests that check source text.
- The synthetic golden gate runs in CI on Python 3.10 to 3.12.
- Golden and export results identical to v34.58 throughout.

## Risks and how they are handled

| Risk | Mitigation |
|---|---|
| Widget keys change and saved runs no longer restore | Keys move to one registry unchanged; the restore and faithful-recompute tests stay green |
| Cache contracts break (plan, workbook, deck) | The existing cache-contract tests; no change to cache keys |
| Hidden coupling through globals | One section per release; each returns a typed object; undefined-name gate |
| Scope creep | Each step is a release that can stand alone; stop at any step |

## Decisions needed

1. Approve Option A and the order above.
2. Put the project under git (a local repository is enough to start; a company Git server enables CI). Without it, CI and code review stay theoretical.
3. Whether feature requests may interleave between steps (recommended: yes, one release at a time).

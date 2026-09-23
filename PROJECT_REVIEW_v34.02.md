> **Historical document (v34.02).** Kept for the record; many figures and findings below no longer apply (the page has shrunk, the PDF exporter is gone, `run_plan` exists). The current assessment is the principal audit of v34.47 and the roadmap releases that follow it (CHANGELOG from v34.48).

# Kromi Cabinet Planner — Critical Project Review (at v34.02)

*Scope: full codebase as it stands after the v33.96–v34.02 work. Evidence-based; every
structural claim was measured against the source, not recalled. The brief was to be
highly critical and assume mistakes until proven otherwise, so strengths are stated
briefly and weaknesses in detail.*

---

# Executive Summary

The project is **two codebases wearing one coat**. Underneath is a genuinely strong,
pure, framework-free planning engine — 27 focused modules, ~9,800 lines, 1,673 passing
tests, no Streamlit or I/O dependencies, clean separation by concern (demand, sizing,
routing, fitting, distribution, invariants). That layer is close to the stated standard
of "industrial, bug-free, quality."

On top sits a **single 6,136-line Streamlit page** that is the opposite: 4,605 of those
lines (75%) execute at module level as one long top-to-bottom script, mixing UI,
pipeline orchestration, a 491-line PDF generator, the OpenAI client, the override
workflow, and nine "shim" functions that smuggle run-time settings into the pure engine
through module-level globals. This page is where every production bug of the last two
weeks lived: two latent `NameError`s, the Helix overfill mis-sizing, and the cap/buffer
interaction. None of them were engine bugs. All of them slipped through because the page
cannot be tested end-to-end — the render smoke stops at the upload gate, and the 4,605
lines past it never run under test.

So: **the engine satisfies the goals; the page is the liability.** The single most
valuable direction is not new features but finishing the in-progress decomposition —
pulling the deterministic pipeline behind one cached `run_plan` entry point and killing
the shim/global pattern with an explicit config object. That move simultaneously closes
the testability gap that produced every recent bug, removes the fragility class, and
fixes the per-interaction full recompute. Everything else is secondary.

Two honest corrections surfaced during this review, both worth stating plainly:

1. The classifier drift I attributed to the AI last session was **wrong** — across 1,075
   common codes between the two reported runs, ProductCategory changed on 0 and ToolClass
   on 1. The 510→498 KTC shift was the threshold change (0.7→0.8) behaving correctly.
2. The "179 unused imports" figure is misleading: 109 are **intentional re-exports** in
   `engine/__init__.py`. The real dead weight is 68 imports, all in the page.

---

# Architecture Review

## Strengths

- **Engine purity is real and rare.** `engine/` has no Streamlit import, no file I/O in
  the hot path, and is a deterministic function of its inputs. This is why it is testable
  and why the 1,673 tests are meaningful rather than theatre.
- **Sensible decomposition by domain.** demand → sizing → fitting → routing_rules →
  cabinet_math → distribution → invariants is a clean pipeline with each stage in its own
  module. `engine/plan.py` (the new composition layer) is the right idea.
- **Strong invariants discipline.** `engine/invariants.py` (consumption conservation,
  uniqueness) encodes real domain guarantees and is checked at run time.
- **Auditability.** Per-build zips, a 2,473-line CHANGELOG, Run_Metadata sheets, and the
  override-set persistence give a real audit trail — appropriate for aerospace/automotive
  customers.

## Weaknesses

- **The page is a monolith and a script, not a module.** 4,605 of 6,136 lines run at
  import time. Streamlit re-executes all of it on every widget interaction. This is the
  central architectural defect: it is untestable, re-runs the entire plan on every click,
  and forces orchestration, UI, and rendering to share one namespace.
- **The shim/global anti-pattern.** The engine is functional (factors passed as
  parameters), but the page re-introduces global mutable state: `helix_overfill_factor`
  and `carousel_reserve_factor` are assigned at module level (line ~1950) and read by nine
  wrapper functions that forward them into the engine. This is brittle by construction —
  a call resolving to the bare engine function instead of the shim silently uses a default
  constant. That is *exactly* the Helix overfill bug. The pattern guarantees more of the
  same.
- **Rendering lives in the wrong layer.** `build_per_sp_pdf` is 491 lines of reportlab
  inside the UI page. There is a `presentation.py` (374 lines) where it belongs. PDF
  generation cannot be tested without importing the whole Streamlit page.
- **No single entry point to the plan.** The pipeline is a sequence of mutations on a
  `work` DataFrame interleaved with UI. There is no `plan = run_plan(df, config)` to call,
  cache, or test. The six extracted segments are the down payment on this; the capstone is
  not built.
- **Two-tier "constants."** `engine/constants.py` is 1,462 lines — geometry spec, override
  schema, planning factors, and validation sets in one grab-bag. It is data, not logic
  (1 def), so this is low-severity, but it conflates three unrelated concerns.

---

# Code Quality Review

- **68 dead imports in the page.** Genuinely unused (the page is an endpoint, so no
  re-export excuse). Pure noise that slows comprehension. Example classes: leftover engine
  imports after extractions (`_parse_pack_override`, `apply_capacity_buffer`) and stale
  helpers. *The engine non-`__init__` modules are clean — 0 unused — so this is a
  page-only problem.*
- **26 broad `except Exception` in the page.** Several are legitimately defensive (PDF
  generation, optional Excel sheets, cosmetic formatting), and one is even annotated
  `# pragma: no cover - defensive`. But 26 is a lot, and broad swallowing is precisely how
  a real error hides as a missing optional feature. They deserve an audit pass:
  narrow the exception type or at least log.
- **A few oversized functions.** `cabinet_math.rebalance_cabinets` (345 lines) and
  `classification.classify_with_evidence` (243) are doing too much in one frame; both are
  decomposition candidates. `run_override_application_segment` (143, my own recent work)
  is at the upper bound of acceptable and only survives because it is a faithful 1:1
  extraction proven against the original.
- **The shim names shadow the engine names.** `compute_plan_for_subset`,
  `rebalance_cabinets`, `apply_carousel_cap` all exist as both a page shim and an
  `_engine_`-aliased import. Same identifier, two meanings, resolved by scope. This is the
  root reason the overfill bug was invisible to a token-level diff.
- **Positives:** consistent docstrings (28/28 engine modules), no `TODO/FIXME/HACK`
  littering (0 markers), no bare `except:`, no `print` debugging, parameterized SQL
  throughout.

---

# UI/UX Review

- **Density.** 525 `st.*` calls and 89 `st.session_state` references in one page. This is
  a control-heavy expert tool, which the domain justifies, but the sidebar and main panel
  have grown organically. The user could not find the carousel cap controls in the PDF —
  a symptom of too many knobs without grouping.
- **Parked grouping work.** `render_group_popover` and the `controls_model.py`
  (NumberSpec / ControlGroup) abstraction exist to group controls into popovers, but the
  wiring (Carousel Controls, Capacity Buffer) is deferred and unconnected. The
  infrastructure is half-built.
- **Re-run cost is a UX problem too.** Because the whole script re-executes per
  interaction and the plan is not cached, every control change re-runs the full pipeline.
  On a 1,075-row dataset that is tolerable; it will not be at 10,000 rows.
- **Reproducibility surprise.** A browser refresh silently resets settings to defaults
  (capacity buffer 10%→0% in the reported case). That is standard Streamlit behavior, but
  it caused real confusion. Persisting the last-used controls (the run_prefs module exists)
  would remove a whole class of "why did the number change" reports.
- **The PDF parameter omission (now fixed in v34.01)** was a genuine UX failure: a capped
  run that did not show the cap. Worth a systematic check that every run-affecting control
  appears in both the Excel Run_Metadata and the PDF snapshot — they drifted apart because
  they are two hand-maintained lists.

---

# Performance Review

- **Full recompute per interaction.** No `run_plan` + `@st.cache_data` around the
  deterministic pipeline, so changing any control re-runs everything. The fix is the
  capstone, with a cache key that is a superset of the run fingerprint.
- **AI is the real cost, and it is already cached.** `ai_classify_batch_cached` and
  `_ai_suggest_colmap_cached` use `@st.cache_data`, so within a session repeated identical
  batches are free. The known cost driver is the classification "reason" field
  (latency/tokens) — worth making optional or trimming.
- **Cross-session AI reuse is built but unwired.** `db/classification_reuse.py`
  (`classifications_by_code`, `apply_stored_classifications`) exists and is referenced
  **zero** times in the page. Wiring it would make a re-uploaded or slightly-edited file
  reuse prior classifications, cutting both cost and cross-run variance.
- **DataFrame `.apply(axis=1)` and per-row `.at[]` loops** appear in the override and
  routing paths. Fine at 1k rows; vectorization matters only if row counts grow an order
  of magnitude.

---

# Security Review

Genuinely low risk for an internal tool — better than the rest of the code suggests.

- **API key:** read from `OPENAI_API_KEY` env, hard failure if absent. Not hardcoded. Good.
- **SQL:** 34 `execute()` calls, all parameterized; the only `executescript` is the static
  schema. No injection surface found.
- **Path construction:** override folders are built through a `_safe_scope_component`
  sanitizer, mitigating traversal from customer/site names.
- **The one thing to flag:** customer consumption data (part numbers, descriptions,
  volumes) is sent to OpenAI for classification. For aerospace/automotive customers this is
  a **data-governance** question, not a code bug — it should be a conscious, documented
  decision (DPA / zero-retention endpoint / opt-out), not an implicit one.

---

# Technical Debt

Ranked by how much it hurts.

1. **The 6,136-line page / 4,605-line top-level script.** Untestable, re-runs wholesale,
   conflates every concern. Root of all recent bugs.
2. **Shim + module-global factor injection (×9).** The fragility class that produced the
   overfill bug. Should become an explicit `PlanConfig`.
3. **`apply_carousel_cap` shim drops two controls.** It forwards only
   `helix_overfill_factor`, not `carousel_fill_ceiling` or `empty_cabinet_threshold_pct`
   (engine defaults 1.0 / 0.0). If those controls are meant to influence the cap, they
   currently do not — a latent bug of the same family, not yet user-visible.
4. **Classification reuse built but unwired.** Dead capability that also happens to be the
   real fix for cross-run AI variance.
5. **68 dead imports in the page.** Noise.
6. **No architecture document.** No `docs/`. Onboarding and the CTO review rely on reading
   6,000 lines.
7. **EGC Planner Phase 2** is an intentional stub (`pages/2_EGC_Planner.py`) — fine, but
   tracked here for completeness.
8. **Two hand-maintained parameter lists** (Excel Run_Metadata vs PDF controls) that drift
   — caused the v34.01 bug.

---

# Quick Wins (high impact, low effort)

| # | Win | Why it matters | Effort |
|---|-----|----------------|--------|
| Q1 | Remove the 68 dead page imports | Cuts noise, raises signal; pyflakes-verifiable | XS |
| Q2 | Wire `classification_reuse` | Cheaply reduces cross-run AI variance and cost | S |
| Q3 | Single source for the parameter snapshot (one dict feeding both Excel + PDF) | Kills the drift that caused v34.01 | S |
| Q4 | Add a `PROJECT_REVIEW` / `ARCHITECTURE.md` under `docs/` | Removes the "read 6k lines" onboarding tax | XS |
| Q5 | Fix the `apply_carousel_cap` shim to forward fill-ceiling + empty-threshold (or prove they should not apply) | Closes a latent bug of the overfill family | S |

---

# High-Impact Improvements (significant value)

| # | Improvement | Why it matters | Effort |
|---|-------------|----------------|--------|
| H1 | **`PlanConfig` frozen dataclass** replacing the nine shims/globals | Removes the entire bug class that hit production twice; makes the engine call sites explicit | M |
| H2 | **`run_plan(df, config) -> PlanResult` + `@st.cache_data`** | Closes the end-to-end test gap that shipped two NameErrors; ends per-interaction full recompute; enables true reproducibility | L |
| H3 | **Extract the per-bucket planning loop** (compute vs display) — the last segment before H2 | Prerequisite for H2; makes the planning core testable | M |
| H4 | **Move `build_per_sp_pdf` to `presentation.py`** | Removes 491 lines from the page; makes PDF testable | M |
| H5 | **A shipped "factor-injection" guard test** (Stage C) | Mechanically prevents the overfill/cap bug family from recurring | S |

---

# Refactoring Opportunities (specific)

- **`pages/1_Kromi_Planner.py`** → split into: `planner_app.py` (thin UI + control wiring),
  `planner_pdf.py` (the 491-line PDF), `planner_ai.py` (OpenAI client + cached calls), and
  let `engine/plan.run_plan` own orchestration. Target: page under ~1,500 lines, zero
  engine-factor shims.
- **`engine/constants.py`** → split into `geometry.py` (Häwa/Storetec spec + lookups),
  `override_schema.py` (columns + validation sets), and a slim `constants.py` (planning
  factors). Low risk; pure data moves.
- **`cabinet_math.rebalance_cabinets` (345 lines)** → extract the move-selection and
  audit-event construction into named helpers; the relocation logic and the bookkeeping
  are two separable responsibilities.
- **The nine shims** → delete entirely once `PlanConfig` exists; the engine functions take
  the config (or its fields) directly, called from `run_plan`, with no page wrappers.

---

# Recommended Action Plan

### Critical (do first — they remove bug classes and unblock everything)

1. **H3 → H1 → H2 as one campaign.** Extract the per-bucket loop, introduce `PlanConfig`,
   then compose `run_plan` + cache. This is the spine: it ends the untestable-script era,
   the shim fragility, and the recompute cost in one arc. Staged, with golden proofs, as
   the recent segment work has been.
2. **H5 (factor-injection guard).** Cheap, safe (a test), and it pins the lesson from the
   two production bugs so the campaign above cannot regress it.

### Important (do alongside / soon)

3. **Q5** — fix or justify the `apply_carousel_cap` fill-ceiling/empty-threshold gap.
4. **Q2** — wire classification reuse (also reduces AI cost).
5. **Q3** — unify the parameter snapshot so Excel and PDF cannot drift again.
6. **H4** — move the PDF generator out of the page.

### Nice to have

7. **Q1** — dead-import sweep (page).
8. **Q4** — architecture doc (this file is a start).
9. **constants.py** split.
10. The parked UX track (control popovers, green-when-changed, navigation) — *after* the
    logic spine is solid, per the standing priority.

---

## Ranking by impact × effort (the one-line "why")

| Rank | Item | Impact | Effort | Why it earns the slot |
|------|------|--------|--------|-----------------------|
| 1 | H5 guard test | High | S | Stops the recurring bug family for almost nothing; safe (test-only) |
| 2 | Q5 cap fill-ceiling fix | High | S | Known latent bug, same family as the two just fixed |
| 3 | H1 PlanConfig | High | M | Deletes the fragility root; precondition for clean H2 |
| 4 | H3 bucket-loop extract | High | M | Last blocker before the capstone |
| 5 | H2 run_plan + cache | Very High | L | Closes the test gap + recompute + reproducibility — the payoff |
| 6 | Q2 classification reuse | Med | S | Cheap variance/cost reduction; capability already exists |
| 7 | Q3 unified param snapshot | Med | S | Prevents a repeat of the v34.01 drift |
| 8 | H4 PDF extraction | Med | M | De-monoliths; testability |
| 9 | Q1 dead imports | Low | XS | Pure hygiene |
| 10 | constants split / UX track | Low–Med | M | Real but not urgent |

The campaign's center of gravity is H2, but H2 is large and correctness-sensitive on a
live system. The right opening move is the **guard test (H5)** and the **cap fill-ceiling
fix (Q5)**: both are small, both are safe, both directly continue the bug-elimination work
already underway, and the guard makes the larger campaign safe to attempt.

---

# Appendix — Second-Pass Engine Audit (added at v34.03)

The first pass praised the engine but largely took it on trust. This pass did the
opposite: it assumed the planning math was wrong until the numbers proved otherwise.
The conclusion is reassuring, and that is itself a finding worth recording; the
"industrial" claim is earned at the layer that matters.

**Status update:** H5 (the factor-injection guard) is shipped as **v34.03**. It discovers
the five factor-sensitive functions automatically and was shown to flag the exact reverted
overfill omission (`compute_helix_spirals_needed missing overfill_factor`) while passing on
current code. Suite 1673 → 1676.

## What was verified correct (not just assumed)

- **Capacity-buffer math** (`apply_capacity_buffer`): correct percent inflation, correct
  zero/negative guards. Buffer is a percent (10 → ×1.10), confirmed.
- **Cabinet-count boundaries** (`carousel_cabinets_needed`): 720→1, 721→2, 1440→2, 1441→3.
  Exact. Negative/zero slots clip to 0.
- **Base vs buffered consistency**: `helix_cabs_base` and the buffered `helix_cabs` both
  reduce to `ceil(spirals/70)`; carousel base and buffered both reduce to `ceil(slots/720)`
  at buffer 0 / fill-ceiling 1.0. No drift between the two code paths.
- **`apply_carousel_cap`**: correct under the degenerate `cap=0` (S/M tools spill to Helix,
  L/XL tools that cannot spill are flagged as overflow); my initial suspicion of a bug was
  wrong. Never mutates input.
- **`rebalance_cabinets`** (the 345-line one): immutable (input untouched), row- and
  code-conserving, graceful on empty and single-row subsets, and it makes the sensible
  consolidation move. No crash, no data loss across the edge cases probed.
- **Factor threading**: the upstream sizing entry point (`route_and_size_row`) takes
  `helix_overfill_factor` and `carousel_reserve_factor` as **required** parameters, so the
  overfill bug class is structurally impossible at the sizing layer; it can only appear in
  functions whose factor has a default, which is exactly the set H5 now guards.

## new findings from this pass

1. **The `carousel_fill_ceiling` / `empty_cabinet_threshold_pct` feature is dead in
   practice.** The absorption loop inside `carousel_cabinets_needed` is real, non-trivial
   logic, and both `apply_carousel_cap` and `compute_plan_for_subset` thread the parameters
   through; but **no page control feeds them** (0 references), so the loop never executes
   in production and the parameters are always their "off" defaults. This is simultaneously
   an *unfinished feature* and *dead complexity carrying test surface*. The decision is
   binary and should be made deliberately: **wire it** (add the control, and then the cap
   must honour it; the Q5 item) **or delete it** (remove the loop and the parameters,
   shrinking the surface). Carrying it half-built is the worst of both.

2. **`compute_helix_needs` ignores `overfill_factor` on its primary path.** When a
   `Spirals_needed` column is present (always, in the live pipeline) it sums the
   precomputed values and the passed factor is irrelevant; the factor only drives the
   defensive recompute fallback. This is not a bug; the column was computed upstream with
   the same runtime factor; but it means the guard on this particular function is
   defense-in-depth rather than load-bearing. The load-bearing enforcement is the required
   parameter upstream. Worth knowing so the guard is not mistaken for the primary control.

3. **The engine functions are contract-dependent, not defensive.** `compute_plan_for_subset`
   raises `KeyError` on a frame missing `SystemCategory` or `Consumption_pcs` rather than
   degrading. The pipeline always supplies the columns, so this is not a live failure, but
   an "industrial" posture would validate the input frame once at the engine boundary and
   raise a single clear error rather than a bare `KeyError` from deep inside. Low priority.

**Net:** the deep dive did not find a numerical bug in the core sizing path. It found one
half-built feature to resolve (fill-ceiling: wire or delete) and a couple of robustness
notes. Confidence in the engine is higher after this pass than before it; the risk
remains concentrated in the page, exactly where the action plan already points.

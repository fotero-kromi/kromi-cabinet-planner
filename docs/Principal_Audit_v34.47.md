# Kromi Cabinet Planner v34.47 - Principal Architecture Audit

Date: 2026-09-22. Scope: the full tree (`pages/`, `engine/`, `db/`, `ui/`, `tools/`, top-level modules, tests, CI, docs, config). Method: static reading plus runtime experiments (pytest, Streamlit AppTest page drives, a live server launch, synthetic data, mock OpenAI server). Nothing in the project was modified. Tags: **[R]** runtime-verified, **[S]** static only.

---

# Executive Summary

1. **Article numbers are not master data yet - P0.** Numbers are computed fresh on every run from row position and classification. Nothing records issued numbers. Two runs with the same KTC-ID issue the same numbers to different articles, and adding, removing or reclassifying one article renumbers others. [R] This is the most important finding because the numbers now go into production systems.
2. **The app is reachable from the LAN with no login - P0.** Streamlit binds to `0.0.0.0`; anyone on the network can browse every stored customer run, edit or delete override sets, and spend the OpenAI key. Fix: one config line. [R]
3. **Customer text reaches exports as live Excel formulas - P1.** A cell `=HYPERLINK(...)` in an uploaded file becomes a formula in Result, Article setup and the CSV. [R]
4. **The safety net is weaker than it looks - P1.** The CI workflow fails at its first gate, and the tree is not in git, so CI never runs; dependencies are unpinned and `run.bat` never upgrades them. The local release ceremony is thorough, but it is the only gate. [R]
5. **Several failures are silent - P1.** A database error drops technician overrides without a warning; failed AI batches are cached for the life of the process; numbers silently disappear from plan exports when numbering overflows; a banner-row file plans with zero consumption. [R]
6. **The engine is in good shape; the page is the debt.** `engine/` is pure, cycle-free, heavily tested and cached correctly. The 4,253-line page script (479 globals, 54 inputs before the first result) carries domain logic, scattered state and most UX friction.

The fixes for items 2, 3 and most of 5 are small. Item 1 needs a design decision and a registry table. Nothing here justifies a rewrite.

---

# Application Understanding

**Purpose.** Internal tool for a tool-management company. Staff upload a customer tool list (Excel), map its columns, and the app (a) classifies every tool (keyword heuristics, a structure-code vocabulary, optional OpenAI), (b) routes each article to KTC vending (Helix coils, Carousel slots, Lockers) or Kanban and sizes the cabinets per supply point, (c) generates 12-digit KROMI article numbers, (d) exports an Excel workbook, a PowerPoint deck and an "Article setup" sheet, and (e) archives runs in SQLite.

**Main user journeys.** Plan cabinets for a customer (upload, map, tune, run, review, correct, export). Assign article numbers only (numbering mode, since v34.44). Technician corrections via override sets. Load or recompute a stored run.

**Architecture map**

| Area | What exists |
|---|---|
| Frontend | Streamlit 1.58 multipage: `Home.py` picker, `pages/1_Kromi_Planner.py` (4,253 lines, re-executed top to bottom on every interaction), `pages/2_EGC_Planner.py` (static preview), `ui/exports_panel.py`, `ui/technician_panel.py`, `styling.py` CSS |
| Backend / domain | `engine/` (36 modules, 12.2k lines): `plan.run_plan(work, overrides, PlanParams) -> PlanResult`, `cabinet_math`, `classification` (+ tables, `kds_structure_words`), `kromi_numbering`, `workbook`, `preprocessing`, `overrides`, `invariants`, `boundary`, `deck`. AST test keeps Streamlit out |
| Storage | SQLite (`db/`, stdlib `sqlite3`, WAL, 4 SQL migrations, 12 tables), default under the user profile; `runs/file_prefs.json` (relative path); in-memory `st.cache_data` |
| APIs / integrations | OpenAI (classification, optional column mapping), PuLP/CBC solver (experimental optimizer). No inbound API |
| Auth | None |
| Background jobs | None; AI batches run in a thread pool inside the request |
| State | ~100 session-state keys, 10 cached functions, DB, prefs JSON, env |
| Config | `.env` (`OPENAI_API_KEY`), ~25 env vars read in code (2 documented), `.streamlit/config.toml` |
| Deployment | Per-user local launch on Windows via `run.bat`; releases are hand-built zips with a manual `BUILD` bump |
| Monitoring / logging | None (`logging` is never imported) |
| Error handling | 40 `except Exception` blocks (16 in the page, 21 in the engine, 16 of those swallow) |
| Testing | 1,908 test cases (1,669 functions), 25 env-gated skips, ~39 s wall |
| Build / CI | GitHub Actions workflow present but non-functional (see C4) |

**How components communicate**

```
 Browser ──websocket──> Streamlit server (0.0.0.0:8501, no auth)
                          │
                          ▼
            pages/1_Kromi_Planner.py  (script, reruns per click)
   upload → byte memo → sha → _read_sheet → column mapping → prepare_planning_base
     → pre-AI heuristics → [OpenAI thread pool, cached per batch] → post-AI safety
     → override resolution (SQLite sets) → PlanParams → run_plan (cached on content key)
     → render / fragments → ui/exports_panel → engine/workbook, engine/deck
     → db/persist_run (once per save key)
                          │                         │
                          ▼                         ▼
                engine/ (pure pandas)        SQLite (~/.kromi_cabinet_planner)
                                             runs/file_prefs.json (cwd-relative)
```

**What I could not confidently establish:** how numbers are consumed downstream (ERP import, machine DB) and whether any downstream system rejects duplicates; whether the app is ever run on a shared server; Windows firewall behaviour; Excel's own handling of the injected formulas (not opened in Excel).

---

# Architecture Assessment

**Strengths (keep).** A pure, cycle-free engine (Tarjan: 0 cycles; `engine/` imports nothing from `pages/`, `ui/`, `db/`). A single `run_plan` entry point with frozen `PlanParams`, pinned by equivalence tests. Content-addressed caching whose plan key is complete (no missing inputs found). Parameterized SQL, atomic run saves, FK cascades. Strict AI output schema, re-validated server-side. An invariants layer and export verification. A data-driven `KromiRuleset`.

**Weaknesses.**
- **God script.** The page has ~3,277 lines of top-level script, 479 module-level names, a 392-line sidebar block, 14 `st.stop()` and 8 `st.rerun()`. It still holds domain logic: AI response validation (page 309-352), `needs_ai_pack_check` (2563-2584), input normalization (2141-2176), Program-to-supply-point assignment (2235-2369). [S]
- **Wide, untyped seams.** `exports_panel.render` takes 67 keyword arguments; `build_result_workbook` takes 25 (one, `content_key`, unused) and builds ~55 metadata rows from dicts keyed like `"cabA_base"`. [S]
- **Stringly-typed vocabulary.** Mode tokens live only in a page dict (1567); the vending-cabinet set is defined 7 times; capacity 70 is stated three ways; `ui_state` stores the op-mode *display label*, so renaming a label breaks restoring old runs. [S]
- **Implicit data contract.** 84 column-name literals, 41 used across layers, no registry; invariant checks silently pass when a column is missing (`invariants.py:217, 236, 320`). [S]
- **Duplicated rules that disagree.** Four copies of the carousel-slot formula with different zero-demand handling (`cabinet_math.py:224` gives 1, `:891` and the optimizer give 0); three keyword-precedence ladders (tap vs thread-mill order differs). [S]
- **Numbering is coupled to volatile inputs.** The 2-digit code comes from ToolClass (heuristics or AI), the dimension from the first digits of whatever column is mapped as Description, the variant from row position. Any of those changes the number. [R]

**Assumptions worth challenging**

| Current assumption | Why it may be wrong / evidence | Alternative | Trade-off |
|---|---|---|---|
| Numbers can be recomputed each run | They are now written into machine and ERP master data; recompute collides and renumbers (C1) | Issue once, persist, reuse | A registry table and a "re-issue" admin path |
| Local single-user app needs no auth | Streamlit binds `0.0.0.0`; the DB holds every customer's runs (C2) | Bind to localhost; SSO proxy if shared | None for local use |
| Byte-identical golden gates prove a release is safe | They run one private workbook, outside CI, and do not cover numbering stability, security, UX or DB upgrades | Keep them, add a committed synthetic fixture to CI plus property tests | Fixture upkeep |
| One Streamlit script is fine | 4.2k lines, 479 globals; 34 tests assert on source text and freeze its shape | Thin page, `ui/` sections taking small dataclasses | Incremental refactor effort |
| Version ranges are fine because code ships as a zip | `run.bat` installs once and never upgrades; a fresh install resolves Streamlit 1.64 / openai 3.17 | Hashed lock file, venv sync on change | Periodic lock refresh |
| AI on by default improves quality | Customer data leaves the company by default, spend is uncapped, failures are cached | Off without key; explicit opt-in with cost preview | Slightly more heuristic misclassifications unless enabled |
| CHANGELOG as the design record | 232 KB, 3,855 lines, 147 undated headings; 83 version-tag comments in code | Short dated release notes + a handful of decision records | Discipline at release time |

---

# Critical Issues

**C1 - P0 - Article numbers are neither persistent nor stable** [R]
- *Location:* `engine/kromi_numbering.py` (KTC counter 1-based in row order ~319-321; variant = positional counter per (KTC-ID, code, dimension) group ~277); `engine/workbook.py:357-411`; nothing in `db/` stores `Kromi_Art_No`.
- *Evidence:* Two separate runs, KTC-ID 191: run 1 gives A1 `191138500000`; run 2 (a delta list) gives the new article A3 `191138500000`. KTC predecessors: both runs start at `191100001000`. Inserting one article shifts every later number in its group; reclassifying K1 (AI) hands K1's old number to K2. Sub-sheets (Helix_only, Carousel_only) are numbered on their own subsets and can disagree with Result; in Replicate mode one article carries different numbers per supply-point row while the uniqueness check passes.
- *Risk:* Duplicate or reassigned article master data; wrong item dispensed or billed. Incremental onboarding (a second file for an existing customer) is the natural trigger.
- *Recommendation:* An `issued_numbers` table keyed on (ktc_id, listing, code) with `UNIQUE(number)`; reuse existing numbers, allocate new ones above the highest issued per group; accept a mapped column of already-existing KROMI numbers as occupied; number once per unique article and join into every sheet; block the export on conflict. **Interim operating rule:** always number a customer's complete list in one run with one KTC-ID; never run a delta file.
- *Impact* Critical · *Effort* L · *Risk* Medium · *Confidence* High (mechanics), Medium (business exposure until downstream use is confirmed).

**C2 - P0 - No authentication, server listens on all interfaces** [R]
- *Location:* `.streamlit/config.toml` (no `server.address`); Streamlit 1.58 `DEFAULT_SERVER_ADDRESS = "0.0.0.0"` (`starlette_server_config.py:52`); `run.bat:63`.
- *Evidence:* A live launch printed a Network URL on a non-loopback IP and answered health checks there. Reachable without login: "Load a previous run" (up to 100 runs across all customers, CSV download, full recompute; page 670-783); override-set create/update (893-913), which auto-applies to the owner's next run (151-182); delete of sets and rows (`technician_panel.py:437-485`); a blank customer lists every customer's sets; AI calls on the owner's key.
- *Recommendation:* `server.address = "127.0.0.1"`, `headless = true` now. If the app is ever shared: SSO in front, owner checks on update/delete, an audit trail.
- *Impact* High · *Effort* S · *Risk* Low · *Confidence* High (Windows firewall behaviour unverified).

**C3 - P1 - Excel formula injection in every export** [R]
- *Location:* `engine/workbook.py:158-159, 189-457`, `build_article_setup_workbook`; page CSV at 643.
- *Evidence:* `Customer article No = "=1+1"` is written with `data_type 'f'`; an end-to-end page drive showed `=HYPERLINK(...)` live in Result, KTC_only, Carousel_only and Article setup; the CSV carries it raw.
- *Recommendation:* One sanitizer for every string cell (prefix `'` to leading `= + - @ \t \r`, or force `data_type "s"`), including the stored AI `reason` field; one test over all sheets.
- *Impact* High · *Effort* S · *Risk* Low · *Confidence* High.

**C4 - P1 - CI is a false safety net** [R]
- *Evidence:* The pyflakes step greps "undefined name" and matches pyflakes' own message about the star imports in `engine/constants.py:9-12` ("unable to detect undefined names"), so it exits 1 before pytest, ruff and mypy run. The working tree has no `.git`, so the workflow never triggers anyway. On Streamlit 1.6x, 19 page tests fail only because `AppTest.from_file("pages/...")` resolves relative to the test file (all pass once the path is absolute; scratch-verified). Running pytest from the parent directory gives 23 failures (cwd-relative `open()` in source-text tests).
- *Recommendation:* Gate on `ruff check --select F821`; put the project in git and let CI run; absolute page paths via a shared constant; lock file.
- *Impact* High · *Effort* S · *Confidence* High.

**C5 - P1 - Unpinned dependencies, install-once launcher** [S+R]
- *Evidence:* `streamlit>=1.32,<2.0`, `openai>=1.30` (no ceiling); dry-run resolution picks Streamlit 1.64, openai 3.17. The floor admits Streamlit < 1.54 (CVE-2026-33682, unauthenticated Windows SSRF leaking the NTLM hash), while the code already needs >= 1.37 (`st.fragment`). `run.bat:31-37` installs only if `import streamlit` fails, so upgrades never pull new dependencies. `xlsxwriter` is declared but never imported; `.xls` is accepted by the uploader but `xlrd` is absent (uncaught `ImportError`).
- *Recommendation:* Hashed lock file (pip-tools or uv), floor >= 1.54, `run.bat` syncs a venv from the lock when it changes, `pip-audit` in CI.
- *Impact* High · *Effort* S · *Confidence* High.

**C6 - P1 - Database errors silently drop technician overrides** [R]
- *Location:* page 162-184 (`except Exception: pass`), 2910 and `ui/technician_panel.py:408` (unguarded).
- *Evidence:* With a corrupt DB the run proceeds with no overrides and the caption "No stored override set for this scope yet"; the technician panel then crashes before the save step. Run_Metadata still reports overrides applied.
- *Recommendation:* Separate "no set" from "DB error"; blocking warning; record `override_source = "unavailable"`.
- *Impact* High · *Effort* S · *Confidence* High.

**C7 - P1 - Failed AI batches are cached for the life of the process** [R]
- *Location:* page 260 (`@st.cache_data`, no TTL) and 364 (failure returned as a normal value).
- *Evidence:* Mock server: one failing batch costs 9 HTTP requests (3 app x 3 SDK retries); after recovery the same batch returns the cached failure with 0 requests; an empty `results` list is cached as success.
- *Recommendation:* Raise on final failure (exceptions are not cached); `max_retries=0` on the client or fewer app attempts; treat all-missing as failure; move the call into the engine with an injected client and tests.
- *Impact* Medium-High · *Effort* S · *Confidence* High.

**C8 - P1 - Run archive: write-once per-file rows break later saves and provenance** [R]
- *Location:* `db/persist_run.py:218-233, 293`; `db/classification_reuse.py:42-62`.
- *Evidence:* A second run of the same file with a different row set (PPE sheet added, year filter) fails with "Database copy skipped (KeyError)". After an AI run, the stored classification still returns run 1's heuristic values; the snapshot labels AI results "Heuristic".
- *Recommendation:* Insert missing code rows on demand; per-run classification rows (or a supersede chain); recompute reads the run's own values.
- *Impact* High · *Effort* M · *Confidence* High.

**C9 - P1 - "Load & recompute" is not a faithful reproduction** [S+R]
- *Evidence:* Not restored: PPE sheet (widget has no key, 1639), per-class thresholds, Program-to-SP map, restock categories, header row, site, KTC-ID, apply-overrides. `applied_override_set_id` is always NULL (4217, 4221). The save-dedup key ignores build and model, so after an upgrade identical inputs are "already archived" and the new result is never stored.
- *Recommendation:* Key and capture every input; show "Restored N of M settings"; persist the applied set; add build, model and a classification hash to the save key.
- *Impact* High · *Effort* M · *Confidence* High.

**C10 - P1 - Numbers silently vanish from plan exports** [S+R]
- *Location:* `kromi_numbering.py:567-570` (`except ValueError: pass`), `workbook.py:403-406`; KTC-ID input only `max_chars=3` (page 1488-1499), prefilled "191".
- *Evidence:* A replicated 3,400-article KTC plan overflowed the 4-digit counter and the number column was simply absent; > 100 articles in one (class, dimension) group do the same. The UI still reports "Export verification passed".
- *Recommendation:* Validate KTC-ID in every mode; add omission to the export problems list; plain-language overflow message naming the group.
- *Impact* High · *Effort* S · *Confidence* High.

**C11 - P1 - Column mapping can yield blocked or meaningless runs** [R]
- *Evidence:* Substring synonyms ("jahr", "art") map one column to two fields (Year + Consumption, Code + Std/Special) and then the conflict guard blocks the run. The header-row control exists only in numbering mode: a banner-row file maps "Unnamed" columns, plans zero consumption, and Run stays enabled. A numeric code column containing blanks is read as float and exported as `12345.0` (corrupts the customer article number). Text numbers: `"1.234"` becomes 1.234, `"(5)"` bypasses the negative clamp, `"2E3"` becomes 23.
- *Recommendation:* Whole-word matching and skip columns already claimed by required fields; header row in every mode with auto-detection and a block on "Unnamed" headers; read Code as text; explicit decimal locale with a count of unparsed cells.
- *Impact* High · *Effort* S-M · *Confidence* High.

**C12 - P1 - Override-set "Update existing" can overwrite the wrong data** [S+R]
- *Evidence:* The chosen set's rows are replaced by the *newest active set for the page scope* plus new edits (page 844-903, base at 868) [S]. Scope pickers use `LIKE` substring matching: `"%"` returns all sets, `"Cust"` matched two customers [R].
- *Recommendation:* Base = chosen set; diff preview before save; exact scope matching; versioned sets with soft delete (a deactivate function already exists).
- *Impact* High · *Effort* M · *Confidence* Medium-High.

**C13 - P1 - Results UX hides the outcome** [R]
- *Evidence:* 54 inputs before the first result; any setting change hides all results behind "click Run"; the headline "Required cabinets" is item 68 of 139; the numbering-only mode still shows 29 planning controls and "Run cabinet planning".
- *Recommendation:* See UX section.
- *Impact* High · *Effort* M · *Confidence* High.

---

# Security Audit

| # | Finding | Class | Pri | Evidence |
|---|---|---|---|---|
| S1 | No auth, binds `0.0.0.0` (C2) | Confirmed vulnerability | P0 | [R] live launch |
| S2 | Formula injection in Excel and CSV exports (C3) | Confirmed vulnerability | P1 | [R] data_type `f` |
| S3 | Dependency floor admits CVE'd Streamlit on Windows; no lock; install-once launcher (C5) | Likely vulnerability on target machines | P1 | [S] |
| S4 | `showErrorDetails = false` is the legacy value for "stacktrace" in 1.58: type and stack reach the browser; page handlers print `type(e).__name__: str(e)` (360, 926, 1794, 2794, 4092, `exports_panel.py:397`) | Confirmed | P2 | [R] marshalled exception |
| S5 | Resource exhaustion: a 0.63 MB xlsx (258:1) expands to 1M rows, 113 s and 553 MB RSS in one shared process; `maxUploadSize = 200`; every distinct upload stored as a BLOB with no retention; the run picker selects BLOBs for up to 100 runs | Confirmed | P2 | [R] |
| S6 | AI spend and data egress: AI on by default (1312), "Max AI items" has no maximum (1314), up to 20 workers; AI column mapping sends 5 sample rows of *every* column (1776) | Missing control | P2 | [S] |
| S7 | Prompt injection: cell text can steer classification of other rows in its batch; the free-text `reason` is stored and exported (combine with S2); poisoned answers reused for the same file hash | Potential concern | P3 | [S] |
| S8 | Markdown injection via column names, customer, site, file name in `st.warning`/`st.markdown` (1700-1703, 2044, 603-609); no HTML because `unsafe_allow_html` is not set there | Potential concern | P3 | [S] |
| S9 | `LIKE` wildcards unescaped in scope matching (`override_sets.py:228-232`, `store.py:332-336`) | Confirmed logic flaw | P3 alone, P1 with S1 | [R] |
| S10 | Data at rest: full customer workbooks unencrypted, no retention; `runs/file_prefs.json` in the app folder; release zips built without an allow-list (a `.env` beside `Home.py` could be packaged) | Potential concern | P3 | [S] |

**Checked and not vulnerable:** SQL is parameterized everywhere (f-strings only insert fixed identifiers); XXE and billion-laughs payloads are rejected by the XML stack; no `pickle`, `eval`, `exec`, `yaml.load`, `subprocess` or `os.system` in runtime code; no runtime path built from user strings (`_safe_scope_component` restricts scopes); `unsafe_allow_html` only on constant CSS with `html.escape` on interpolations; the API key is never logged, stored or exported; XSRF/CORS defaults on.

**Attacker without authentication (LAN):** read all customers' stored runs and workbooks; alter override sets that silently shape the owner's next plan; delete sets; burn API credit; upload a decompression bomb to stall the process. **Attacker with a normal account:** there are no accounts, so identical.

---

# Performance Audit

Measured [R]:

| Input | First pass | Run | Plain rerun (per click) | Peak RSS |
|---|---|---|---|---|
| ~1k rows (golden workbook) | 2.2 s | 1.5 s | 0.45 s | - |
| 10k rows (synthetic) | 12.2 s | 8.3 s | 1.7 s | - |
| 50k rows (synthetic) | 55.6 s | 38.5 s | 6.7 s | 761 MB |

- **P2 - The optimizer re-solves on every rerun.** A collapsed `st.expander` still executes; a spy counted `solve_ktc_allocation` going from 1 to 4 calls over 3 plain reruns (`time_limit_s=20`) while `run_plan` stayed at 1. It also uses a hard-coded overfill 1.10 and pools supply points, so it can contradict the headline (showed "2 cab" vs a 4-cabinet plan). Put it behind a button, cache it on the plan key, pass the real config. [R]
- **P2 - Per-click cost grows with data** (6.7 s at 50k rows): the workbook cache key and non-fragmented sections recompute on every click. Use a cheap fingerprint for export caches and more fragments. [R]
- **P2 - Run picker loads BLOBs** (`SELECT *` in `get_file` for up to 100 runs). Project columns. [S]
- **P3 - Unbounded AI cache** (per-batch, no max_entries). Memory only; restart clears it. [S]
- Not recommended: replacing pandas or restructuring the engine for speed. Customer lists are in the hundreds to low thousands; the engine is not the bottleneck.

---

# UX/UI Audit

Where users get confused [R unless noted]:
- **Mapping semantics.** The mapped "Description" silently drives the number's dimension digits; KDS files require mapping "Bezeichnung 2" into Description (inverted naming). The overflow error speaks engine jargon and names no group or codes. Add an explicit "Dimension digits from" picker with a live preview ("0000 on 100% of rows") and bilingual labels ("Description (Bezeichnung)"). **P1**
- **Auto-detection creates a conflict, then blames the user**, citing internal bug history. One-click resolution instead of a stop. **P1**
- **Operational mode mixes four planning strategies with a non-planning tool.** Make numbering its own entry with ~6 inputs. **P1**
- **Results vanish on any setting change; headline buried; export needs an extra "Prepare downloads" click.** Keep results visible and dimmed under "Settings changed - Re-run" (auto-rerun when no AI is needed); collapse setup into a summary strip after a run; tabs for Per SP / Review / Technician / Diagnostics. **P1**
- **Irreversible mistakes:** row delete in override sets without confirmation (`technician_panel.py:479-485`); "Clear all corrections" without confirmation (383-393); hard delete of whole sets (434-456); unsaved corrections dropped silently on a new file (1465-1468) or recompute (787); threshold dialog "Cancel" disables active per-class thresholds (1053-1055); "Hide optional columns" wipes optional mappings for the session (1835-1847). **P2** [S]
- **Stale or wrong copy:** empty run picker refers to a "Save this run" checkbox that no longer exists (677-680); "File library (default)" and `./overrides/...csv` help text describe a library retired in v34.23 (713, 1373-1378); the recompute banner always claims the override library applies (977-981); "LPT greedy balancing" shown in Replicate mode (3512); "same data as PDF" (3633) after the PDF export was retired; contradictory accepted Special values (3055 vs 3177). **P2**
- **Scattered controls:** Customer in main area, Site in sidebar; a single-valued Site column silently overrides the typed site (2207-2213); KTC-ID prefilled "191" and remembered per *file name* (`run_prefs.py:68-79`). **P2**
- **AI without a key:** on by default; the user learns of the missing key only after Run, via an error block per batch. Pre-flight check and default off. **P2**
- **Accessibility:** white on the light end of the button gradient 2.83:1; header subtitle 2.12:1; focus ring 1.18:1 (`styling.py:180-297`); sidebar collapse control hidden; planogram confidence shown by fill colour only; mouse-only instructions. **P2**
- **First-time experience:** no glossary (KTC, Kanban, SP, Replicate/Partition), no sample file, no "reset to defaults"; the Home picker adds a click; stored runs cannot re-download the delivered Excel/PPTX; every distinct run is auto-saved with no rename, delete or "final" flag. **P3**

---

# Reliability Audit

| Failure | What happens today | Pri | Fix |
|---|---|---|---|
| OpenAI down / 429 / timeout | Failure cached until restart; 9 requests per attempt; worst case ~9 x 60 s per batch (C7) | P1 | Raise, fewer retries |
| DB corrupt or locked | Overrides dropped silently; technician panel crash stops the save (C6) | P1 | Explicit states |
| Migration fails midway | `executescript` (`store.py:106`) leaves a half-applied schema; every later `init_db` fails "duplicate column"; app runs without DB | P2 | Per-migration transaction, backup before migrate |
| Two first saves of the same file | 1 of 3 succeeds, 2 fail with IntegrityError | P3 | Insert-or-ignore then re-select |
| `KROMI_DB_PATH=kromi.db` (bare name) | Crash at page load (`os.makedirs('')`) | P3 | Normalize path |
| Browser refresh | Unsaved editor corrections lost (session only) | P2 | Draft autosave |
| New file after manual size fixes | Fixes carry over to the new customer's matching codes; that run is not saved, silently (2933, 3443, 4173-4178) | P2 | Reset on content change |
| Corrupt xlsx / `.xls` upload | Uncaught `BadZipFile` / `ImportError` traceback | P2 | Catch, plain message |
| Prefs JSON corrupt | Read as empty; next save wipes all entries (non-atomic write) | P2 | Temp file + replace, or move into SQLite |
| Engine upgrade | Save key ignores build, so recomputed results under a new build are never archived (C9) | P2 | Add build to key |
| Workbook sections fail | Presentation, row highlighting and Charts sheets silently omitted (`workbook.py:304, 499, 546`) while "verification passed" | P2 | Collect into problems list |

**Unknown unknowns.** 10x data: per-click latency approaches 7 s at 50k rows. Six months of maintenance: the 3,855-line CHANGELOG and 34 source-text tests make refactors expensive. Two users at once: `LIKE` scope matching lets one overwrite the other's set. Credentials leak: no spend cap on the key. Unanticipated use: delta numbering runs (C1) are the most likely misuse, and they look perfectly valid on screen.

---

# Code Quality

- **P1 - Page god script** (above). Longest functions: `technician_panel.render` 469 lines, cyclomatic complexity 91; `build_result_workbook` 388; `exports_panel.render` 351; `rebalance_cabinets` 345; `run_plan` 284. [R measured]
- **P2 - Swallowed errors:** 40 `except Exception`, 16 in the engine that `pass`, `continue` or return defaults; no logging anywhere, so none of them leave a trace. [S]
- **P2 - Stringly-typed modes and vocabulary** (7 definitions of the vending set, 2 of the "not available" sentinel, label stored instead of token). [S]
- **P2 - Duplicated rules that disagree** (carousel slots x4, keyword ladders x3). [S]
- **P2 - Facades:** `engine/__init__.py` re-exports 109 names that nothing imports; `constants.py` star imports (the cause of the CI gate failure) plus a frozen-surface test that adds friction to every new constant. [S]
- **P2 - pandas 3 breaks technician category overrides** (`overrides.py:247`: `Invalid value 'high' for dtype 'float64'`, 4 test failures on pandas 3.0.6); PuLP 4 removes the APIs the optimizer uses (827 deprecation warnings). [R]
- **P3 - Dead code:** `controls_model.py`, `heuristic_product_category(_with_listing)`, `save_overrides`, `invariants.VENDING_TYPES`, `layout.grid_dims`, unused styling constants, page shims `compute_helix_needs`/`apply_operational_mode` kept alive only by a test, the second (unreachable) empty-planning-base guard (2418 / 2463). [S grep-verified]
- **P3 - Numbering hygiene:** the step-drill override lives only in `kromi_numbering.py` (and includes "stufenfräser", sending a mill to 14); holders (20008 + dim) and accessories (20 + dim) share one variant pool, so the number cannot be decoded back; no test that the code matrix covers `TOOL_CLASS_VALID`; the v34.47 structure-word table says "regenerate" but its generator was never committed (my omission). [S]
- **P3 - Comment noise:** 83 version tags and 37 history comments in code. [S]

---

# Testing

**What exists.** 1,908 cases: ~1,540 pure engine units, ~50 DB/filesystem, 19 AppTest page drives on ~5-row synthetic files, 34 source-text tests (28 literal string or regex matches), 25 env-gated skips, 1 prompt golden. Suite ~39 s, stable, no sleeps or wall-clock asserts.

**Well protected:** number format invariants (59 tests), classification (~180), cabinet math, `run_plan` equivalence/determinism/picklability, cache contracts, override resolution, fingerprints, persistence round-trips.

**Not protected:** formula injection; number stability and cross-run uniqueness; AI failure paths (no fake client anywhere); DB upgrade from older files; malformed uploads; large inputs; concurrency; test isolation (page tests write `runs/file_prefs.json` into the tree; a developer `.env` can make page tests call OpenAI because AI defaults on; caches are not cleared between drives). The 25 skips gate the *only* real-data end-to-end run, the six page differentials, the ground-truth plan reproduction and the classifier accuracy check, so CI would never exercise them. Brittleness: `ruff format` (recommended by the README) breaks 2 source-text tests with no behaviour change.

**Missing tests, prioritized**
1. CI self-check: absolute page paths, suite runnable from any directory, a lint gate that passes.
2. Formula escaping across every export sheet, the Article setup workbook and the CSV.
3. Numbering properties: insert, delete, reorder, reclassify; cross-run uniqueness against a registry.
4. AI failure paths with a fake client: timeout, 429, malformed JSON, refusal, partial rows, no key; failures not cached.
5. DB upgrade: v1-v3 fixtures with rows migrate and load; a half-applied migration recovers.
6. Malformed uploads end in `st.error`, not a traceback (`.xls`, corrupt zip, password, merged/duplicate headers, banner rows).
7. A committed anonymised synthetic workbook (1-2k rows) with golden manifests; golden capture and differentials in CI.
8. Large inputs under a time budget (marked slow); clear messages beyond 9,999 KTC articles or 99 variants.
9. Two concurrent writers on one SQLite file.
10. Autouse isolation fixture (temp DB, temp prefs, no API key, cleared caches) plus an assert that the tree is untouched.
11. Dependency canaries: latest Streamlit, pandas 3, PuLP 4, `-W error::FutureWarning`.
12. Optimizer in the "nothing heavy on rerun" contract.

---

# Product Opportunities

**Must have**
- **Issued-number registry and incremental onboarding** (C1): reuse numbers, allocate new ones, import existing KROMI numbers, delta files safe by construction.
- **Fit to a fixed installed base.** Today's files state the installed machines (e.g. machine A: 2 Helix + 1 Carousel; machine B: 1 Helix + 1 Carousel). The planner can only *size* cabinets; "Capped" limits Carousels per supply point (page 1554-1564, `apply_carousel_cap`) but there is no Helix cap, no per-machine configuration and supply points are unnamed numbers. Needed: per machine, a fixed count of Helix and Carousel units; assign articles by demand (fast movers to Helix spirals, the rest to Carousel slots), report overflow and free capacity, output the Helix/Carousel decision per article and machine.
- **Numbering as its own flow** with a dimension-source picker, preview, KDS preset and header-row auto-detection.
- **Conflict-free mapping, header row in every mode, "results out of date" state instead of hiding results.**
- **Faithful recompute** and recorded override-set provenance.

**Should have:** saved mapping profiles per template or customer; run management (rename, delete, mark final, re-download delivered files); AI pre-flight with cost estimate; side-by-side operational-mode comparison (cheap, the plan is cached); glossary and German field labels.

**Could have:** skip the Home picker; automatic recompute on change; sample values under each mapping select.

**Probably unnecessary in the user UI:** AI batch size, parallel workers, max items, trim reasons (move to env/admin); the optimizer and classifier-quality sections (move to Diagnostics); the EGC roadmap card; `controls_model.py`.

**Merge / separate:** merge Customer, Site and KTC-ID into one "Customer" block bound to a customer record (KTC-ID should come from the customer, not the file name); split numbering and diagnostics out of the planning flow.

---

# Quick Wins

Highest value, low effort, low regression risk:
1. `server.address = "127.0.0.1"`, `headless = true`, `showErrorDetails = "none"` in `config.toml` (C2, S4).
2. One export sanitizer for formula prefixes, plus a test (C3).
3. Raise on final AI failure instead of returning; fewer retries (C7).
4. Explicit "override store unavailable" warning and metadata flag (C6).
5. Surface numbering omission and validate KTC-ID in every mode (C10).
6. Fix the CI gate (`ruff --select F821`), absolute AppTest paths, Streamlit floor >= 1.54, lock file (C4, C5).
7. Auto-detection: whole-word synonyms, skip claimed columns (C11).
8. Header row in every mode; block runs whose headers are mostly "Unnamed" (C11).
9. Read the Code column as text (C11).
10. Confirmations for row delete and "Clear all corrections"; threshold Cancel only closes the dialog; reset manual size fixes on file change.
11. AI defaults off when no key is present; cap "Max AI items".
12. Copy pass over the stale texts; darken the button gradient.
13. Temp-file-and-replace write for the prefs JSON; allow-list packaging for release zips.

---

# Strategic Improvements

1. **Number registry** with a documented issuance policy, import of existing numbers and a re-issue admin path (C1).
2. **Fixed-installed-base fitting** mode with named machines (Product).
3. **Reproducible runs:** complete input capture, per-run classifications, applied-set provenance, build in the save key (C8, C9).
4. **Page decomposition:** `ui/` sections taking small dataclasses; domain logic moved to `engine/`; an `ExportContext` replacing the 67 kwargs; convert source-text tests to behaviour tests first.
5. **Vocabulary and data contracts:** `engine/vocab.py` (str-Enums, same values), `engine/columns.py` with `require_columns` at `run_plan` entry and exit, `BucketPlan` dataclass.
6. **Operational hygiene:** git with tags and `BUILD` derived from the tag; lock file; a venv-syncing launcher; rotating file log; per-migration transactions with pre-migration backup; retention for stored workbooks.
7. **CI that means something:** committed synthetic golden fixture, differentials, dependency canaries, `pip-audit`.

---

# Target Architecture

```
pages/         thin: widgets -> PlanParams -> run_plan -> ui sections   (<1k lines)
ui/            render-only sections taking dataclasses: setup, mapping, results,
               exports (ExportContext), technician, numbering
services/      I/O without st.*: OpenAI client (injected), override resolver,
               number registry, prefs, persistence adapters
engine/        pure domain (unchanged core) + vocab.py, columns.py, report.py,
               ai_response.py, input_frame.py, installed_base.py (fitting)
db/            SQLite + SQL migrations (unchanged approach) + issued_numbers,
               per-run classifications, applied set id
```

What stays: Streamlit, pandas, SQLite with plain SQL migrations, `run_plan`/`PlanParams`/`PlanResult`, content-addressed caching, the invariants layer, `KromiRuleset`, the golden tools, the test suite. What changes: the page shrinks, I/O moves behind small service functions, vocabulary and column contracts become explicit, numbers become persistent. No ORM, no DI framework, no pydantic; dataclasses and str-Enums are enough.

---

# Migration Plan

Each step ships on its own behind the existing suite and the golden gates.

- **Phase 0 - Safety (1-2 releases):** quick wins 1-5 and 13; interim numbering rule communicated to users.
- **Phase 1 - Foundations:** git, lock file, working CI, isolation fixture, committed synthetic golden fixture; convert the 34 source-text tests to behaviour tests (prerequisite for refactoring the page).
- **Phase 2 - Data integrity:** number registry (schema migration with backup, policy decision, import of existing numbers); per-run classifications; faithful recompute; migration transactions.
- **Phase 3 - Product:** numbering as its own flow; fixed-installed-base fitting; results-out-of-date state; mapping profiles.
- **Phase 4 - Structure:** vocab and column contracts; `ExportContext`; move domain logic out of the page; split the page into `ui/` sections.
- **Phase 5 - Cleanup:** remove facades and dead code; retire the stale review document; trim version-tag comments into release notes.

---

# Prioritized Roadmap

| Priority | Issue | Impact | Effort | Risk | Confidence | Recommendation |
|---|---|---|---|---|---|---|
| P0 | Numbers not persistent, cross-run collisions, renumbering (C1) | Critical | L | Medium | High | Registry + interim one-run rule |
| P0 | No auth, binds 0.0.0.0 (C2) | High | S | Low | High | Bind localhost; SSO if shared |
| P1 | Formula injection in exports (C3) | High | S | Low | High | Central sanitizer + test |
| P1 | CI non-functional, no git (C4) | High | S | Low | High | Fix gate, git, absolute paths |
| P1 | Unpinned deps, install-once launcher, CVE'd floor (C5) | High | S | Low | High | Lock file, floor 1.54, venv sync |
| P1 | DB error drops overrides silently (C6) | High | S | Low | High | Explicit unavailable state |
| P1 | AI failures cached (C7) | Med-High | S | Low | High | Raise on failure |
| P1 | Archive write-once rows break saves/provenance (C8) | High | M | Medium | High | Per-run classifications |
| P1 | Recompute not faithful; no set provenance (C9) | High | M | Low | High | Capture all inputs |
| P1 | Numbers silently omitted; KTC-ID unvalidated (C10) | High | S | Low | High | Validate + surface |
| P1 | Mapping conflicts, header row, float codes, locale (C11) | High | S-M | Low | High | Whole-word, header row, text codes |
| P1 | Override update wrong base; LIKE scope (C12) | High | M | Medium | Med-High | Chosen base, exact scope, versions |
| P1 | Results hidden, headline buried, op-mode mix (C13) | High | M | Low | High | Stale state, summary strip, own numbering flow |
| P1 | Fixed installed base not supported | High | M-L | Medium | High | Installed-base fitting mode |
| P2 | Stack traces to browser (S4) | Medium | S | Low | High | `showErrorDetails = "none"` |
| P2 | Upload bomb, BLOB growth (S5) | Medium | S-M | Low | High | Size/ratio guard, retention |
| P2 | AI egress and spend defaults (S6) | Medium | S | Low | High | Off without key, cap, opt-in |
| P2 | Optimizer re-solves each rerun, contradicts plan | Medium | S | Low | High | Button + cache + real config |
| P2 | Half-applied migrations brick the DB | Medium | M | Low | High | Transactions + backup |
| P2 | No logging; 40 broad excepts | Medium | S | Low | High | Rotating file log |
| P2 | pandas 3 / PuLP 4 breakage | Medium | S | Low | High | Cast dtype; migrate PuLP API |
| P2 | Destructive actions without confirmation | Medium | S | Low | High | Confirm, soft delete, undo |
| P2 | Stale copy; accessibility contrast | Medium | S | Low | High | Copy pass; solid colours |
| P2 | Page god script, 67-kwarg seam, duplicated rules | Medium | M | Medium | High | Phase 4 |
| P2 | Source-text tests, skipped real-data coverage | Medium | M | Low | High | Behaviour tests, synthetic fixture |
| P2 | README and PROJECT_REVIEW out of date; 23 of 25 env vars undocumented | Medium | S | Low | High | Rewrite README, archive review |
| P3 | Dead code, facades, comment noise, generator not committed | Low | S | Low | High | Phase 5 |
| P3 | Prompt/markdown injection, data at rest | Low | S | Low | Medium | Sanitize, retention |

---

# Top 10 Things I Would Fix First

1. Bind to localhost and set `showErrorDetails = "none"` (today).
2. Communicate the interim numbering rule (one complete list per KTC-ID per run), then build the issued-number registry.
3. Central export sanitizer against formula injection.
4. Make the CI gate pass, put the project in git, add a hashed lock file with Streamlit >= 1.54 and a venv-syncing `run.bat`.
5. Explicit warning when the override store is unavailable; never run silently without overrides.
6. Stop caching AI failures.
7. Surface numbering omissions and validate the KTC-ID in every mode.
8. Mapping robustness: whole-word auto-detection, header row everywhere, Code read as text.
9. Fix "Update existing override set" and exact scope matching.
10. Faithful recompute: capture every input, store the applied override set, include build and model in the save key.

---

# Things NOT To Change

- Streamlit, pandas and SQLite with plain SQL migrations: right-sized for a per-user internal tool.
- The pure `engine/` and the AST test that keeps Streamlit out of it.
- `run_plan` / `PlanParams` / `PlanResult` and the content-addressed caching (the plan key is complete).
- Parameterized SQL, atomic run saves, FK cascades.
- The strict AI JSON schema with server-side re-validation and main-thread merge.
- The invariants layer and export verification (extend it, do not replace it).
- The 12-digit number format and the `KromiRuleset` dataclass (make it persistent, not different).
- Keyword and vocabulary tables as Python data.
- The golden and export capture tools and the breadth of the engine test suite.
- The release ceremony's discipline (red-first tests, byte-identity gates); it should move into CI, not away.

---

# Questions / Unknowns

1. How are KROMI numbers consumed downstream, and does any downstream system reject duplicates? This decides whether C1 stays P0 or is mitigated elsewhere.
2. Is the app ever run on a shared server or VM, or only on personal laptops? What is the Windows firewall policy? (C2 severity.)
3. Is sending customer tool data to OpenAI covered by a data-processing agreement? (S6.)
4. Is there a git repository outside this tree? The shipped zips contain none.
5. Excel's behaviour with the injected formulas was not tested in Excel itself; Windows runtime was not tested.
6. For the installed-base fitting: which demand measure decides Helix vs Carousel (packs/month?), what fills first when capacity runs out, and should the future machine layout (a third machine) be planned in the same run?
7. The EGC page was reviewed only for reachability, not audited in depth.

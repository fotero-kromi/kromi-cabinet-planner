# Changelog


All notable changes to the Kromi Cabinet Planner are documented here.

## [v34.60] - Quality gate passes on fresh installs and on Windows

Hotfix for the gate introduced in v34.59. Planning results and exports are
byte-identical to v34.59 (synthetic manifest unchanged).

- `tools/synthetic_golden.py`: the plan-table digests used
  `frame.to_csv(index=False)`, which ends rows with `os.linesep`, so every plan
  digest differed from the manifest on Windows. Hashing moved into
  `frame_digest(frame)`, which passes `lineterminator="\n"`. New test: the
  digest is the same with `os.linesep` set to `"\r\n"` and to `"\n"` (red
  before the fix).
- `tests/test_factor_injection_guard.py` read a source file without an
  encoding, which fails under cp1252 on Windows; it now reads UTF-8, as does
  one `.gitignore` read in `tests/test_check_tool.py`. New
  `tests/test_text_encoding.py`: no text-mode `open()` or `read_text()` in
  `engine/`, `db/`, `ui/`, `pages/`, `tools/` or `tests/` omits the encoding
  (red with the two findings before the fix).
- `requirements-dev.txt` pins `numpy<2.5`: numpy 2.5 needs Python 3.12 and its
  type stubs use the 3.12 `type` statement, so mypy (python_version 3.10)
  stopped on `numpy/__init__.pyi` on every fresh 3.12 install. Reproduced with
  numpy 2.5.3 on Python 3.12, green with 2.4.6. New contract in
  `tests/test_requirements_floor.py`.
- CI: a `windows-latest` job (Python 3.11) runs ruff, mypy and the suite;
  reported, not blocking (`continue-on-error`) until it has proven stable.
  Contract in `tests/test_ci_workflow.py`.
- Verification: 5 new contracts. `python tools/check.py --tests --base v34.59`
  green: 2,149 passed / 25 skipped / 0 failed (Python 3.11). mypy also green on
  a fresh Python 3.12 install. `python tools/synthetic_golden.py --check`
  identical.

## [v34.59] - Synthetic golden gate, one quality gate, GitHub repository

Step 0 of the code professionalization plan (docs/Code_Professionalization_Plan.md):
the safety net that lets the page be decomposed, or replaced, without changing a
result. Planning results and exports are byte-identical to v34.58.

- `tools/synthetic_golden.py` generates an invented, deterministic tool catalog
  (364 rows: drills, step drills, mills, ISO inserts, taps, reamers, holders,
  screws, abrasives, saw blades, free text; missing consumption, stock, two
  locations, system types, repeated articles) and drives the planner page
  through four scenarios: standard with cabinet consolidation; capped with two
  replicated supply points, bulk routing and forced screws; fixed configuration
  with a Program mapping, stock, lockers and the stock-based Helix promotion;
  numbering only. Each run is reduced to digests of the persisted plan tables
  and of the exported workbook (the build, timestamp and AI model rows left
  out).
- `tests/test_synthetic_golden.py` compares them with the committed
  `tests/golden/synthetic_manifest.json` in every `pytest` run, so CI now runs
  a byte-identity gate without the private customer workbook. Checked: the
  digests are identical across processes and hash seeds, and the gate fails
  on a one-number engine change and on an export-only change.
- `--update` rewrites the manifest after an intended change.
- `tools/check.py` runs every gate in one command: ruff (F821; E9, F63, F7,
  F82, F811; F401), mypy, a customer-name scan over every tracked file and a
  wording scan (em dash, banned filler words) over the lines added since
  `origin/main`; `--tests` adds the full suite. The customer names are stored
  only as salted SHA-256 digests (single words, two-word names, one
  case-sensitive name), so no file spells them; `tests/test_check_tool.py`
  runs the scan in every test run. Fixed on the way: the first draft of the
  synthetic gate's anonymity test listed the names in plain text; it now uses
  the hashed scan.
- `.gitignore` keeps every customer file type (`*.xlsx`, `*.xls`, `*.xlsm`,
  `*.csv`, `tests/fixtures/`) out of git.
- The project is a private GitHub repository. `CLAUDE.md` carries the working
  rules (argue first, tests first, no customer data, release ceremony, git and
  communication rules); `docs/` holds the roadmap, the audit, the
  professionalization plan, the rewrite decision and the domain rules;
  `.claude/settings.json` runs `tools/cloud_setup.sh` to install the
  dependencies when a Claude Code cloud session starts. Release zips now carry
  `CLAUDE.md`, `docs/` and the settings file.
- Verification: 20 new contracts (test_synthetic_golden 9, test_check_tool 10,
  test_release_packaging 1). Private golden and export gates identical to
  v34.58 (only the Build row of Run_Metadata differs).

## [v34.58] - Stock-based Helix promotion (fixed configuration)

Owner request after the first takeover check: an onboarding list lacks the
consumption of many articles the customer clearly uses (large stock), so they
get the Carousel minimum while the Helix stands half empty. With the rule off
(the default) planning results and exports are byte-identical to v34.57.

- New switch in the fixed configuration: "Stock-based Helix promotion" with
  "Stock covers (months)" (default 3). It needs the Current stock column.
- After the normal fit, per supply point, the Helix space still free (the
  headroom stays empty) takes Carousel articles whose stock implies a higher
  use: implied monthly packs = stock / VPE / months. A candidate is a KTC
  article placed in a Carousel, of size S or M (the sizes the overflow move
  already allows into a spiral), without a technician cabinet override, whose
  implied demand is above the Helix threshold and above its recorded demand.
  Highest implied demand first; each gets the spirals the normal Helix sizing
  gives for that demand and is skipped when they do not fit.
- The Carousel compartments a promotion frees go to Carousel articles that
  found no space, most used first ("Placed in the Carousel space freed by
  the stock-based Helix promotion").
- Only the machine type and the spirals change: routing, demand, the
  numbers and the other articles' places stay as they were. The article gets
  the status `Promoted` and a note with its stock and implied demand; its
  takeover maximum follows the spirals. The page reports the promotions, the
  Run_Metadata names the rule and its counts when it is on, Load & recompute
  restores both settings, and the run fingerprint moves only when it is on.
- Verification: 17 new contracts (test_stock_promotion).

## [v34.57] - Manual Helix-fit fixes work on a known workbook

Fix release. Planning results and exports are byte-identical to v34.56 for
every run without a manual size fix.

- "Treat as Helix-fit (M)" and "Select all and apply" did nothing on a
  workbook the database already knew. Since v34.53 such a workbook reuses its
  stored classifications on a fresh run, and the plan applied the manual size
  fix first and the reuse second, so the stored L/XL size came back: the fix
  was listed as active but changed no placement. The fix is now applied after
  the reuse and always wins.
- Verification: 3 new contracts (test_manual_size_fix_reuse); the page
  sequence transcribed in test_run_plan_equivalence follows the new order.

## [v34.56] - Takeover sheets per supply point; step-drill code from the structure word

Owner request after the first real fixed-configuration test. Without a stock
column mapped, planning results and exports are byte-identical to v34.55,
except the KROMI code of step drills named only in a mapped category column.

- New optional mapping "Current stock pcs". Auto-detection takes a current
  stock header (for example "AKTUELLER BESTAND 31.08.2026", "Lagerbestand",
  "Current stock") and never a minimum, maximum, safety or reorder level, a
  stock location or a stock value. Load & recompute restores it; a new file
  starts without it; mapping it moves the run fingerprint only when mapped.
- With the stock mapped, the result workbook adds one `Takeover sheet SP n`
  per supply point after the Article setup, in the columns of the KROMI
  takeover template: Cust. Prop. Art. Nr. (the customer-property number of
  the Result and Article setup sheets), Kunden Art. Nr., Bezeichnung 1 and 2
  (a mapped category column's own text, then the description), VPE, im KTC,
  am HLO, Total and Schranktyp. A separate "Download takeover list" offers
  only these sheets; the export panel shows the pieces in the KTC and at the
  HLO per supply point.
- The split: whole packs go into the KTC up to the article's maximum, the
  rest (and loose pieces) stays at the HLO. Maximum = compartments x VPE for
  a Carousel; spirals x the places one spiral of the article's size holds
  (the plan's spiral capacity: S 28, M 22, L 18, XL 12, by category when the
  size is unknown) x VPE for a Helix, keeping one spiral free for the
  reground pieces of a regrind article. Lockers (not part of the takeover
  yet), Kanban articles and articles without space hold nothing in the KTC.
- The stock of a row belongs to its supply point (with a Program mapping each
  location brings its own stock). In Replicate mode the copies share one
  stock: it fills the machines in supply-point order and the rest is listed
  once, on the first supply point's sheet. Duplicate rows of one article at
  one supply point become one line.
- The planning base sums the stock of merged rows and keeps the text of a
  mapped category column (it used to keep only the normalized category), so
  the heuristics see the customer's own words. The Result sheet shows
  `Stock_pcs` next to PackUnits when mapped.
- Numbering fix: a provided structure word "Stufenbohrer ..." (KDS
  Bezeichnung 1 mapped as the category) now sets the step-drill class, so the
  KROMI-property number carries code 14; it carried 13 whenever the
  description did not repeat the word. Threading inserts ("WSP Gewinde ...",
  structure family 806 = inserts) keep code 12, now pinned by a test.
- A planning file that carries a stock column gets it mapped automatically,
  so its workbook gains the `Stock_pcs` column and the takeover sheets; set
  the mapping to "not available" to leave them out. The export capture tool
  pins the stock unmapped and now picks the plan workbook by its label (the
  takeover download is a second workbook).
- Verification: 56 new contracts (test_takeover, test_takeover_wiring,
  test_structure_word_codes); full suite 2,104 passed / 25 skipped / 0
  failed; ruff gates and mypy (47 files) clean; golden gate identical to
  v34.55; export capture drift confined to the Run_Metadata build string.
  On the real onboarding list (664 articles, two supply points, fixed
  configuration) the stock is found automatically, the two takeover sheets
  reconcile to the file's total stock, their numbers equal the Article
  setup's customer-property numbers, and the only number changes against
  v34.55 are the five step drills (13 to 14).

## [v34.55] - Reliability: safe schema updates, a local log, no save races

Seventh roadmap release (audit reliability table). Planning results and exports
are byte-identical to v34.54.

- Schema migrations run one per transaction together with their version
  record. A failing statement rolls the migration back; it used to leave a
  half-applied schema, after which every start failed with "duplicate column"
  and the app ran without its database. Before a pending migration runs on an
  existing database, the database is copied next to itself as
  `<file>.pre-migration-v<N>-<time>.bak` (SQLite online backup, consistent in
  WAL mode). New databases need no copy.
- Errors the app catches on purpose now leave a trace: a rotating local log
  (`~/.kromi_cabinet_planner/logs/planner.log`, 1 MB x 5; `KROMI_LOG_PATH`
  moves it, `off` disables it) records the database copy being skipped, an
  unreadable override database or override set, an unreadable upload, AI
  mapping and batch failures, optimizer and deck failures, stored settings
  that could not be restored, export notes and failed export verification,
  each with its traceback where there is one. Logging never breaks the app.
- Two sessions saving the same new workbook at once no longer collide on the
  unique file hash (insert-or-ignore, then read back); one of them used to
  fail with IntegrityError.
- `KROMI_DB_PATH` set to a bare file name (for example `kromi.db`) resolves
  against the working folder instead of crashing the page at load.
- Release packaging ships the new `app_log.py` and never a database backup
  (`*.bak`); the type gate covers `app_log.py`.
- Verification: 9 new contracts (test_reliability); full suite 2,048 passed /
  25 skipped / 0 failed; golden gate identical to v34.54; export capture drift
  confined to the Run_Metadata build string.

## [v34.54] - Faithful Load & recompute (audit C9)

Sixth roadmap release. Planning results and exports are byte-identical to
v34.53; the recompute now reproduces the stored run with only the engine
changed.

- Restored on recompute (they were not): the PPE sheet, the per-class
  thresholds (switch and values), the restockable categories, the Program to
  supply point map, the site, the KTC-ID and the customer label. The PPE
  sheet, site and override toggle now have stable keys.
- The column mapping is checked at the run's header row. A file with banner
  rows above the headers (a KDS template) used to lose its whole mapping on
  recompute because the columns were read from row 1.
- The optional column mapping (Program, supplier, restocking and others) is
  no longer cleared by the new-file reset when a stored run's workbook is
  loaded; the reset still applies to a different file.
- Sheet pickers are only restored when the stored workbook still has that
  sheet. The recompute banner says "Restored N of M stored settings" and
  names any setting that could not be restored.
- Each run records the override source it applied (none, off, unsaved editor
  corrections, or the database set with its id); the set id is stored with
  the run (it was always empty). The recompute picker preselects that choice
  per run. Deleting an override set keeps the runs that used it and clears
  their link instead of failing on the database reference.
- The duplicate-save check includes the build, the AI model when AI ran, and
  a digest of the classifications. After an upgrade the same inputs are
  archived as a new run instead of "Already archived".
- Verification: 9 new contracts (test_faithful_recompute), including a full
  run, archive, load and recompute in a fresh session that must produce the
  same planning parameters. tools/golden_capture.py no longer dumps the
  duplicate-save hash (it now carries the build, so it changes every release
  by design); with that tool the per-tool, bucket and roll-up dumps are
  identical to v34.53. Full suite 2,039 passed / 25 skipped / 0 failed;
  export capture drift confined to the Run_Metadata build string.

## [v34.53] - Run archive: every run saved, each with its own classifications (audit C8)

Fifth roadmap release. Planning results and exports are byte-identical to
v34.52; only what the database keeps changes. Existing databases need no
migration: older runs keep their links and still load and recompute.

- A later run of a file that brings article codes the first run did not have
  (PPE sheet added, another year filter or header row) is now archived. It
  used to fail with "Database copy skipped (KeyError)". New codes get their
  tool record with the next line number.
- Each run links to the classifications it used. An identical earlier answer
  is shared (repeated runs add nothing); a different answer is added and
  supersedes the previous newest. So an AI run after a heuristic one is kept
  as AI: the stored run shows it, the snapshot labels it with the right source
  (it said "Heuristic"), and "Load & recompute" of any run reads that run's
  own answers instead of the file's first ones. A recompute re-applying a
  stored run's answers links to them instead of adding copies.
- A known workbook reuses the newest AI or manual answer per code, even when
  a later run classified the code heuristically.
- Technician overrides are no longer stored as the classifier's answer: an
  overridden category keeps the pre-override prediction, an overridden size is
  left for the recompute to re-derive. The run's delivered values (with the
  overrides) stay on the run. Before, a recompute without overrides still
  carried the overridden categories.
- Verification: 11 new contracts (test_run_archive), one contract updated
  (the newest classification wins for the file; the run keeps its own); full
  suite 2,030 passed / 25 skipped / 0 failed; golden gate identical to v34.52;
  export capture drift confined to the Run_Metadata build string.

## [v34.52] - Fixed configuration: fit the list into existing machines

New operational mode "Fixed configuration (existing machines)" for sites where
the machines already stand. Every other mode is byte-identical to v34.51
(golden gate identical; export capture drift confined to the Run_Metadata
build string; the real KDS file gives a cell-for-cell identical Article setup).

- Per supply point enter the Helix, Carousel and Locker A/B/C count; one
  headroom (default 10 %) is kept free in every machine. Articles reach a
  supply point the usual way (Program column mapping, or the supply-point
  mode). Tools and PPE share the machines.
- Demand follows the existing rules: KTC/Kanban split, Helix/Carousel
  preference, spirals and slots per article, restock buffers. The most used
  articles (monthly pieces, then packs, then code) are placed first.
- Overflow may move to another machine type the article physically fits
  (switchable, on by default): S/M Carousel articles into a Helix, Helix
  articles into a Carousel, locker articles to larger compartments. Moved
  articles are re-sized with the same rules the other modes use. Technician
  cabinet overrides never move.
- Articles that find no space are marked "Not placed" with the reason (for
  example "Carousel needs 3 slot(s), 0 free; too large (size L) for a Helix
  spiral") and stay in every list. Restock buffers are kept only where space
  is left, and the note says when one was not. L/XL articles the leftover
  Helix space could take are offered the "Treat as Helix-fit (M)" fix, most
  used first, only as many as fit.
- The sidebar shows only the controls that apply: capacity buffer, Carousel
  fill ceiling, consolidation, empty-cabinet threshold and Tools + PPE
  handling are hidden (their values are kept for the other modes), and the
  optimizer comparison is not offered.
- Results: a "Fit into the configured machines" section (placed / moved / not
  placed, and per supply point and machine type the capacity, usable, used and
  free space, labelled with the mapped programmes), then "Configured machines".
  The workbook adds `Fixed_Configuration` and `Not_placed`, marks not-placed
  rows red in Result and KTC_only, adds Placement_Rank / Placement_Status /
  Placement_Note, keeps not-placed articles out of Helix_only, Carousel_only
  and the planogram, and records the configuration in Run_Metadata. The run
  fingerprint, Load & recompute and the stored run settings carry the machines,
  headroom and move toggle.
- Fixed: with the Program mapping active the supply-point captions said items
  were replicated (or partitioned) across supply points; they now say the
  Program column assigns them.
- Fixed: when the Result numbers fit but the KTC successor numbers of the
  Article setup overflowed the 2-digit variant field, the sheet was left out
  of the planning workbook without a word. The export notes now say so and
  point to the Description mapping (audit C10 class).
- Decision recorded: KROMI article numbers are not stored between runs. They
  stay a per-run result, because articles move between KTC and Kanban and the
  parameters change the numbers (roadmap item C1 closed by the owner).
- Verification: 39 new contracts (test_fixed_config, test_fixed_config_wiring,
  one in test_silent_failures); full suite 2,019 passed / 25 skipped / 0
  failed; lint and type gates clean.

## [v34.51] - UX safety: ask before destroying, AI and optimizer on sensible terms

Fourth roadmap release (audit UX findings). Standard flows are byte-identical
to v34.50.

- AI fallback is on by default only when an OpenAI key is configured; without
  one the checkbox starts off and says why. Previously every batch failed
  after Run and the user learned it only then. With a key nothing changes.
  "Max AI items per run" gets an upper bound (20,000, or the configured
  default if higher) against accidental spend.
- The experimental optimizer runs on request ("Run optimizer comparison") and
  keeps its result for the current plan. A collapsed expander still executes
  its body, so it used to re-solve (up to 20 s) after every click. It now
  uses the run's own Helix overfill factor instead of the 1.10 default, and
  its caption says the comparison is pooled and before the buffer (it could
  appear to contradict the headline).
- Destructive technician actions ask first: "Clear all corrections" and
  deleting a single row of a saved override set now show a confirmation,
  like deleting a whole set already did.
- The threshold dialog gets a real "Close without changes"; switching the
  per-class thresholds off is the separate, explicit "Use standard for all"
  (the old "Cancel" silently switched them off).
- Copy corrected: the empty run list no longer points to a retired "Save this
  run" checkbox; the recompute banner states the actual override source (none,
  set #N, or the newest set for the scope); the retired file-library wording
  is gone from the override toggle and the recompute picker; the accepted
  Standard/Special values match the parser (1 = standard, 2 = special,
  yes/no, or the words); the supply-point caption describes Replicate
  correctly; the drilldown no longer refers to the retired PDF.
- Accessibility: primary buttons use the solid brand green (white text 6.4:1)
  instead of a gradient whose light end gave 2.8:1.
- Verification: 7 new contracts (test_ux_safety); full suite 1,980 passed /
  25 skipped / 0 failed; golden gate byte-identical to v34.50; export capture
  drift confined to the Run_Metadata build string.

## [v34.50] - Mapping robustness and data integrity (audit C11, C12)

Third roadmap release. Standard flows are byte-identical to v34.49, and the
real KDS onboarding file produces a cell-for-cell identical Article setup
workbook.

- Auto-detected mappings never collide (audit C11). Synonym matching stays
  substring-based (German compounds such as "Jahresverbrauch" must still read
  as consumption), but optional defaults now skip any column a required field
  (or an earlier optional field) already uses: Year no longer grabs the
  consumption column, Standard/Special no longer grabs "Artikel" via "Art".
  These collisions used to stop the run with a mapping-conflict error the
  user had not caused. New `engine.colmap.deconflict_defaults`; explicit picks
  and the conflict guard are unchanged.
- Header row in every mode (audit C11). The control moved from the
  numbering-only block to the Listings section. A sheet whose data columns
  are mostly unnamed now stops with a message naming the row that most likely
  holds the headers (`suggest_header_row`, `headers_look_misplaced`); empty
  formatted columns never trigger it, and when no better row exists it only
  warns. Previously a banner-row file mapped "Unnamed" columns in planning
  mode and planned zero consumption with Run enabled. The header row is
  captured for "Load & recompute".
- Customer article numbers stay exact (audit C11). A numeric code column
  with an empty cell was read as floats and exported as "12345.0" (including
  the Article setup's Customer article No). New `clean_code_cell`: integral
  floats keep their integer text; everything else is cleaned as before.
- Override-set scope is exact (audit C12). `list_override_sets` matched the
  typed customer/site as a substring with wildcards, so a partial or wildcard
  name offered other customers' sets for "Update an existing set". Matching
  is now exact (case-insensitive); None means no filter, "" means exactly
  "no customer", and the save dialog passes the typed text as is.
- "Update an existing set" merges onto the chosen set (audit C12). It used
  to replace the chosen set's rows with the newest set of the page's scope
  plus the edits, losing the chosen set's own corrections whenever it was
  not that newest set. New `update_override_set_with_edits`: edits win per
  field, untouched rows are kept.
- Manual size fixes belong to one file. Helix-fit size fixes carried over to
  the next file's articles with the same codes; they are now cleared when the
  file content changes (like pending corrections), the user is told how many
  corrections and fixes were discarded, and a run that is not archived
  because fixes are active says so.
- Verification: 17 new contracts (test_mapping_defaults, test_header_row,
  test_code_as_text, test_override_scope, test_size_fix_reset); full suite
  1,973 passed / 25 skipped / 0 failed; golden gate byte-identical to
  v34.49; export capture drift confined to the Run_Metadata build string.

## [v34.49] - Foundations: working CI, dependency hygiene, test portability (audit Phase 1)

Second release from the audit roadmap. No planning behaviour changes; the
standard flows are byte-identical to v34.48.

- CI gate fixed (audit C4). The undefined-name step grepped pyflakes output
  for "undefined name", which also matched pyflakes' star-import notice, so
  CI failed at its first step on every run and pytest, ruff and mypy never
  executed. It now uses `ruff check --select F821` (real undefined names
  only). A reported, non-blocking `pip-audit` step lists known
  vulnerabilities in the declared dependencies.
- Tests run anywhere (audit C4). All page drives and source reads resolve
  files through `tests/_paths.py` instead of repository-relative strings.
  Streamlit 1.6x resolves `AppTest.from_file` relative to the test file, and
  plain `open("pages/...")` depended on the working directory: 18-19 tests
  failed on a fresh install and 23 when pytest started from the parent
  folder. Verified: full suite green on Streamlit 1.58 (pinned) and 1.64,
  from the repository root and from its parent folder. A hygiene test keeps
  relative paths out.
- Dependency floors (audit C5). `streamlit>=1.54,<2.0` (earlier releases
  carry CVE-2026-33682, an unauthenticated Windows SSRF leaking the NTLM
  hash, and the app needs far newer APIs than the old 1.32 floor),
  `openai<4.0` (a new major is adopted deliberately), `defusedxml` declared
  (hardened XML parsing of uploads).
- Dependency sync on launch (audit C5). New `tools/ensure_deps.py`, called by
  `run.bat`: reinstalls whenever `requirements.txt` changed since the last
  successful install (fingerprint stamp in the user profile) or Streamlit is
  missing or below the floor. The old launcher installed only when Streamlit
  was missing, so raised floors and new packages never reached existing
  machines. A failed update never blocks a working installation.
- Unreadable uploads end in a plain message (audit reliability): a damaged or
  non-Excel file, and a legacy .xls without the optional xlrd reader, now
  explain what to do instead of raising a traceback.
- pandas 3 readiness (audit code quality): technician overrides make an
  all-empty numeric audit column text before writing a label into it (a
  FutureWarning in pandas 2, a TypeError in pandas 3). Values are identical to
  pandas 2's implicit upcast; the override suite passes with FutureWarning
  escalated to an error.
- Documentation truth pass: README architecture tree (no more modules that do
  not exist), module map, testing (real counts and timing, gated-data table),
  the actual CI gates, a configuration table of the environment variables the
  code reads, and the release packager. PROJECT_REVIEW_v34.02.md is marked as
  historical.
- Verification: 18 new contracts (test_suite_hygiene, test_ci_workflow,
  test_requirements_floor, test_ensure_deps, test_upload_errors,
  test_overrides_dtype); full suite 1,956 passed / 25 skipped / 0 failed on
  Streamlit 1.58 and 1.64 and from the parent folder; golden gate
  byte-identical to v34.48; export capture drift confined to the Run_Metadata
  build string.

## [v34.48] - Security hardening and no more silent failures (audit Phase 0)

First release from the principal audit roadmap (docs/Principal_Audit_v34.47.md).
Every change adds protection or visibility; no feature was removed, and the
standard planning flows produce byte-identical results.

- Network exposure closed (audit C2, P0). `.streamlit/config.toml` binds the
  server to this computer (`server.address = "localhost"`, browser opens the
  same alias). Streamlit otherwise listens on every interface, letting anyone
  on the network open stored customer runs, change or delete override sets
  and use the OpenAI key without a login. Deliberate sharing stays possible
  with `--server.address 0.0.0.0` (README). Verified live: loopback answers,
  the LAN address does not.
- Error details out of the browser (audit S4). `showErrorDetails = "none"`;
  the previous `false` is Streamlit's legacy spelling of "stacktrace".
- Formula-safe exports (audit C3). New `engine/export_safety.py`: every
  formula-typed cell in the plan workbook and the Article setup workbook is
  stored as text (the visible value is unchanged), and the stored-run CSV
  download apostrophe-quotes text starting with = + - @ tab or CR. Plain
  numbers and lone placeholders are untouched. Cost: under 1 s on 1.5M cells.
- Failed AI batches are no longer cached (audit C7). The batch call moved to
  `engine/ai_batch.py` (testable with a fake transport) and `ui/ai_calls.py`
  (Streamlit wrapper, same 5-tuple contract). A final failure is raised
  inside the cached function, which Streamlit never memoises, so the batch is
  asked again on the next run instead of being replayed until a restart. A
  response containing none of the batch rows now counts as a failed attempt
  (it used to be cached as a success). No backoff sleep after the last
  attempt. Prompt, schema and validation rules unchanged.
- Override database errors are reported (audit C6). An unreadable database
  used to look like "no stored override set" and the run silently used no
  technician corrections, then the technician panel crashed before the save
  step. Now: a clear warning on the run, Run_Metadata "Overrides applied"
  reads "NO - override database unreadable", the Manage panel degrades to a
  message, saving a set on top of an unreadable base is refused (it would
  have dropped the stored rows), and a recompute of a chosen set stops with
  an explanation instead of a traceback.
- KROMI numbers never vanish silently (audit C10). New
  `numbering_omission_reason()`; the plan workbook's notes (shown as a
  warning with the export) state why Kromi_Art_No and the Article setup
  sheet were left out. The KTC-ID field warns immediately in every mode when
  it is not exactly 3 digits. Skipped optional sheets (Presentation,
  Dist_Subclass, Charts) and skipped size-issue highlighting are now listed
  too instead of being swallowed.
- Remembered KTC-IDs are written atomically; a corrupt preference file is
  set aside as `file_prefs.json.corrupt-<timestamp>` instead of being
  overwritten (which lost every other file's entry).
- Release packaging from an allow-list (audit S10): `tools/package_release.py`
  refuses .env, secrets.toml, runs/, databases, caches and archives even
  inside allowed folders.
- Test isolation (audit F9): an autouse fixture gives every test its own
  preference store and database and an empty API key (a developer's .env
  cannot re-insert one). The capture tools isolate the preference store too.
  Page drives used to write remembered KTC-IDs into the repository, which
  leaked between tests.
- Verification: 30 new contracts (test_export_safety,
  test_ai_batch, test_silent_failures, test_server_config,
  test_release_packaging, test_run_prefs); full suite 1,938 passed /
  25 skipped / 0 failed; golden gate byte-identical to v34.47; export capture
  drift confined to the Run_Metadata build string.

## [v34.47] — KDS structure-code vocabulary

Field validation of a numbering run showed ~660 of the 963 official KDS
structure-code words (Bezeichnung 1) were unknown to the ProductCategory
vocabulary, so those rows fell back to text heuristics - which miscoded
countersinks (code 13 instead of 17), holder adapters (11) and extensions
(20 vs 20008).

- New `engine/kds_structure_words.py`: an exact-match table of 669
  structure-code words (keys normalized, values canonical ProductCategory
  names), generated from the official KDS structure-code list with each
  entry's own L1 family deciding the category. Checked in
  `normalize_product_category` right after the canonical-name identity and
  before any keyword matching, so compound words can never be misread by a
  substring.
- Collet entries ("... Spannzangen") map to tool_holders although the
  keyword matcher read them as accessories: the engine code matrix defines
  collet = 20008 and the structure list's L1 agrees.
- Deliberately absent: the "Weitere" free-text family, "Freitext", and
  "Entgratgabel" (deburring forks stay 'other' -> code 19, as today).
  Cells deviating from the official list keep today's behaviour.
- Effect: a KDS file mapped with ProductCategory = Bezeichnung 1 now
  classifies every official structure-code word deterministically from the
  customer's own taxonomy. Countersinks reach code 17, holder adapters,
  extensions, reductions and collets reach 20008. Files without such
  values are untouched (golden gate byte-identical; export drift confined
  to the Run_Metadata build string).
- Verification: 7 new contracts in tests/test_kds_structure_words.py;
  full suite 1,908 passed / 25 skipped / 0 failed.

## [v34.46] — Numbering mode: master-file article order

The Article setup download now follows the source file instead of the
planning-base sort.

- The numbering-only mode captures each article code's first-occurrence
  order before the planning-base dedup sorts the frame, and reorders the
  sheet with the new `order_article_setup` helper: one row per article in
  master-file order (the KTC predecessor or the Kanban number), then the
  duplicate numbers (the KTC successors, the only KROMI-property rows)
  appended after the last non-duplicate row, again in master-file order.
  Codes missing from the captured order keep their relative order at the
  end of their block; the Replaces / Replaced by linkage is unaffected.
- Scope: numbering mode only. The planning flow and the Result workbook's
  Article setup sheet are untouched, and no numbers change.
- Verification: 5 new contracts in tests/test_numbering_mode.py; full
  suite 1,901 passed / 25 skipped / 0 failed; golden gate byte-identical
  to v34.45; export capture drift confined to the Run_Metadata build
  string.

## [v34.45] — System column authoritative both ways; Article setup contract v2

Two corrections from field use of the numbering mode with a real onboarding
file.

- System column decides both directions (numbering mode): a mapped System
  type cell naming Kanban alone now forces Kanban even against a KTC
  default; KTC / Locker markers keep forcing KTC (Locker beats a Kanban
  word in the same cell, matching the planner's parse precedence). Only
  blank, flexible ("KTC or Kanban") or unrecognised cells fall back to the
  per-run default. Previously the override worked one way only - a Kanban
  cell could not win against a KTC default. Planner routing semantics are
  untouched.
- Article setup sheet contract v2 (applies to the Result workbook's sheet
  and to the numbering mode's download alike):
  - Column order: Kromi_Art_No first, then Customer article No (renamed
    from Code), Description, System, Property, Replaces, Replaced by,
    PackUnits. Listing and CabinetType are dropped.
  - Property corrected: Kanban stock is invoiced to the customer at
    delivery, so Kanban rows are now "Customer property". Only the KTC
    successor is "KROMI property"; the KTC predecessor stays
    "Customer property". The numbering-mode pair count now counts
    successors.
  - No number changes: generation, variant pools and uniqueness are
    untouched; only labels, order and column set changed.
- Verification: 4 new/updated contracts in tests/test_numbering_mode.py,
  7 updated in tests/test_article_setup.py; full suite 1,896 passed /
  25 skipped / 0 failed; golden gate byte-identical to v34.44; export
  capture drift confined to the Article setup sheet (the contract change)
  and the Run_Metadata build string.

## [v34.44] — Operational mode: Only article number assignment

A new operational mode assigns KROMI article numbers without planning any
cabinet. It is built for supplier onboarding templates whose only purpose
is to get every article its number(s).

- New op mode "Only article number assignment" (token `NumberingOnly`) in
  the operational-mode selector. In this mode the page maps only what the
  numbering needs, classification still resolves ToolClass, no cabinet is
  planned, nothing is persisted, and the run's single output is the
  Article setup sheet downloaded as its own workbook
  (`build_article_setup_workbook`, sheet "Article setup").
- Property system without a plan: since no cabinet plan exists to decide
  KTC vs Kanban, a mode control sets the default system per run (Kanban or
  KTC) and a mapped System type column overrides it per row - KTC / Locker
  markers force KTC via the existing `parse_system_type`, everything else
  keeps the default (`resolve_article_system`, new in
  `engine/kromi_numbering.py`).
- Header-row control: onboarding templates often carry banner rows above
  the real headers, so the numbering mode exposes a 1-based header-row
  input. The standard flow keeps passing row 1, so existing runs read
  their files exactly as before (`_read_sheet` now takes `header_row`).
- Consumption is optional in this mode (the column pick allows "not
  available"; unmapped consumption scaffolds to 0), and an unmapped pick
  no longer enters the rename map. Restock and program mapping are
  skipped, as in Helix mode.
- Verification: 7 new contracts in `tests/test_numbering_mode.py`
  including an end-to-end AppTest drive of the mode on a banner-row
  template; full suite 1,893 passed / 25 skipped / 0 failed; golden gate
  and export capture both byte-identical to v34.43 for the standard
  flows (zero drift outside the new mode).

## [v34.43] — Article setup sheet: dual numbering for the property lifecycle

Every KTC article now receives two KROMI numbers on a new, always-included
"Article setup" workbook sheet: the predecessor (customer property, the
existing fixed-"10" counter scheme, byte-identical to the Result sheet's
number) and the successor (KROMI property, the dimension/description scheme
Kanban already uses). Kanban articles appear once with their existing number.

- NEW `engine.kromi_numbering.build_article_setup` (pure): unique articles by
  (Listing, Code), first occurrence wins; the successor's variant CONTINUES
  the (KTC-ID, code, dimension) group's counter after every dimension-scheme
  number the full frame consumed, so one shared pool guarantees no collision
  with any Kanban number on this sheet or on the Result sheet. Predecessors
  can never collide structurally (the "10" segment is never emitted by the
  class matrix). Linkage columns Replaces / Replaced by mirror the machine's
  ersetzt/ersetztDurch fields; Property carries Customer property / KROMI
  property.
- `engine/workbook.py` writes the sheet after Carousel_only; omitted exactly
  when the Kromi_Art_No column is (invalid KTC-ID, missing ToolClass or
  description, variant overflow), and its numbers join the export
  verification's uniqueness check.
- Documented consequence: in multi-supply-point Replicate runs the sheet
  keeps each article's first-occurrence predecessor number, so the visible
  counter can carry gaps; single-SP runs stay a clean 1..N.
- Verification: 16 new contracts in tests/test_article_setup.py (RED-first);
  golden capture PRE/POST byte-identical on all three scenarios (plan math
  untouched); export capture shows the new sheet as the only drift, every
  pre-existing sheet cell-identical.

## [v34.42] — audit #2 fix release: no open risks

Every finding of the second independent audit is closed.

C1(v2), the proven divergence in the vectorized restock layer: the
per-column normalization memo keyed a dict by value, and Python's
True == 1 == 1.0 collapsed hash-equal raws into one slot, so a 1.0 cell
inherited another value's normalization instead of counting as
unrecognized. The layer now maps the normalize callable per cell, which is
the row-wise reference semantics by construction; two regression pins
cover the exact proven frame and a float64-dtype column, and the parity
pool gained numeric floats and numpy scalars, closing the generator blind
spot that let this ship. The mask architecture and its speedup are
untouched.

M1(v2), the identity model: two identities, each in exactly one role. The
byte memo keeps the file-event identity, which must exist before any
bytes are read; the mapping reset and the pending-corrections signature
moved after the digest and key on the content hash, restoring E6's
documented contract that a same-content re-upload or a same-workbook run
switch keeps the technician's mappings and unsaved corrections, while a
different file always resets. An end-to-end drive pins survive-on-same and
clear-on-different, and the v34.36 identity pin evolved to the two-role
model with an explicit assertion that no (name, size) key survives at
either site.

m2(v2): run_plan states its index precondition, raising a legible error on
duplicate row labels instead of relying on the pipeline's guarantee
implicitly; the equivalence mirror carries the same lines. m1(v2): the
dead _render_html_component leftover is deleted. m3(v2): the two local
wall-clock display dates are recorded exemptions at their sites, since a
user-facing calendar date is the product intent.

All nine database hashes, both workbook digests, the full suite, and the
extended parity harness are green and byte-identical.

## [v34.41] — structural stage 3: the technician panel is a ui module

The 463-line Technician review panel moved verbatim into
ui/technician_panel.py, and its coupling turned out to be the cleanest of
the three: eight explicit parameters, with the database module handle, its
availability flag, the save dialog, and the path resolver crossing as
values so the optional-import decision stays in exactly one place on the
page. The fragment is a thin shell; the S4 editor pin and the diff-gate
pin followed the move.

Two audit cosmetics close with this stage. The Kanban-restockable
surfacing (m2) turned out to be already satisfied: the run banner has
named the flagged Kanban count and explained that no buffer is reserved
since the restocking arc, so it closes as verified rather than changed.
The database-copy swallow now names its cause: the caption carries the
exception class, so a failed archive is diagnosable without losing the
user-friendly reassurance.

The structural project is complete: the page went from 5,342 lines and
three god-functions to 4,100 lines of orchestration with three thin
fragment shells, engine/workbook.py joined the pure engine under the
purity contract, and the ui package holds the two panels behind explicit
parameters. Every dump and both digests are byte-identical across all
three stages.

## [v34.40] — structural stage 2: the exports panel is a ui module

The 290-line Export and Presentation panel moved verbatim into the new ui
package (ui/exports_panel.py): the page fragment is a thin shell, and
every value the panel reads arrives as an explicit keyword parameter,
sixty-seven of them, which is the honest measure of the coupling the page
had hidden in closures and the ground for grouping them deliberately in a
later pass. The deck cache and the JSON key sanitizer moved in as
module-level residents; the export filename helper stays page-side and
passes as a callable, since it is bound to the upload object. The workbook
cache wrapper travelled inside the panel unchanged, so cache-key semantics
held, and the two structural pins followed the move while the behavioral
export contracts passed untouched.

A method note for the record: the free-variable analyzer that generated
the parameter list leaked the nested wrapper's parameter names into the
outer bound set and under-reported by thirteen names; pyflakes was the
ground truth that caught and completed the list. The page shrank from
4,869 to 4,562 lines. Every dump and both digests are byte-identical.

## [v34.39] — structural stage 1: the workbook builder is an engine module

First stage of the audit's standing structural project. The 374-line
result-workbook builder and its two planogram helpers moved verbatim into
engine/workbook.py; the body is Streamlit-free (verified on the syntax
tree), so it sits with the rest of the pure engine, in mypy's scope, and
on the module map. The page keeps a thin cached wrapper with the exact
original signature, so the cache-key semantics are unchanged, and the two
export contracts retargeted their spies to the moved reference. Sixteen
orphaned page imports were swept. The page shrank from 5,342 to 4,869
lines.

Engine purity is now a contract rather than a habit: a test walks every
engine module's syntax tree and forbids Streamlit imports outright. Its
first draft matched the phrase "does NOT import streamlit" inside a
docstring, which is why it reads the tree and not the text. Every dump and
both workbook digests are byte-identical, as a verbatim move must be.

## [v34.38] — the restock segment is vectorized (audit P2)

The per-row loop in run_restock_segment became layer masks: the override,
provided, and rule layers resolve as vectorized series operations, with
normalization mapped over each column's unique values so the exact
normalize_restock_flag semantics apply per distinct token. Measured on a
5,000-row adversarial frame, the segment went from 0.323 to 0.014 seconds,
a 23x speedup that removes the audit's projected per-run second at
100,000-row catalogs.

The safety net is the strongest this project uses: the row-wise original
is frozen verbatim as the parity reference in
tests/test_restock_vectorization.py, and 300 randomized adversarial trials
(junk tokens, NaN, whitespace, booleans and ints in the provided column,
Kanban and cabinetless rows, empty frames, every operational mode) require
frame equality with dtypes and exact info-counter equality against it.
That includes the subtle corners: the audit trail recorded for a
file-answered no, the double unknown count when both layers carry junk on
one row, and the Kanban flag counter. All 49 restocking contracts, the
equivalence suite, every dump, and both digests are byte-identical.

Audit P3 closes as measured-and-declined: the per-pass repr of the frozen
params grows with stored classifications on loaded runs, but at the
current 1,075-entry scale it is sub-millisecond; the re-open trigger is
reload catalogs two orders of magnitude larger, recorded here so the
decision is a fact rather than a gap.

## [v34.37] — cached distributions and the audit quick wins

Audit P1: the four distribution tables (category by items and by volume,
cabinet type, system category) are plan-keyed cached builds; a plain rerun
serves the cached frames instead of re-running four groupbys per click,
and the KTC filter folded into the cached call so the per-pass pandas cost
of this section is zero. Measured on the real customer file, plain reruns
dropped from about 0.79 to about 0.62 seconds. The workbook builder keeps
receiving the same frames, which are deterministic per plan key, so both
digests are byte-identical.

Quick wins from the audit: the deck section's optionality probe is a
truthful find_spec check instead of a decorative import; the facade
contract now forbids name collisions across the four topical constant
modules outright, closing the last-wins failure mode; the upload-digest
spy matches exact bytes rather than payload length; and the README no
longer mentions the PDF output retired in v34.25, in all four places the
audit located.

One audit note retracted with the correction on record: m4 claimed the
overrides content signature was computed per pass but consumed only by the
gated save block. Re-derivation shows the signature is part of the save
key itself, which the gate compares on every pass, so the per-pass
computation is required; replacing it for sub-millisecond savings would
churn every archived inputs hash for nothing.

## [v34.36] — audit fix release: C1, M2, M1, M3

Four findings from the independent adversarial audit, fixed in dependency
order with behavioral pins for each.

C1, the critical: the reload path could silently serve the wrong file. The
upload memo keyed on (name, size), the stored-run shim carried no content
identity, and the memo survived run switches, so two stored runs sharing a
filename and an exact byte length shared bytes and digest. Fixed at the
root: _BytesFile carries the stored content hash as its file_id (the
reload context now includes the file row's sha256, with the run id as a
fallback), a run switch drops the memo outright, and one _file_identity
expression now serves the memo, the mapping-state reset, and the
pending-corrections signature, closing the same (name, size) weakness in
the two pre-existing sites the audit flagged as the same family. The pin
crafts two parseable workbooks with identical byte lengths and different
content and proves the second reload gets its own bytes and digest.

M2, re-graded during the deep test: the page path was already guarded (an
empty Tools sheet reaches a legible "no usable rows" error, proven by an
end-to-end drive that now pins it), so the engine-side fix is precision,
not rescue: prepare_planning_base states its precondition, naming the
missing planning columns in a ValueError instead of surfacing a pandas
KeyError from inside the groupby. The check derives from the aggregation
spec itself, so it maintains itself as the spec evolves.

M1: the try/except-pass around the size-lock detector is gone; the
advisory write runs unguarded, and a pin proves a raising detector now
propagates instead of vanishing. Every dump and digest is byte-identical,
which is the referendum that the guard had been masking nothing on the
real file: removing it changed no behavior, only the failure mode.

M3: the database, not the session's last key, is now the dedup authority.
persist_run gained run_id_by_inputs_hash, migration 004 indexes the
column, and the save block looks up the hash before archiving: an A-B-A
settings round trip archives two runs, not three, proven end to end, and
the misleading cache-hit durations on duplicates disappear with the
duplicates themselves. The inputs hash is computed once and shared by the
lookup and the payload.

## [v34.35] — constants split into topical modules; vectorization measured and declined

The 1,463-line constants module split into four topical modules behind a
facade: cabinet_geometry (machine specs and capacities), sizing_factors
(reserve and overfill factors, time constants, routing enums),
override_schema (the technician override columns and valid sets), and
classification_tables (the keyword taxonomy, supplier patterns, pack
hints, and toolclass maps). constants.py re-exports the whole surface, so
every existing import keeps working unchanged; new code may import from
the topical modules directly. The split was parse-driven with a loud gate
on anything unroutable, which caught the private Locker grid-formula
helper and kept it beside the tables that call it. A facade contract
freezes the exact 78-name public surface, checks the four modules import,
and pins object identity between the facade and its sources. Every dump,
digest, and the whole suite pass byte-identical, as a pure reorganization
must.

Recorded decision, measured first: the parked classification-loop
vectorization stays declined at current scale. On a synthetic 5,000-row
catalog the deterministic loops cost 0.35 seconds total (the category
heuristics dominate), once per file and content-cached; rewriting
correctness-sensitive keyword logic to save a cache-amortized fraction of
a second fails the project's own bar. Re-open trigger: catalogs around
20,000 rows or the loops exceeding two seconds.

## [v34.34] — the Carousel fill ceiling is a run setting

The last parked engine knob reached the surface. carousel_fill_ceiling was
live, tested math threaded through the cap and the rebalancer, but nothing
above cabinet_math ever set it, so every plan ran at the 1.0 default. It
is now a real setting: PlanConfig carries it (default 1.0, reproducing the
original behavior exactly), run_plan passes it into the bucket segment as
a required argument alongside the other sizing factors, and the segment
forwards it into the per-bucket rollup, the rebalancer, and the carousel
cap. The equivalence mirror passes it at the same position. On the page it
is a number input next to the reserve factor (0.50 to 1.00): full packing
at 1.00, or operational headroom per cabinet at the cost of more cabinets.
The restore contract carries the key, the fingerprint covers the value
(read from PlanConfig, keeping the single canonical source), and
Run_Metadata names it.

Deliberate one-time drift, fully itemized: the three grand dumps moved by
the inputs_hash column alone, with every plan value proven identical, and
both workbook digests moved by exactly the one new Run_Metadata row, shown
by removing only that row and watching the digest flip. POST_v34.34 and
EXPORT_v34.34 seal the new records; per-tool and bucket dumps are
byte-identical. Six contracts pin the wiring: the config default, the
segment math responding to a lower ceiling, run_plan forwarding the config
value, fingerprint sensitivity, the restore key, and the metadata row.

## [v34.33] — execution duration persisted; engine module map

Two parked hygiene items from the roadmap backlog. The archived run now
carries how long the plan computation took: the page times the
plan-retrieval call and persists it as duration_ms, closing the gap where
the column was always None. Persistence only fires on the pass that
produced a new run, so the stored value is the compute cost, floored at
one millisecond. A contract drives a run and asserts the persisted row
carries a positive duration. The golden dumps never select the column, so
all nine hashes and both workbook digests are byte-identical.

The README gained the engine module map: one line per module, drawn from
the module docstrings, so the pure-engine surface is readable at a glance
without opening the tree.

## [v34.32] — the upload is digested once per file

The last per-click full scans of the upload are gone. The content digest
over the raw workbook bytes, and the bytes copy itself, now happen once
when a file is first seen and are memoized against the uploader's file
identity; every later script pass reuses the stored bytes and digest. A
new upload recomputes, and the reload path carries session-stable bytes
and behaves the same way. The sheet reader's cache is keyed on that digest
plus the sheet name, with the bytes underscore-prefixed, so streamlit no
longer serializes the full upload for the cache key on every pass either.

On the sample customer file these scans are cheap; the point is the
scaling, since both costs grew linearly with file size and sat on every
click. Together with the earlier releases of this arc, a plain rerun now
performs no engine execution, no export or deck builds, no editor diff
walk, no frame serialization for cache keys, and no upload scan. Two
contracts pin the release: the full upload is hashed exactly once across
the parse pass, the run pass, and plain reruns, and the sheet reader is
token-keyed. All nine database hashes, both workbook digests, and the
gated battery are byte-identical and green.

## [v34.31] — exports build on demand

The workbook and the presentation deck left the run pass. A completed run
now renders a Prepare downloads step; the click builds both artifacts,
content-cached, inside the exports fragment alone, and the prepared
downloads stay keyed to the plan: a new plan shows the Prepare step again,
so stale files are never offered. On the click pass the button itself
carries the fragment rerun and the body builds immediately, so no explicit
rerun exists and app-scope semantics stay untouched. The display
normalization block (Standard/Special and the Restockable Yes/empty
mapping) moved out of the export span so the rest of the page always sees
the same frame regardless of whether exports were prepared, and the deck
builder's presentation import moved inside the cached wrapper, keeping the
module an optional dependency with the same gating point.

Measured on the real customer file, the run pass dropped from about 3.8 to
about 2.3 seconds with the export builds deferred, and plain reruns hold
at about 0.8. The capture instrument and the export cache contract drive
the Prepare click; the cache contract's semantics tightened accordingly: a
run pass builds zero export views and zero decks, the Prepare click builds
each once, and plain reruns add zero. All nine database hashes, both
workbook digests through the new flow, and the gated battery are
byte-identical and green.

## [v34.30] — fragments: repeat-click sections rerun locally

Two result-area sections became st.fragment functions, so their widget
interactions rerun the section alone instead of the whole script: the
category distribution display (the item-count versus monthly-volume basis
radio plus the breakdown expander) and the technician review panel (the
filters, the override editor, and the saved-set management). Combined with
the v34.29 flat-key work, a browse or filter click inside these panels now
costs the section, not the full pass.

The mechanics that keep this safe: fragments read the frames from the
latest full run, so display stays consistent; widgets keep their session
keys, so restore and the drives are unaffected; and st.rerun() defaults to
app scope on this Streamlit version (verified against the installed
signature), so the apply-overrides and load paths inside the technician
panel still trigger the full recompute they always did. A structural pin
guards the wrap and forbids any fragment-scoped explicit rerun from
sneaking in. Full runs execute fragments inline, which is why the entire
suite, every drive, all nine database hashes, both workbook digests, and
the gated battery pass byte-identical.

## [v34.29] — I1 capstone: flat per-click cost

The per-click rerun cost after a completed run was measured on the real
customer file before anything was touched. The engine no longer re-executes
on a plain rerun (the earlier cache releases already hold that line), so
the residual second per click was profiled to its parts: streamlit's
generic serialization of the full work and overrides frames for the run
cache key, a presentation deck rebuilt from scratch on every script pass,
and the technician editor walking a five-hundred-row diff loop even when
nothing was submitted.

All three are gone. The run cache is now keyed by cheap content tokens: a
vectorized frame digest (engine/export_shaping.frame_token covers columns,
dtypes, and values through pandas row hashing) for each frame plus a digest
of the frozen params, computed once per pass, with the frames themselves
underscore-prefixed so streamlit never serializes them. The key cost stays
flat as customer files grow, while the content-addressing stays exact: any
change to the frames or the params is a miss, a plain rerun is a hit
returning an unpickled fresh copy. The deck build joined the cached
builders, content-keyed on its small stats bundle. The editor diff walk
sits behind the form-submit gate, with the diff list hoisted so every
consumer path stays defined.

Measured on the real file, plain reruns went from about one second to
about 0.8 with the deck and diff work removed; the structural win is the
scaling, since the removed costs grew with row count. The measurement
harness ships as tools/perf_baseline.py. Four contracts pin the capstone:
a run pass followed by plain reruns adds zero engine executions and zero
deck builds, the run cache is token-keyed with underscore-prefixed frames,
the diff walk sits behind the gate, and the frame token tracks values,
columns, and dtypes exactly. All nine database hashes, both workbook
digests, and the gated battery are byte-identical and green.

## [v34.28] — restocking handling, stage 4: the technician override

The restocking decision joined the override chain end to end, completing
the four-stage feature. restocking_override is an OVERRIDE_COLUMNS field:
apply_overrides validates the value against the recognized yes/no
spellings, writes the raw text onto the frame as Restocking_Override,
counts the change, and reports invalid values through the standard
invalid-overrides audit without applying them. The restock segment reads
the override first, so the precedence chain is complete: Override beats
Provided beats Rule beats the default, the audit trail records Override as
the source, and the segment info counts override_true alongside the other
sources. Unrecognized override cells count as unrecognized values and fall
through rather than silently deciding anything.

The technician editor carries the state: a Restocking yes/no column shows
each row's current decision (robust to the boolean frame value and the
Yes/empty display normalization), a change lands in the diff as a
restocking override, rides the pending-merge path, and saves into the
database set with the other fields; the set storage needed no schema
change, since rows are built dynamically from OVERRIDE_COLUMNS and the
loader forward-fills the column on older sets.

Golden records: all nine database hashes and both workbook digests are
byte-identical, as the release is behavior-neutral until an override is
actually written. POST_v34.28 and EXPORT_v34.28 seal the records. Five new
contracts pin the stage: column registration, apply-and-validate, segment
precedence with the Override source, a run_plan round trip from an
override row to a reserved buffer with clean invariants, and the editor
wiring.

## [v34.27] — restocking handling, stage 3: hardening

The buffer model is now guarded by invariants, archived per row, and pinned
against the optimizers. Two checks joined engine/invariants.py: the frame
check (slot counts are 0 or 1; a reserved slot implies a restockable row on
a KTC cabinet with a valid target; a named target implies a slot; Kanban
rows never carry one) runs inside verify_plan, and the bucket check (any
bucket with buffers holds at least one cabinet of the buffer's class, and
the slots the frame reserves equal, per target family, what the bucket
plans consumed) merges into the integrity report right after bucket
planning, in run_plan and in the equivalence mirror at the same position.

Persistence: migration 003 widens cabinet_calculations with restockable
and restock_slots, written per row from the frame (robust to both the
boolean value and the Yes/empty display normalization) and mapped back on
load. The golden capture's per-tool dump deliberately gained the two
columns, so the nine-hash gate is restock-aware from here on.

Adversarial pins prove the protection-by-construction claim directly: the
carousel cap spills stockpiles while the three restock columns come back
byte-identical, and the rebalancer relocates rows without touching them. A
capped end-to-end run with buffers past the hard limit raises the
exceedance flag on the affected buckets while keeping every buffer. The
additivity pin states the pure-math claim precisely: with the consolidation
off, each bucket's Carousel slots equal the baseline plus its buffers;
with it on, the consolidation legitimately reshapes the base component and
the conservation and floor invariants carry the guarantee instead.

Golden records: buckets and grand dumps are byte-identical; the three
per-tool dumps moved by exactly the two new columns, proven old-columns
identical and new columns all zero, and POST_v34.27 is the new record.
Both workbook digests are unchanged. Eight new contracts pin the stage.

## [v34.26] — restocking handling, stage 2: planogram and workbook visualization

Reserved buffer compartments are now visible everywhere the plan is read.
The planogram draws one blue cell (hex 4A90D2) per buffer, labelled with
the item code plus an (R) suffix, placed after the regular items of its
target cabinet, and the legend gained a matching Restock buffer swatch.
The layout engine carries a new cell kind channel for this: LayoutItem and
Compartment gained a kind field, the allocator sorts buffers after every
regular item of their type and copies the kind onto the cells, and the
fill resolver lets the restock kind win over the confidence palette. A
pure builder, restock_layout_items, turns the frame's restock columns into
the synthetic one-compartment items, so a frame without the feature yields
nothing and the planogram is unchanged.

The workbook views gained the columns: Restockable (displayed as Yes or
empty) and Restock_target joined the user-friendly column list, and the
trimming in user_view drops both automatically when the feature is off, so
a plan without restocking keeps its sheets exactly as before. The display
normalization runs unconditionally before the cached workbook build; a
first version accidentally sat inside the Standard/Special mapping gate,
which the restock-active evidence probe caught as raw booleans in the
KTC view, and the fix dedented it. Run_Metadata carries the restocking
snapshot: the mapped column name or off, the rule categories or off, and
the count of reserved buffer compartments.

Golden records: the nine database hashes are byte-identical through the
whole chain since v34.24. Both workbook digests moved by exactly the
itemized content: the legend cell in both configurations, three
Run_Metadata rows in both, and the Restockable display normalization in
the technical full-audit sheet (booleans become Yes or empty).
EXPORT_v34.26 is the new record. Four new contracts pin the stage: kind
propagation and buffer ordering in the allocator, the synthetic items
builder, the blue fill resolution, and the column-list membership.

## [v34.25] — PDF retired; the workbook carries everything

The per-supply-point PDF is gone. Every piece it held now lives in the
Excel workbook, most of it already did: the compact and detail tables and
the per-SP distribution and occupation blocks were on the Presentation
sheet before this release. The absorption adds the remaining pieces: a
five-metric KPI row per supply point (KTC items, Kanban items, buffered
spirals, buffered compartments, cabinets) and a subclass breakdown table in
each Presentation drilldown block, a new Charts sheet with one native pie
per supply point (slide bucket order, zero buckets filtered, each chart
referencing its own data block), and nine parameter rows completing
Run_Metadata as the full calculation snapshot the retired parameters page
used to be: per-class thresholds, special coverage, the consolidation
toggle, the empty-cabinet threshold, the screws/accessories forcing, the
regrind and system-type mappings, Description_2 usage, and the AI fallback
flag. Three pure builders shape the absorbed pieces in
engine/export_shaping.py and are pinned by tests/test_excel_report.py,
which also pins the retirement itself: no reportlab in the requirements, no
PDF machinery on the page, no PDF half in the capture instrument, and no
engine module left to import.

Removed: engine/pdf_summary.py and its contract file, the cached PDF
builder, the combined two-file download with its browser script (a single
native Excel download button replaces it), the reportlab dependency, and
the capture instrument's PDF canonicalizer, session interception, keep
path, and manifest fields. The instrument found one bug during the gate:
with the combined button gone, its fallback payload selection grabbed the
presentation deck as the workbook; the fallback is removed, so a missing
workbook now fails loudly instead of digesting the wrong file. The digest
hardening proposed in v34.24 is settled by the retirement itself.

Golden records: the nine database hashes are byte-identical to v34.24, as
the engine is untouched. Both workbook digests moved by exactly the
absorbed content, verified cell-level in the kept artifacts, and
EXPORT_v34.25 is the new record with an Excel-only manifest.

## [v34.24] — restocking handling, stage 1: core semantics

A per-item Restockable decision now drives buffer compartments. The source
is a mapped yes/no column (auto-detected by common German and English
header names) or a configurable category rule; a mapped yes or no always
beats the rule, and both beat the default of not restockable. Recognized
cell values: yes, y, ja, j, 1, x, true, wahr for yes; no, n, nein, 0,
false, falsch, and the empty cell for no. Anything else counts as no and
is reported as an unrecognized value.

A restockable vending item keeps its normal allocation and reserves one
buffer compartment: Helix and Carousel items buffer in a Carousel, Locker
items in their own locker class. Coil cabinets cannot restock, which is
why one lone Helix buffer opens the first Carousel of its supply point.
Restocking is a vending concept: Kanban rows never carry a buffer, and an
override that moves a flagged item to Kanban drops the allocation with the
move. Buffers ride the frame as separate slot columns, added on top of the
percentage capacity buffer and never inflated by it; the rebalancer and the
carousel cap operate on row stockpiles only, so a buffer can never be moved,
spilled, or reduced. In Capped mode, buffers are allowed to push the
Carousel count above the hard cap; the page then explains the exceedance
and asks for an adjusted recompute instead of dropping anything. The Helix
operational mode is incompatible with restocking, so the mapping picker and
the category control are hidden under it and the segment stays inert.

New pieces: run_restock_segment in engine/plan.py, wired after the
operational mode and before bucket planning; PlanParams.restock_categories
(a required field, following the no-defaults convention); PlanResult
carries restock_info for the page banners; compute_carousel_needs gained
extra_slots and compute_locker_needs gained per-class extras; the subset
plan reports restock_car_slots and per-class locker buffers and flags
carousel_cap_exceeded_by_restock; normalize_restock_flag lives in
engine/preprocessing.py; the Restocking column joined the prepare
passthrough list, closing the silent-drop path the passthrough comment
documents; the page gained the picker, the category multiselect, and the
results banners; cm_restock and ks_restock_categories joined the restore
registries.

Deliberate golden drift, both re-baselined with proofs: the fingerprint
grew from 55 to 57 elements (the mapped column name inside the columns
splat, plus the categories tuple), which moves inputs_hash in the three
grand database dumps; value identity was proven per dump with the hash
column excluded, and POST_v34.24 is the new record. On the export side the
technical workbook's Result_Full sheet gained the four new frame columns
(Restockable, Restockable_Source, Restock_target, Restock_slots), the only
code-caused export change; EXPORT_v34.24 is the new record. During that
gate the sealed v34.23 default-PDF digest turned out to be non-reproducible
from its own sealed code: two fresh captures from the extracted v34.23 zip
agree with each other and with the current tree but not with the sealed
value, while the other three sealed digests reproduce. The release gate was
therefore validated fresh against fresh, isolating the code delta cleanly.
Recorded here so the anomaly is not rediscovered; a digest scheme less
sensitive to stream-length and offset jitter is proposed for a later
release. The export capture instrument now also saves the workbook next to
the PDF under KROMI_EXPORT_KEEP, which is what made the byte-level
comparison possible.

Tests: tests/test_restocking.py with 32 contracts covering value
normalization, source precedence and audit trail, buffer targets per
cabinet family, Kanban exclusion, mode inertness, buffer math including
the capacity boundary and the first-Carousel forcing, run_plan end to end
with the rule and with a vend override to Kanban, and a page drive through
the mapped column to the banner. The run_plan equivalence mirror gained
the segment at the same position, and the fingerprint pins were
re-baselined for the new length and sensitivity.

## [v34.23] — file override library retired from the runtime

Database override sets are now the only runtime source. The page no longer
holds the overrides directory binding, the three file shims, or any file
reader: the resolver answers from the newest active set for the scope or
returns an empty frame, the apply caption names the database set, the scope
caption shows the raw customer and site (the database key) instead of a
sanitized folder path, the empty-source caption points at the technician
panel instead of a CSV location, and a broken database degrades to a bare
run instead of falling back to files. The engine file loader and saver
remain, documented as the foundation of tools/migrate_override_files.py,
which is the one bridge for bringing a legacy library into the database.

Upgrade note: legacy per-customer override files no longer apply at runtime.
A fresh start needs nothing. An installation that wants its old corrections
runs the migration instrument (dry run, correct the map, apply) at any time
before or after upgrading; the instrument stays functional in this build.

Collision review: golden drives never had a file library for the test scope,
so the resolver returns the same empty frame as before, proven by all nine
database hashes and all eight export digests matching the v34.22 record; the
override signature, save key, reload modes, and pending-edit precedence are
untouched and pinned; the migration instrument suite still passes against
the retained engine functions. The retirement itself is pinned structurally
and behaviorally in tests/test_override_resolution.py. 1,798 tests
collected, 1,773 passed, 25 skipped; gated battery 9/9; mypy and all ruff
gates clean.

## [v34.22] — override file-library migration instrument

tools/migrate_override_files.py moves the legacy per-customer override files
into database sets, prepared for the retirement decision without making it.
Three hard rules, each pinned by the contract tests: the database stays
authoritative, so a scope with any existing set, including a deliberately
deactivated one, is skipped and a stale file can never resurrect over newer
corrections; the operator owns the scope names, since folder names are
sanitized and lossy while the resolver matches raw names, so the dry run
writes migration_map.csv with folder-derived guesses that must be corrected
before apply; and the source files are never modified or deleted, with a
second apply pass proven to be a no-op. The dry run is the default, prints a
per-scope verdict report (CREATE, SKIP_DB_EXISTS, SKIP_EMPTY), and targets
the application's own database location by default so applied sets land
where the v34.20 resolver reads. Migrated sets carry reviewer
"file-migration" and a note with the source path and file timestamp.

tests/test_migrate_override_files.py drives a synthetic library against a
seeded database and pins the verdicts, the untouched-library guarantee, the
operator-corrected raw-name flow through to latest_override_set, idempotence,
and the pre-existing set staying untouched. 1,797 tests collected, 1,772
passed, 25 skipped; both golden gates identical to the v34.21 record; gated
battery 9/9; mypy and all ruff gates clean.

## [v34.21] — tree-wide import cleanliness in the gate

The engine-side F401 debt closes, and much smaller than the pyflakes count
suggested: ruff, the gate tool, already understands the package __init__
re-export hubs that produced most of the pyflakes findings, and reported five
real ones. Each of the five went through a consumer analysis across the whole
tree (imports through the module, attribute access, and string references
such as monkeypatch targets) before any edit: all five are standard-library
typing and dataclass helpers with zero consumers anywhere, so they are
deletions, not re-exports, and the v34.18 re-export hazard does not apply to
them. The CI unused-import gate widens from the page and the tests to the
whole tree; the __init__ hubs and the tests keep their documented per-file
exemptions in pyproject.toml.

Gates: all nine database golden hashes and all eight export digests identical
to the v34.20 record, gated battery 9/9, 1,795 tests collected, 1,770 passed,
25 skipped, mypy clean, and all three ruff gate commands pass tree-wide.

## [v34.20] — override-source consolidation (I5)

Recon found a split brain, not a style question: corrections saved from the
editor land in database override sets, but a fresh upload read only the
legacy per-customer file directory, so saved corrections never applied to the
next fresh run of the same scope, and the editor merged its diffs against a
base that diverged from the one the run applied. The default override source is
now resolved in one place, _resolve_active_overrides: the newest active
database set for the exact customer and site wins, and the file directory
remains the legacy fallback; a caption names the applied source. Both the
apply path and the editor's merge base use the resolver, so the base a
technician diffs against is always the base that applied. Precedence is
untouched and pinned: live pending edits outrank everything, a picker reload
with a chosen set applies exactly that set, and a reload with overrides
disabled applies none. A broken database never blocks a run; the resolver
falls back to the files.

Collision review: golden drives use throwaway databases with no sets and no
file library for the test scope, so the resolver returns the same empty frame
as before, proven by all nine hashes and all eight export digests matching
the v34.19 record; the override signature in the save key is computed from
the applied frame and stays content-true regardless of source; the reload
picker paths are untouched. tests/test_override_resolution.py pins the
database preference end to end through run_plan, the none-mode precedence,
and the shared-resolver wiring at both call sites. Remaining open product
decision, documented and parked: full retirement of the file directory with a
one-time migration of legacy files into database sets.

Gates: 1,795 tests collected, 1,770 passed, 25 skipped; gated battery 9/9;
mypy clean; both ruff gates clean.

## [v34.19] — lint and type gates in CI (I6)

The engine and the data layer are now mypy-clean (16 findings in 10 files
fixed, zero remaining across 37 checked sources) and the fix stays enforced:
mypy runs as a blocking CI step with its scope and strictness in
pyproject.toml, now covering both engine and db. Every fix is
behavior-preserving and was verified against the golden record: builtin
generic annotations where names were missing or lists carry optional values
(classification hits, sizing caps, plan segment counters, preprocessing info),
an explicit optional on the cabinet-math monthly override, an Any on the
regrind spiral floor whose contract is whatever int() accepts, the insert
helpers assert the lastrowid invariant instead of casting an optional, the
distribution builder re-uses its declared list types instead of re-annotating,
and the fingerprint narrows the optional program map inside its guarded
branch without changing the emitted value for any valid input (the golden
fingerprint tuple is untouched, proven by the pinned test).

The advisory ruff step in CI becomes a blocking gate with a curated rule
set: syntax errors, undefined names, and redefinitions across the whole tree,
plus unused-import cleanliness on the page and the tests. Engine-side F401
stays out of the gate by policy: the reverted v34.18 wide sweep proved that
several apparently unused imports are re-exports consumed by tests and
callers, so that hygiene lands as explicit re-export annotations, not
deletion. Tool versions are pinned exactly in requirements-dev.txt
(ruff 0.15.20, mypy 2.1.0) so the gate is reproducible.

Gates: all nine database golden hashes and all eight export-content digests
identical to the v34.18 record, gated battery 9/9 on the real file with the
historical anchor, 1,792 tests collected, 1,767 passed, 25 skipped, and all
three new gates pass locally exactly as CI runs them.

## [v34.18] — page dead-import sweep, canonical category identity, typing fix

The page's 74 unused imports are removed with a surgical rewriter verified by
a zero pyflakes count, zero undefined names, and the full battery. The same
sweep was attempted across the engine, database, and tool modules and then
deliberately reverted: pyflakes cannot see external consumers of re-exports,
and the suite proved that several apparently unused names are imported
through those modules by tests and callers. Engine-side import hygiene moves
to the lint-gate work as a ruff F401 policy with explicit re-export
annotations instead of deletion; the decision and the failed-probe evidence
are recorded here so the hazard is not rediscovered.

normalize_product_category now maps canonical category names to themselves
before any keyword logic. A mapped category column carrying the canonical
English names used to fall through the freeform synonym matcher to 'other',
losing Provided status and, where descriptions were thin, sending rows to the
AI stage for answers the file already gave. Exactly two call sites exist (the
boundary's step A and first_valid_product_category) and both are strictly
more accepting of canonical input; freeform synonym behavior is unchanged and
pinned. tests/test_normalize_canonical.py adds identity pins for every
canonical name in three casings plus synonym regressions; the boundary
contract pin is updated to the corrected Provided semantics.

The classification hit-collector gains its List[str] annotation (the known
mypy finding from the I1 move).

Gates on the final tree: all nine database golden hashes and all eight
export-content digests identical to the v34.17 record, gated battery 9/9,
1,792 tests collected, 1,767 passed, 25 skipped, pyflakes clean on the page.

## [v34.17] — reuse-by-SHA (I4)

A freshly uploaded workbook whose SHA-256 matches a stored file now reuses
the classifications stored for it: they flow through the same
stored_classifications parameter the reload path uses, so run_plan applies
them with the mechanism proven since I1, an information banner announces the
reuse, and the covered codes are subtracted from the AI candidate list so the
model is never called for rows the store already answers. Only authoritative
answers are reused (source ai or manual): heuristic, provided, and default
rows re-derive identically from the same bytes, and pinning a stored 'other'
would have blocked a later AI-enabled re-upload from improving it. The loader
is cached per database path plus digest, so isolated databases never
cross-hit. Precedence: a reload context with a classification snapshot wins
in full; a reload of an older run stored without a snapshot falls through to
the file-level store, which is the correct recovery for pre-snapshot
archives. The same covered-code subtraction now also protects reloads: a
recompute with AI enabled no longer re-sends rows whose answer the snapshot
already fixes.

Collision review: golden drives run against throwaway databases, so the path
is inert there, proven by all nine hashes matching the re-baselined v34.16
record and all eight export digests matching; persistence is already
idempotent per file (records once per file, newest classification wins), so
a reused run re-saves cleanly; the fingerprint is orthogonal (content
identity, not classification state); the AI consulted-flag audit becomes
honest for covered rows, which were previously stamped as consulted and then
overwritten. tests/test_sha_reuse.py drives the page twice against one
database and pins the reuse end to end, plus reload precedence. 1,767
collected, 1,742 passed, 25 skipped, gated battery 9/9.

## [v34.16] — content-addressed run fingerprint (I7)

FingerprintInputs gains content_sha, the SHA-256 of the uploaded bytes,
emitted in the fingerprint tuple directly after the file name and size. The
digest is computed once per rerun at the single point where the bytes
materialize on the page and is reused by the persistence layer, which already
deduplicates stored workbooks by the same digest (the duplicate hashing there
is removed). This closes the remaining stale-plan hole in the invalidation
contract: replacing a workbook's content while keeping its name and byte size
now invalidates the displayed plan, the same class of bug the fingerprint was
built to prevent.

Collision review, each surface validated: the save key becomes strictly finer
(same content is now required for two runs to deduplicate in-session); the
inputs_hash column stored per engine execution changes value by design, since
it is the digest of the save key; session survival of the fingerprint across
mapping resets is unchanged; restored archives recompute the fingerprint
fresh and follow the ordinary force-run reload flow; the content caches are
untouched, proven by frozen invocation counters across reruns.

Golden record note: the grand dump includes inputs_hash precisely so the
instrument catches save-key drift, and it caught this deliberate one. All
nine dumps are byte-identical with the identity column excluded (proven per
dump), the eight export digests are identical, and the gated battery is 9/9
with the historical anchor. The nine-hash record is re-baselined on this
build. tests: 4 new in test_fingerprint_content_sha.py including a page-level
pin that the live fingerprint carries the digest of the planned bytes; the
golden fingerprint tuple, the length pin, and the per-field sensitivity sweep
are regenerated deliberately for the new field. 1,764 collected, 1,740
passed, 25 skipped.

## [v34.15] — per-SP PDF builder extracted to the engine (I3)

build_per_sp_pdf (492 lines) moved verbatim from the page into
engine/pdf_summary.py, the 31st streamlit-free engine module. Two seams, both
documented in the module: the reportlab document class is constructed through
the platypus module attribute so the cache contracts and the export
instrument keep intercepting every build, and a build failure now raises
instead of warning from inside the engine; the page catches outside its cache
wrapper with the same warning text, so a failure is never cached and the next
rerun retries, exactly the historical behavior. reportlab stays optional: the
module exposes REPORTLAB_AVAILABLE and returns None when it is missing, and
the page imports the flag from the engine instead of guarding its own
imports. The page shrinks by 499 lines to 5,162.

tests/test_pdf_summary.py (3 tests) feeds the builder real pipeline inputs
(boundary frame through run_plan through the distribution builders) and pins
a parseable multi-page document, the missing-reportlab None path, and the
raise-through on a rendering failure.

tools/export_capture.py canonicalization completed for good: reportlab wraps
these content streams in ASCII85 on top of Flate, so the plain zlib decode
failed silently and the generated-at stamp and the build label inside the
stream text were never neutralized; every earlier PDF digest movement this
cycle traced to that one token (unequal build labels), each time confirmed
against a zero-byte difference between the trees under a frozen clock. The
decoder now falls back to ASCII85 plus Flate, and PDF digests are finally
independent of the build label, the container, and the capture session.

Proof battery: all nine database golden hashes identical; all eight
export-content digests identical between the sealed v34.14 extract and this
tree with the final canonicalizer; the gated battery is 9/9 on the real file
with the historical anchor; 1,760 tests collected, 1,735 passed, 25 skipped.

## [v34.14] — boundary heuristics extracted to the engine and cached

Steps A through D of the page's boundary (ProductCategory classification,
ToolClass derivation, insert override, SizeCategory and PackUnits resolution
with the insert pack safety net) and the post-AI final safety pass with the
default size fill moved verbatim into engine/boundary.py as two pure
functions: apply_pre_ai_heuristics and apply_post_ai_safety. The page routes
both through content-addressed st.cache_data wrappers keyed on the frame
content plus the two knobs the passes read (the pack-hint toggle and the
insert default pack size). The AI candidate selection (step E) and the AI
dispatch stay on the page between the two calls; whenever the AI stage applies
anything the frame content changes, which changes the post-pass key and
recomputes. The page shrinks by roughly 180 lines and the engine gains its
30th streamlit-free module, which also moves the last per-row heuristic loops
off the rerun path.

tests/test_boundary_cache_contract.py (8 tests) pins the branch behavior on
crafted frames (classifier resolution of blank categories, pack sizes parsed
from text hints, the insert override with the PPE exemption, provided-value
normalization, the post-pass fills), the purity, determinism, and pickle
properties the cache relies on, and the release contract itself: across a run
pass and a plain rerun each boundary pass executes exactly once. One
observation recorded for the roadmap, behavior preserved verbatim: a mapped
category column carrying the canonical English name is folded to 'other' by
normalize_product_category and re-resolved by the description classifier.

tools/export_capture.py canonicalization completed: the build label also
rides in the PDF document info outside the content streams, so it is now
neutralized in the skeleton as well; canonical digests are build-label
independent and container stable.

Proof battery: all nine database golden hashes identical; all eight
export-content digests identical between the sealed v34.13 extract and this
tree with the completed canonicalizer, plus a zero-byte difference on the PDF
between the two trees under a frozen clock; the gated battery is 9/9 on the
real file with the historical anchor; all six pipeline invocation counters
(preparation, both boundary passes, the plan, the workbook views, the PDF
document) freeze after the run pass, and a plain rerun serves byte-identical
workbook bytes. Rerun cost on the container drops from ~1.5-1.7s to ~0.7s;
the caching arc that started at ~3.4s is complete. 1,757 tests collected,
1,732 passed, 25 skipped.

## [v34.13] — negative consumption guard; main e2e sealed on the historical anchor

prepare_planning_base now clamps negative consumption to zero at entry, before
the year filter and the dedup aggregation, and reports the count in
base_info["negative_consumption_clamped"]; the page surfaces a warning when the
count is nonzero. Found on a real ERP extract whose annual quantities carried
nine credit/return artifacts: unguarded, they flowed into pack math as invalid
Target_packs (plan integrity 8/9, export verification failed), and under
deduplication the SUM aggregation would have silently folded a negative into
another row of the same key. Frames without negatives are not written to at
all, so clean data passes through with identical values and dtypes.
tests/test_negative_consumption_guard.py (4 tests) pins the clamp, the count,
the untouched pass-through, the dedup-sum protection, and the full
prepare-plan-verify chain holding all invariants with a negative input row.

The original historical ground-truth workbook (the production Result export of
2026-06-23) is available again, and both end-to-end tests pass against it on
this build: the full-pipeline test reproduces the sealed metrics exactly
(1,075 rows split across the two systems, Helix 2, Carousel 1, no error
banners) and the two-drive determinism test holds. The gated real-file battery
is now nine tests: six QA differentials, the size-fix regression, and both
e2e tests. The anchor file itself stays outside the repository.

tools/export_capture.py hardened: the PDF /ID token is written by reportlab
with a newline before the bracket, so the previous strip never fired and the
container-salted ID leaked into the digest, making PDF digests stable within a
session but not across sessions. The hardened strip makes them
container-stable; the gate for this release was additionally closed at the
byte level (zero differing PDF bytes between the sealed v34.12 tree and this
one, in-process).

Proof battery: all nine database golden hashes and all eight hardened
export-content digests identical to the sealed v34.12 record; gated battery
9/9 on the real file with the historical anchor; 1,749 tests collected,
1,724 passed, 25 skipped.

## [v34.12] — content-keyed caches on the export builders; size-fix form defect

The result-workbook build (the full ExcelWriter region: metadata, presentation
and drilldown sheets, distribution sheets, the verified Result views, listing
sheets, planogram, and amber styling) and the per-supply-point PDF build now
route through _cached_build_result_workbook and _cached_build_summary_pdf under
st.cache_data (max_entries=4). Streamlit hashes the input frames, the scalars,
and a deterministic serialization of every composite input; the Run_Metadata
timestamp and the PDF generated-at stamp are excluded from the keys, so a
cache hit serves the original build, its stamps included, because the served
bytes ARE that build. Any change to the plan, the settings, the overrides, the
KTC-ID, or the export toggles alters an input and rebuilds. The
Standard/Special export columns are now written onto the frame before the
cached build, so the frame is identical whether the build runs or a cached
copy is served. The export-verification findings and the planogram note are
returned as data and rendered by the page in the historical order.

Defect found and fixed by the new instrument: in replicate mode with more than
one supply point, any size-flagged tool crashed the page with a duplicate
element key, because the size-fix form rendered one checkbox per flagged ROW
keyed on the code alone. The form now renders one row per unique code, which
matches the per-code fix semantics. Gated regression:
tests/test_size_fix_form.py.

tests/test_export_cache_contract.py pins the release: across an initial run
pass and a plain rerun, the workbook views are augmented and the PDF document
is instantiated exactly once; a rerun serves byte-identical workbook bytes.
tools/export_capture.py is a permanent instrument that captures both export
artifacts headlessly under a frozen clock and digests them with volatile parts
neutralized (freezegun is an instrument-only dependency).

Proof battery: all eight export-content digests (two configurations, workbook
sheet values plus canonical PDF) identical before and after the rewiring; all
nine database golden hashes identical; the six QA differentials and the
deterministic e2e pass on the real file; 1,745 tests collected, 1,720 passed,
25 skipped. Rerun cost on the container drops from ~2.5s to ~1.5-1.7s; the
remainder attributes to the pre-boundary heuristic row passes (~0.6-0.8s, the
C2 roadmap item) and rendering/persistence.

## [v34.11] — content-keyed cache on the planning-base preparation

The page's call to prepare_planning_base now routes through
_cached_prepare_planning_base under st.cache_data (max_entries=4), keyed on the
content of the four arguments: the mapped frame plus the dedup mode, the year
mode, and the has-year flag. A new upload, a mapping change, the program-to-SP
assignment written into the frame, or a dedup/year toggle each alters an input
and recomputes; a plain widget rerun is a hit that returns a fresh unpickled
copy. The engine function itself is untouched, so every existing preprocessing
test keeps guarding the same object.

tests/test_prep_cache_contract.py (6 tests) pins the properties the cache
relies on (the preparation never mutates its input frame, is deterministic in
frame and info dict alike, and pickles round-trip) plus the release contract
itself: a synthetic workbook driven through the reload path shows a plain rerun
adds zero preparation calls, where before the cache it re-executed the
dedup-conflict scan every pass. That scan was the dominant per-rerun cost
(2.6s of the ~3.4s rerun on the container); the rerun now measures ~2.5s.
Rerun profiling on this build attributes the remainder to eager export building
and export shaping (~1.2s: workbook writes plus augment_for_export) and the
pre-boundary heuristic row passes (~0.6-0.8s: classify_with_evidence and the
insert safety pass), which are the next caching targets on the roadmap.

Value identity proven by the golden gate: all nine SHA-256 digests from
tools/golden_capture.py match the sealed record byte for byte, and the six QA
differentials pass on the real file. No planning number changes; 1,743 tests
collected, 1,719 passed, 24 skipped.

## [v34.10] — I1 capstone: composed run_plan engine call with a content-addressed cache

The page's deterministic planning pipeline, 590 inline lines from supply-point
assignment through the grand total, is now one pure engine function:
engine/plan.run_plan(work, overrides_df, params). The page resolves session
state, widgets, mapping choices, and I/O into a frozen PlanParams plus the
gathered override frame, makes a single call, and renders every status message
from the returned PlanResult in the historical order with the historical
content. The pack-size audit and the classification preview are snapshots taken
inside run_plan at their original mid-pipeline positions, before bucket
planning writes rebalanced routing back into the frame, so the rendered numbers
are unchanged.

The call is wrapped in st.cache_data (max_entries=4) keyed on the content of
the inputs. A plain widget rerun after a run is now a cache hit that replays
none of the pipeline: across four AppTest passes on the real 1,075-row file,
run_plan executed exactly once. A technician correction, a manual size fix, an
AI merge, or any settings change alters an input and recomputes, as before.
Rerun profiling attributes the remaining rerun cost to prepare_planning_base
(2.6s, the dedup-conflict groupby scan) and eager export building (0.75s);
both are deterministic and are the next caching targets, tracked on the
roadmap rather than folded into this release.

Equivalence is proven three ways. tests/test_run_plan_equivalence.py (19 tests)
transcribes the page's stage sequence literally as the expected side and
compares run_plan against it across four regimes (defaults; capped mode with
replication, bulk routing, forced screws, and split coverage; a technician
override set with manual fixes, stored-classification reuse, system-type and
special-to-KTC forcing, and the fit-check; Helix mode with separated listings
and partition), and pins input purity, determinism, picklability, and
PlanParams hashability. tools/golden_capture.py, new in this release, drives
three scenarios through the page's reload path on a real raw workbook (supplied
via KROMI_RAW_INPUT_XLSX), dumps the persisted plan as deterministic CSVs, and
hashes them; all nine SHA-256 digests are byte-identical before and after the
rewiring, and the harness itself was validated by two independent captures of
the sealed build producing identical digests. The six QA differentials and the
deterministic end-to-end drive pass unchanged.

The stored-classification applier, a pure dictionary lookup that the pipeline
runs as one of its stages, moved from db/classification_reuse.py into
engine/classification.py; the db module re-exports it unchanged, so its public
API is intact and the database read stays with the database. The page-local
_grand_total and _bucket_label helpers moved into engine/plan.py as
grand_total and a module-private label helper, and the preview column list is
now the shared PREVIEW_COLUMNS constant.

No planning number changes; 1,737 tests collected, 1,713 passed, 24 skipped.

## [v34.09] — audit fixes: archive key, snapshot single-sourcing, dead code, truthful CI

A full project audit at v34.08 re-verified the engine and test posture and turned up
a small set of defects outside the plan math. This release fixes all of them; no
planning number changes.

The run archive's deduplication key now derives from the full run fingerprint, the
KTC-ID, and a signature of the effective override rows, instead of a hand-picked
ten-field tuple. The old key leaned on outcome fields (total cabinets, row count)
as proxies, so two runs whose differences lay outside the tuple, such as the helix
threshold or the operational mode, collided whenever their cabinet totals matched,
and the second run was silently never archived. The override signature closes the
matching gap on the other side: the fingerprint carries only the apply-overrides
flag and the scope, so without it a run corrected in the live editor, or recomputed
against a different database set, would share its key with the uncorrected run and
never reach the archive. Three source-contract tests in
tests/test_persist_save_key.py pin the key to the fingerprint, require the
override-content signature, and ban outcome proxies, in the style of the
factor-injection guard.

The end-to-end harness seeded the value 10 into ks_pack_hint, a checkbox, where the
intent was ks_insert_pack, the insert default packing unit. Harmless today only
because both controls sit at those effective values by default; corrected so the
ground-truth comparison cannot drift if either default changes.

The run fingerprint and the PDF parameter snapshot now read the overfill and
reserve factors from PlanConfig instead of the raw widget locals. Values are
identical; the change removes the last second source for those factors, the drift
pattern behind v34.01.

Dead code removed: the page's unused render_group_popover and its controls_model
import, left behind by the reverted UX experiment (controls_model.py and its tests
stay, parked for the UX track), and the corporate CSS selector leg
[class*="css"], which matches nothing on current Streamlit.

The CI workflow previously gated on ruff format and mypy, both of which fail on the
current tree, so the badge misreported project health. It now gates on what every
shipped build verifies: a zero undefined-name pyflakes scan and the full pytest
suite, with ruff kept as a non-blocking advisory until the scheduled format and
typing pass after the run_plan work. The version matrix keeps the declared support
floor, Python 3.10 through 3.12, matching run.bat and the README; the pandas pin
below 3.0 keeps 3.10 installable. pyflakes joins requirements-dev, and a stale
dependency comment about a pickle fallback that never existed is corrected.

## [v34.08] — differential QA tests for column mappings and controls

Crystallises the headline findings of the column-mapping and control QA campaign as
a permanent gated regression suite. The campaign drove an enriched copy of a real
customer file through the page's reload path and checked every column mapping,
operational mode, sidebar control, and special feature; no defect was found. This
locks six of the highest-value findings into automated checks, so a future change
that breaks one is caught before it ships.

Six gated tests in tests/test_qa_differential.py, skipped unless the raw customer
workbook is provided through KROMI_RAW_INPUT_XLSX (no ground truth is needed, and no
customer name lives in the test). Each test builds an enriched workbook in memory
(the raw sheet plus deterministic duplicate rows and, where a feature needs one, a
synthetic auto-detectable column), drives the deterministic pipeline with an empty
stored-classification map so no model call happens, and asserts the differential
directly against the persisted plan in the database. The checks cover: deduplication
collapsing duplicate codes, the year filter keeping only the latest year, a mapped
System type column forcing its KTC-marked rows onto a vending machine, the
special-to-KTC toggle raising the KTC count, the four operational modes producing
distinct cabinet compositions, and a live technician override re-routing only the
targeted code.

Every assertion is independent of header auto-detection: a differential toggles a
control while the column mapping stays fixed across both runs, and the System type
check uses a within-run per-row correspondence rather than a remap. No engine or page
code changed; this is a test-only addition.

## [v34.07] — end-to-end pipeline verification harness

Closes the long-standing verification gap. The AppTest render smoke stops at the
upload gate and never executes the planning pipeline, so until now no automated
test exercised the page's orchestration on real data; correctness rested on the
engine unit tests plus a render check. This adds a headless end-to-end harness that
drives the page's full deterministic pipeline through the reload path: stored input
bytes and stored AI classifications are injected into session_state, the page
recomputes the run on the current engine without calling OpenAI, and the one-shot
_force_run flag pushes it past the run gate. The whole pipeline executes (demand,
sizing, routing, supply points, operational mode, bucket planning, rebalance, and
the export and presentation sections render).

Two gated tests in tests/test_e2e_pipeline.py, skipped unless both real customer
files are provided through environment variables (no customer name lives in the
test): one asserts the pipeline runs without exception, every row survives
preprocessing and splits across the two systems (1075 total), the deterministic
sizing base reproduces the ground truth (one Carousel cabinet, two Helix cabinets),
and the run reaches the Export section; the other drives the pipeline twice and
asserts the metrics are identical.

The harness was validated against a real customer Result workbook. The deterministic
sizing reproduces the ground truth exactly. The KTC/Kanban classification split
differs from that older build (312/763 here versus 364/711), which was traced to the
original run using advanced per-class thresholds and forced routing (its Result has
KTC items at zero monthly usage and Kanban items at eighty, impossible under any
single threshold) rather than the uniform threshold the harness configures. A
direct classification on the current engine returns the harness's exact split, so
the harness is faithful; the difference is the original run's parameters, not an
engine or harness defect.

This is the verification vehicle for the rest of the decomposition campaign: run it
before and after a refactor on the same engine version and the metrics must match.

No application code changed. Test-only. The suite is unchanged at 1702 passing when
the customer files are absent (the two new tests skip); 1704 when they are present.

## [v34.06] — PlanConfig: the two sizing factors become one frozen object

The first step of the configuration arc. The page used to thread the two run-time
sizing factors (helix_overfill_factor, carousel_reserve_factor) as mutable
module-level globals, read both by the factor-injecting shims and passed as
arguments to the engine segments, with the Run_Metadata export and the database
persistence reading them too. A mismatch between one of those reads and a segment
argument was the shape of the Helix overfill bug.

This introduces engine/plan_config.py with a frozen PlanConfig dataclass holding
the two factors, defaulting to the engine base constants. The page now builds one
PlanConfig from the UI inputs and reads every factor from it (eight
helix_overfill_factor and eleven carousel_reserve_factor value reads migrated),
replacing the two mutable global assignments. Because the config is frozen and
built once, every reader sees one immutable source that cannot drift after
construction. It is also the object the cached run_plan entry point will take next.

The migration is value-preserving by construction: PlanConfig is built as
PlanConfig(helix_overfill_factor=float(ui_h), carousel_reserve_factor=float(ui_c)),
exactly what the old globals computed, and each read was renamed
helix_overfill_factor to _plan_cfg.helix_overfill_factor. The engine segments and
their tests are untouched: the page still passes _plan_cfg.helix_overfill_factor
into their explicit parameters, so there is no engine-API or test churn.

The constant de-shadow guards (v33.91) caught the structural change, as designed.
They were updated to pin the new shape: the factors are built into the frozen
config from the UI and read as _plan_cfg.<name>, with a new guard asserting no bare
module global rebind can return. Five PlanConfig unit tests were added (defaults
match the constants, instances are frozen, custom values stick, value equality,
and the value-equals-old-global property).

No behavior change. Identical routing and identical plans. The suite grows from
1696 to 1702 passing.

## [v34.05] — strengthen the bucket-planning-segment test battery

A recheck and hardening pass over the v34.04 extraction. First the recheck: the
segment's three outputs all reach their consumers (bucket_plans to the grand total,
the per-bucket tabs, and the PDF; rebalance_audit_all to the audit display and the
run persistence), the audit event keys the page reads (items_moved, cabinets_before,
cabinets_after) match what the engine rebalancer produces, the call sits correctly
between bucket construction and the grand total, and no reference to the four removed
shims survives anywhere in the page, run-restore, or the database layer. Nothing was
left dangling and no logic was dropped.

Then ten functional tests were added (the segment file grows from 10 to 20 tests),
each with its expected value confirmed against the engine before being written:

- overfill_factor is threaded to the helix rollup (1.0 needs a second spiral where
  1.1 keeps one), proving the explicit parameter is forwarded rather than defaulted
- regrind floors a single-spiral helix item to two spirals
- capped mode spills S/M carousel overflow to Helix (count drops to the cap, nothing
  flagged) as distinct from the L/XL case that cannot spill and is flagged
- Helix mode flags an oversize Helix-routed tool; Carousel mode flags a locker-only
  size; the rebalancer leaves a well-utilised cabinet untouched
- mixed KTC and Kanban rows split correctly; an empty bucket list still initialises
  SizeIssue; per-bucket mutations accumulate across buckets; NaN numerics do not crash

Every engine function the segment calls already carries its own engine-level tests
(detect_size_locked_items, rebalance_cabinets, apply_carousel_cap, compute_plan_for_subset,
flag_unfit_for_mode, locker_for_size), so the firing logic is covered there while these
tests cover the segment's orchestration and parameter forwarding.

Test-only; no engine or page behavior change. The suite grows from 1686 to 1696 passing.

## [v34.04] — extract the per-bucket planning loop into the engine

The seventh and largest segment extraction of the decomposition campaign. The
per-bucket planning loop (locker consolidation, the bidirectional rebalancer, the
Carousel cap, the per-bucket plan rollup, and size-locked-item flagging) moves out
of the page and into engine/plan.py as run_bucket_planning_segment. The loop had no
display calls inside it, so the extraction is a clean compute/display split: the
segment mutates the work frame and returns the bucket plans and rebalance audit;
all rendering stays in the page below the call.

The four shims the loop called (compute_plan_for_subset, rebalance_cabinets,
apply_carousel_cap, detect_size_locked_items) injected the page's runtime sizing
factors from module-level globals. The segment takes those factors
(helix_overfill_factor, carousel_reserve_factor) as explicit parameters and forwards
them to the engine functions directly, so it reads no page state. With the loop
gone, those four shims and their _engine_ alias imports were dead and are removed,
dropping the page's factor-injecting shim count from nine to five. The two engine
helpers the loop used (parse_system_type, locker_for_size) were also stranded and
their now-unused page imports removed; apply_operational_mode and its shim stay
(it is called before the loop).

The extraction was proven faithful before wiring: stripping the three injected
factor kwargs from the segment yields a token stream identical to the original loop
body (2115 characters each). The factor-injection guard added in v34.03 covers the
segment's new direct engine calls and stays green. Ten functional tests exercise the
segment across modes (Standard / Capped / Helix / Carousel), the rebalancer,
carousel cap, locker consolidation, multi-bucket rollup, in-place write-back, and a
real-customer-file check that reproduces the raw routing base (1 carousel / 2 helix)
from the ground-truth result sheet.

Page drops from 6136 to 5970 lines. Suite grows from 1676 to 1686 passing. No
behavior change: identical routing and identical plans, now computed in a tested
engine function instead of a top-level script block.

## [v34.03] — guard test: run-time sizing factors must be forwarded, never defaulted

A first improvement out of the full project review (PROJECT_REVIEW_v34.02). Two
production bugs in this line came from calling a factor-sensitive engine function
without forwarding the run-time factor, so the engine silently used its default
constant of 1.1. A token-level diff could not see it, because the call name
matched a page shim that did inject the factor while the real call resolved to the
bare engine function.

This adds a shipped guard. It introspects engine.cabinet_math for every function
that exposes a defaulted sizing-factor parameter (overfill_factor,
helix_overfill_factor, carousel_reserve_factor) and asserts, by AST, that every
call site that could omit the factor passes it: calls in engine/plan.py (which
imports the engine functions by their real names) and calls through the page's
_engine_ aliases inside its shim bodies. The page's own shims, which carry no
factor parameter, are the injection point and are not policed.

The guard was shown to bite: replaying the reverted overfill fix on a throwaway
copy, it flags the exact omission (compute_helix_spirals_needed missing
overfill_factor at the call site); against the current code it passes. Five
factor-sensitive functions are discovered automatically, so a new one added later
is covered without editing the test. carousel_fill_ceiling and
empty_cabinet_threshold_pct are deliberately out of scope: those controls are not
yet wired into the page, so the engine off-defaults are intended; whether they
should reach the carousel cap is tracked as review item Q5.

Test-only; no engine or page behavior changes. The suite grows from 1673 to 1676
passing.

## [v34.02] — capped mode: the carousel cap is a hard limit

Bug fix from a production report: a plan capped at N carousels could still propose
N+1 once the capacity buffer was applied. The cap is enforced on the base routing
(apply_carousel_cap spills overflow into Helix), but compute_plan_for_subset then
applied the buffer to every dimension, so the buffered carousel count was computed
from inflated slots and could cross a cabinet boundary above the cap. In the field
this showed as "capped at 2" producing 3 carousels under a 10% buffer (base 1404
slots, buffered 1545, ceil(1545/720)=3).

In capped mode the page now passes buf_carousel=0.0 to the plan computation, so the
buffer no longer adds carousels beyond the cap: the carousel count is the capped
routing count, and the carousel slots reported as buffered equal the base slots.
The buffer still applies in full to Helix and Locker, which are not capped, and to
every dimension in the other modes. The compute_plan_for_subset shim gained a
buf_carousel passthrough to carry this; the engine already supported per-family
buffers, so no engine change was needed.

The fix was confirmed against the reported run: replaying that frame, the current
path reproduces 3 carousels and the fix returns 2, with Helix unchanged. Four tests
pin the behavior on a frame sized exactly to the report (1404 carousel slots, two
cabinets at base and three under a 10% buffer): the suppressed carousel count holds
at the base two and equals car_cabs_base, Helix still buffers to two cabinets, the
buffered carousel slots equal the base slots, and a regression guard keeps the
non-capped path buffering carousels as before. The suite grows from 1669 to 1673
passing; the page renders without error and the undefined-name scan stays clean.

The other half of the same report, the missing operational mode and carousel cap in
the PDF parameters, was fixed in v34.01.

## [v34.01] — show operational mode and carousel cap in the PDF parameters

Bug fix from a production report. The PDF "Calculation parameters" page is built
from a controls snapshot that omitted two fields the Excel Run_Metadata already
records: the operational mode (Standard / Helix only / Carousel only / capped) and,
in capped mode, the maximum number of carousels. A reviewer running in capped mode
could not see the cap or the mode in the PDF, only in the Excel. Both fields are
now added to the snapshot next to the carousel controls, so the PDF shows, for
example, "Operational mode: Helix + Carousel (capped)" and "Max carousels (capped
mode): 2"; non-capped runs show the mode with the cap as n/a.

This is a reporting change with no effect on the plan. It was verified by rendering
the parameters page through the same code path with a capped-mode snapshot and
extracting the PDF text to confirm both fields appear with the right values. The
engine suite is unchanged at 1669 passing; the page renders without error and the
undefined-name scan stays clean.

This fix addresses the missing-parameter half of the report. The other half, the
carousel cap interacting with the capacity buffer (a capped-at-N plan can still
report N+1 carousels once the buffer is applied), is a sizing-semantics question
under separate review before any change.

## [v34.00] — compose the override-application step into a segment

The largest composition step so far, and the first that separates a pure transform
from the interactive layer wrapped around it. The override library has two parts:
gathering the active override set (from the live editor, a database set, or the
file library, all of which read UI and session state) and then applying it and
reconciling the frame. The gathering stays on the page; the application moves into
`run_override_application_segment` in engine/plan.py. The segment snapshots the
pre-override prediction, recomputes Monthly_packs and Target_packs for touched
rows, re-derives sizing for rows whose CabinetType was explicitly forced (Helix,
Carousel, Kanban, Locker), and re-routes touched rows whose routing was not
explicitly set, since a changed PackUnits or ProductCategory can flip the
KTC/Kanban decision. It returns (frame, override_stats, rerouted_flips); the page
keeps the result captions and the re-route notice.

The extraction was held to the working code two ways. A whitespace- and
comment-insensitive comparison of the segment body against the page block showed
them identical except for where rerouted_flips is initialised, which the segment
does earlier because it returns the value; the downstream notice still fires under
the identical condition. A full-frame golden across every path (each forced type,
the re-route, an empty no-op) matched a reference for both the default and a
non-default overfill factor.

That golden surfaced a real defect. The page block called a page-local
compute_helix_spirals_needed shim that injects the run-time helix_overfill_factor;
a direct port would have called the bare engine function at its 1.10 default, so a
forced-Helix row under a non-default overfill would have been sized with the wrong
spiral count. The segment now forwards helix_overfill_factor explicitly, matching
the shim. The current default is 1.10, so installed behaviour is unchanged, but
the fix removes a latent wrong-sizing path. With the inline block gone, the dead
page imports and the now-unused shim were removed (decide_spiral_capacity,
route_and_size_row, regrind_spiral_floor, threshold_for_row, apply_overrides, and
the compute_helix_spirals_needed shim with its aliased import).

Twelve tests are added covering each forced-routing path, the re-route, an empty
no-op, the touched-row count, the Monthly_packs recompute, the pre-override
snapshot, a guard that forced-Helix sizing tracks the run-time overfill factor,
and a full-frame golden at two overfill factors, plus a real-data no-op. The suite
grows from 1657 to 1669 passing; the page renders without error and the
undefined-name scan stays clean.

## [v33.99] — compose the supply-point step into a segment

Fourth composition step, completing the cleanly-separable pure pipeline. The
supply-point assignment and its consumption-conservation guard are folded into
`run_supply_point_segment` in engine/plan.py. Replicate mode duplicates each item
across the supply points at 1/N consumption; partition mode assigns each item to
one supply point, balanced by consumption; either way total consumption must be
preserved. The segment runs the assignment, checks before/after totals, and
returns (frame, conservation_issues) so the page surfaces a failure and the
replicate-mode caption.

The segment was proven identical to the inline block on real customer data across
both modes and one and three supply points, frame-for-frame, with the same
conservation result (replicate at three supply points correctly triples the row
count). The now-unused page imports of `assign_supply_points` and
`check_supply_point_conservation` were removed; `check_kromi_uniqueness`, which
shared an import line, stays.

Six tests are added: partition and replicate each equal the inline block,
replicate multiplies the rows, a single supply point is an identity in count,
conservation holds on a valid split, and a real-data check of both modes. The
suite grows from 1651 to 1657 passing; the page renders without error and the
undefined-name scan stays clean.

This is the last pipeline step that folds cleanly. The remaining deterministic
steps are interleaved with the interactive override-library application and the
per-bucket planning loop, which depend on UI state; composing a single run_plan
entry point over them needs the override application separated from override
gathering first, a larger and correctness-sensitive change tracked separately.

## [v33.98] — compose the bulk-routing step into a segment

Third composition step toward run_plan. The optional bulk-routing block, both its
enabled and disabled paths, is folded into `run_bulk_routing_segment` in
engine/plan.py. The block carried no UI, so the whole if/else moves: when enabled,
apply_bulk_routing consolidates high-volume item families onto bulk vending and
returns its stats; when disabled, the segment fills the audit columns the rest of
the pipeline reads (ItemFamily, VendMode, VendBlockReason, and the pre-route
snapshots) with no-routing defaults, preserving any technician VendMode override.
The page now calls the segment and unpacks (frame, stats) in one line.

The segment was proven identical to the inline code on real customer data: the
disabled path matches a verbatim copy of the old else-branch frame-for-frame with
zeroed stats, and the enabled path matches apply_bulk_routing exactly. With the
inline calls gone, the now-unused page imports of `detect_item_family` and
`apply_bulk_routing` were removed.

Eight tests are added: disabled equals the inline else-branch, enabled equals
apply_bulk_routing, the audit columns get created, stats come back zeroed when
disabled, VendMode defaults to Vending, an existing VendMode override is
preserved, the pre-route snapshots match the sized values, and a real-data check
of both paths. The suite grows from 1643 to 1651 passing; the page renders without
error and the undefined-name scan stays clean.

## [v33.97] — compose the two forcing-override steps into a segment

Second composition step toward run_plan. The two forcing-override steps, System
type and special-to-KTC, are folded into `run_routing_override_segment` in
engine/plan.py. They share the same routing parameters and both pin the rows they
force so later bulk routing and consolidation leave them alone; System type runs
first and wins over special. Each step runs only when its flag is set, and the
segment returns the per-step counts so the status captions stay in the page,
unchanged. The page now computes the two flags from the mapped columns and the
toggle, calls the segment once, and renders the same captions from the returned
counts.

The segment was proven identical to the inline sequence across all four flag
combinations on a synthetic frame that exercises both forcing paths (frame and
counts both byte-for-byte), and as a no-op on real customer data, which carries
neither column. With the inline calls gone, the now-unused page imports of
`apply_system_type` and `force_special_to_ktc` were removed.

This shipped after a full static audit of the codebase prompted by the two latent
undefined names found in v33.96. The audit confirmed those were the only bugs of
their class: zero undefined names, zero call-signature mismatches across 178
engine names and 43 page functions, zero use-before-assignment (every flag from
the heuristic proved a false positive), and every module imports and compiles.
The undefined-name scan is part of the ceremony now and stays clean.

Eight tests are added: both flags equals inline, each flag alone, neither as a
no-op, the counts shape, System-type-wins-over-special, in-place mutation, and a
real-data no-op. The suite grows from 1635 to 1643 passing; the page renders
without error.

## [v33.96] — compose the demand and sizing segments; fix two latent undefined names

First step of the run_plan composition. The two contiguous runs of pure pipeline
stages are now composed into a new engine/plan.py, the future home of a single
run_plan entry point. `run_demand_segment` runs demand arithmetic then the base
KTC/Kanban decision; `run_sizing_segment` runs cabinet-type assignment, the
optional dimensional fit-check, and physical sizing, taking the fit-check
condition as a flag so the Fit_* columns are created only when a dimensions
column was mapped. Both are pure, with no Streamlit dependency. The rest of the
pipeline, the parts still interleaved with previews, stats, and conservation
checks, moves into segments in later steps, and the cache capstone lands once the
whole pipeline is one function. Both segments were proven frame-identical to their
inline sequences on real customer data, including with and without the fit-check.

Wiring the sizing segment surfaced a latent bug. A static undefined-name scan,
now a standing check, found that the page had been calling `assign_physical_sizing`
without importing it since that function was extracted, so a real planning run
that reached the sizing step would have raised NameError. The headless render
smoke and the engine tests never caught it because neither executes that page
path. Routing the call through the segment, which imports the function itself,
fixes it. The same scan found a second undefined name, `_split_coverage`, a flag
the coverage-status caption and the run metadata both read; it was restored with
the same test compute_demand uses (a Standard/Special column survived and the
special coverage differs from the standard one). The scan is now clean across the
page and every engine module.

Fourteen tests are added: each segment equals running its stages by hand, with
and without the fit-check, preserves rows and index, leaves the input frame
untouched, adds the expected columns, honours the reserve factor, chains to a
plan, and a real-data check that matches the inline sequence and reaches the
known ground-truth plan (2 carousel + 1 helix). The suite grows from 1621 to 1635
passing; the page renders without error.

## [v33.95] — bundle AI-run diagnostics into a dataclass

Third sub-slice of the classification orchestration. The loose counters the wave
loop accumulated, batches and items run, failures, missing responses, input and
output tokens, and per-batch durations, are now one `AIRunDiagnostics` dataclass
in engine/ai_classifier.py. As each batch future completes the loop folds its
outcome in with `record_batch` (or `record_crash` when a worker raises), and the
object answers the derived figures the progress line needs: total tokens, average
batch duration, and cost at a given price. The progress bar and the parallel
execution stay in the page.

The accumulation is byte-identical to the old loop, proven by replaying a mixed
event stream (completed, missing-response, errored, and crashed batches) through
both the old loose variables and the dataclass and matching every field plus the
two exact error-message formats, the err-over-missing precedence, total tokens,
average duration, and cost. After the loop the object's values are exposed under
the same names the rest of the page reads, so the summary line, Run_Metadata, and
run persistence are untouched; the dataclass is the source of truth and those
names are a thin compatibility view that a later step removes.

Sixteen tests are added: the empty initial state, each `record_batch` rule (token
and count accumulation, error logging, missing-response counting, err-over-missing
precedence, integer coercion), `record_crash` logging with the exception type
name, the derived figures (total tokens, mean duration, cost, and their empty
cases), mixed-sequence totals, duration ordering, and a real-data simulation that
drives the diagnostics from batches built off a planner Result workbook so every
customer item is accounted for. The suite grows from 1605 to 1621 passing; the
page renders without error.

## [v33.94] — extract per-batch AI result merge to engine/classification.py

Second sub-slice of the classification-orchestration block. The per-batch merge,
which writes the model's answers into the planning frame, is now
`classification.merge_classification_results`. The page keeps the progress bar,
the parallel execution, and the timestamp; the merge rules move to the engine,
where they are tested directly instead of being buried in the wave loop.

The merge respects existing results. A product category is replaced only when the
current one is weak or its confidence is unknown/low; the row's listing then
corrects the answer (a Tools row cannot become PPE, a PPE row collapses non-PPE
answers to ppe unless they are accessories or screws), and the result must be a
known category. Size is filled only when blank, pack-units only when the model
returns 1 or 10 and it differs, and a heuristic pack-unit is applied only when the
current pack source is Default or Heuristic. Model and timestamp are recorded on
every field written. The function mutates the frame in place, matching the wave
loop that accumulates results across batches.

Behaviour is identical. The extracted function was proven equal to the old inline
loop across every branch on a frame built to exercise each one (weak vs strong
category, low and unknown confidence, both listing corrections, invalid category
and tool-class rejection, the other-forced-low rule, heuristic pack gating, blank
size and pack overrides), comparing all columns with dtype checks at a fixed
timestamp. The threading and progress UI that surround the merge are untouched.

Twenty-three tests are added, named with canonical categories so the accept paths
are exercised: the category gate and listing corrections, confidence and
reason capture, tool-class fill-only-when-blank, pack-unit heuristic and override
rules, size fill-only-when-blank, untouched rows, in-place mutation, and a
real-data merge that fills every blank size on a planner Result workbook when one
is supplied through an environment variable. The suite grows from 1582 to 1605
passing; the page renders without error.

## [v33.93] — extract AI batch preparation to engine/ai_classifier.py

First sub-slice of the large classification-orchestration block. The
classification driver mixes pure logic with Streamlit progress UI and threading,
so it is being taken apart in stages rather than in one move. This ship extracts
the pure batch-preparation step into `ai_classifier.build_classification_batches`:
it splits the rows that need AI into batch-sized chunks and assembles each batch's
per-item payload and the deterministic cache key the cached classifier consumes.
No model call and no Streamlit; the page keeps the progress bar, the parallel
execution, and the result merge, which are the next stages.

The cache key is load-bearing. The cached classifier is a pure function of its
key, so a wrong key means either a needless model call or a wrong cached answer.
The extracted function was therefore proven byte-identical to the old inline loop
on real customer data across five capped-row counts, four batch sizes, and both
reason-trim settings, including every cache key, with row coverage conserved and
the keys stable across rebuilds. The parallel wave reads the same plan shape
(position, row indices, item count, cache key) it always did.

Eighteen tests are added: the batching maths (ceil division, remainder in the
last batch, ordered row coverage, single-batch and one-per-row edges, empty
input, sequential ordinals, only-capped batched, non-default index preserved),
payload shaping (fields cleaned and upper-cased, long descriptions shortened,
listing defaulting to Tools), cache-key behaviour (hashable tuple, deterministic,
moves with trim and with model, distinct rows differ), and a real-data simulation
that batches a planner Result workbook with every row conserved when one is
supplied through an environment variable. The suite grows from 1564 to 1582
passing; the page renders without error.

## [v33.92] — extract the dimensional fit-check to engine/fitting.py

Another slice of the planning pipeline moved out of the page. The optional
dimensional fit-check, a per-row loop that read CabinetType and PackageDimensions
and wrote four Fit_* columns, is now a single engine function,
`fitting.apply_fit_check`. It wraps the existing `fit_disposition` primitive, so
the geometry is unchanged; only the place the loop lives has moved. The page block
shrinks to a guarded one-line call, and the function returns a copy with the new
columns rather than mutating in place.

The function is advisory and additive by contract: only KTC rows are checked,
non-KTC rows receive blank fit columns, and routing is never touched. That
contract is now pinned in tests rather than left implicit in the page.

Behaviour is identical. The extracted function was proven frame-identical to the
old inline block across every branch (ok, misfit with and without a recommended
cabinet, no-dims from empty and from unparseable text, non-KTC blanks), with the
input frame and its index left untouched. The downstream fit-check panel that
counts ok / misfit / no-dims and lists the misfits was checked against the new
output and reads the same columns with the same results. The Fit_* columns are
advisory and UI-only; they are not part of the Result export and are not
persisted, so neither path is affected.

Twenty tests are added: the column contract (exactly four columns added, input
not mutated, index and row count preserved, empty frame handled), the KTC
branches, blank non-KTC rows across several system categories, equivalence with
the row-level primitive, determinism, and a real-data simulation that attaches
realistic package envelopes to a planner Result workbook (1075 rows, every row
conserved, non-KTC blank) when one is supplied through an environment variable.
The suite grows from 1544 to 1564 passing; the page renders without error.

## [v33.91] — de-shadow the carousel-reserve and helix-overfill constants

A correctness fix at the root. The carousel reserve factor and the helix
single-spiral overfill factor were imported from constants.py and then rebound
from their sidebar inputs, so one name carried two meanings: the shipped default
before the rebind, and the user's chosen value after it. Any read of the constant
form instead of the rebound form would have sized cabinets to the default and
ignored the user, with no error to show for it.

That ambiguity is now removed structurally. The two constants are imported under
alias names (`_DEFAULT_RESERVE_FACTOR`, `_DEFAULT_OVERFILL_FACTOR`) that are used
only to seed the widget defaults, so the bare upper-case names no longer exist in
the page. The run-time values live in plainly-named lower-case variables
(`carousel_reserve_factor`, `helix_overfill_factor`) assigned from the inputs. A
leftover redundant re-declaration of the overfill factor was deleted. Because the
upper-case names are undefined, any site that had been missed would raise on sight
rather than fall back silently. No engine source changed.

Fourteen tests are added. Nine are static guards that the shadow cannot return:
the bare constants appear only at the aliased import, the run-vars are assigned
from the inputs, the widgets seed from the aliases, no redundant re-declaration
remains. Four show why the fix matters by driving sizing where the
minimum-allocation floor does not mask the factors (reserve moving stockpiles
17 vs 14, overfill moving a 30-pack item between one and two spirals, a deeper
reserve enlarging carousel slots on a 220-item frame). One runs the full sizing
pipeline on a planner Result workbook supplied through an environment variable, so
no customer name lives in the test.

Real customer data was re-validated and is identical: the ground-truth plan
(2 carousel + 1 helix = 3 cabinets), the per-item sizing, and the demand stage
across four customer files all match the pre-change baseline byte for byte, as
expected since the engine is untouched. The factors are inert on that particular
dataset (the floor dominates its carousel items), which is a property of the data
and is exactly what the de-shadow protects every other dataset from. The suite
grows from 1530 to 1544 passing; the page renders without error.

## [v33.90] — portable control model + reusable group renderer; "Threshold controls"

Groundwork for grouping the sidebar controls and for keeping the view layer thin
enough to swap later. A new `controls_model.py` holds the control definitions and
their logic as plain data, with no UI framework import: each control is a
`NumberSpec` (label, default, bounds, help, formatting) and controls collect into
a named `ControlGroup` that answers whether any value is non-default and what the
applied-settings summary reads. A single `render_group_popover` in the page draws
any group as one popover button that turns green when something is changed --
keyed off the stable `st-key-*` class rather than the volatile emotion classes --
with the summary underneath. Adding a control group later is data plus one call.

This is the seam that lets the engine and the control logic outlive a change of
view framework: only the one renderer is Streamlit-specific. The first visible
change is the rename of "Additional threshold controls" to "Threshold controls"
for a thinner label. The carousel controls move into their own grouped popover,
and the per-type capacity buffer and fill ceiling get their UI, in the next ship.

Seven tests cover the model (non-default detection with float tolerance, integer
coercion, suffix formatting, group summaries in spec order, default fallback).
The suite grows from 1523 to 1530 passing; the renderer renders without error and
no existing control behaviour changed.

## [v33.89] — carousel fill ceiling + empty-threshold absorption (engine plumbing)

The second new carousel lever, again as engine plumbing the UI will switch on
later. A new `carousel_cabinets_needed` helper sizes the carousel cabinet count
from a soft fill ceiling -- a fraction of physical capacity -- rather than always
packing to physical. At 0.85 a cabinet fills to 85% and leaves headroom, which
can open an extra cabinet. The empty-cabinet threshold governs that extra
cabinet: a headroom-driven cabinet is opened only if its occupation would reach
the threshold; otherwise its contents are absorbed into the headroom of the
others, up to physical capacity. The result is never below `ceil(slots /
capacity)`, so physical capacity is always respected.

The three carousel-counting paths -- `compute_carousel_needs`,
`compute_plan_for_subset`, and the cap in `apply_carousel_cap` -- now route
through the helper, and the ceiling is threaded through the rebalancer and the
size-locked detector so their projections agree. For the absorption threshold
those paths reuse the existing empty-cabinet threshold, which is the control the
user already sets. The defaults (ceiling 1.0, threshold 0.0) reproduce the
original count exactly, proven byte-identical on the real customer plan, on
`compute_carousel_needs` across ten slot totals, on the carousel cap, and on the
rebalancer. The rebalancer's relocation headroom intentionally stays at physical
capacity so consolidation can still pack tight to drop a cabinet.

Twelve tests cover the helper (headroom honoured, tiny overflow absorbed, a
marginal cabinet above threshold kept, never below physical, non-positive ceiling
treated as one) and the routing through each counting function. The suite grows
from 1511 to 1523 passing; no engine behaviour changed at the defaults.

## [v33.88] — per-type capacity buffer (engine plumbing)

First step toward letting the capacity buffer be set per cabinet family rather
than only as one global figure. `compute_plan_for_subset` now accepts
`buf_helix`, `buf_carousel`, and `buf_locker` keyword arguments alongside the
existing global `buf_pct`. Each family's resource count is buffered by its own
value; a family left at `None` falls back to the global, so the buffer is still
applied at the single existing chokepoint, just split three ways.

The change is backward-compatible by construction: with no per-family value the
output is byte-identical to before, proven on the real customer plan at three
buffer settings and on the rebalancer. The new arguments are threaded through the
rebalancer and the size-locked detector so their internal projections stay
consistent once the values are non-uniform. The page is untouched in this ship,
so behaviour on screen is unchanged; the UI that sets per-family values, and the
fill-ceiling control, follow in the next ships.

Seven tests cover the fallback identity, the global-equals-uniform identity, and
each family inflating only its own cabinet count. The suite grows from 1504 to
1511 passing; no engine behaviour changed at the defaults.

## [v33.87] — run_plan staging, slice 2: physical sizing to the engine

Second slice of the staged `run_plan` extraction. The inline block that sizes
Helix spirals and KTC carousel stockpiles moves into `engine/sizing.py` as
`assign_physical_sizing`. Like the cabinet-type slice before it, this block had
no diagnostics, so there was no warning to lose, and it writes to row subsets by
mask rather than rebuilding the frame, so no row can be dropped.

One subtlety drove the function signature. The reserve factor and the Helix
overfill factor are reassigned from the user's run-time inputs earlier in the
page, so at this point they hold the user's chosen settings, not the module
constants. The function therefore takes both as parameters; reading the constants
instead would have silently ignored the user's settings and mis-sized cabinets.
The slice was proven frame-identical to the captured inline output for both the
default factors and a deliberately different set, so the parameters are honoured
rather than baked in. Tests pin the same two guards as before -- row count and
index preserved, only the two integer columns added with every original column
untouched -- plus a sensitivity check that a changed reserve, minimum, or overfill
moves the result.

Sixteen tests were added (the routing branches, the regrind floor, the carousel
reserve and minimum, the empty frame, parameter sensitivity, and the conservation
guards). The suite grows from 1488 to 1504 passing; no engine behaviour changed.

This ship also includes a cross-engine safety pass: all 26 engine modules import
cleanly with no circular dependency, no existing engine module's source was
changed by the recent slices, and the new modules compose on real customer data
without dropping a single row while the fully-derivable demand columns reproduce
the baseline exactly.

## [v33.86] — run_plan staging, slice 1: cabinet-type assignment to the engine

First slice of the staged extraction of the planning pipeline into a pure
`run_plan` function. The pipeline is mostly engine calls glued together in the
page with inline loops; this moves one of those loops -- the per-row cabinet-type
and spiral-capacity assignment -- into `engine/sizing.py` as `assign_cabinet_types`.
The per-row decisions stay in `engine.cabinet_math`; this holds the orchestration.

The slice was chosen for safety: the block had no diagnostics, so there was no
warning to lose, and a per-row loop that appends one entry per row, so no row can
be dropped. Both properties are now proven. The new function was checked
frame-identical to the captured inline output across every branch (Kanban, the
three locker sizes, Carousel, and Helix with its spiral capacity), and the edited
page reproduced it. The two guards that matter most for a pipeline stage are
pinned by tests: row count and index are preserved exactly, and only the two
intended columns change while every original column is untouched.

The now-unused `decide_cabinet_type` import was removed from the page. Fourteen
tests cover the routing branches, the locker-size mapping, threshold sensitivity,
the empty frame, and the conservation guards. The suite grows from 1474 to 1488
passing; no engine behaviour changed.

## [v33.85] — cache the workbook read (the largest per-rerun cost)

Streamlit re-executes the whole page on every interaction. Profiling the pipeline
on a representative file showed the single largest repeated cost was the full
workbook parse: roughly 290 ms re-read every time the user touched any control,
while the demand and routing stages were a few milliseconds each. The parse was
the only heavy step with no memoization.

The full read is now wrapped in a content-keyed cache: the sheet is parsed once
per (file content, sheet name) and a rerun, or a re-upload of the same file,
reuses the parsed frame. Measured on the same file, a cache hit returns in about
0.24 ms against the 286 ms re-parse, roughly a thousandfold saving on every rerun
after the first. The cached frame is verified identical to the direct read, and
because the cache hands out a copy per call, downstream code that reshapes the
frame cannot corrupt it.

This is a targeted fix, not a whole-plan cache. The full computation cannot be
memoized as one unit yet: the pipeline interleaves about 190 render calls and
several mid-pipeline interactive widgets (the fit-check form, the manual size
fixes, the technician editor) across roughly 3,400 lines, and a cached function
cannot call Streamlit. Caching the computed plan wholesale needs the pure-pipeline
extraction, which is the next planned step; the workbook read was the largest
piece that could be cached cleanly and safely on its own.

No engine behaviour changed and the suite is unchanged at 1474 passing; this is a
page-level optimization verified by the read-equivalence check and the render
smoke rather than by new unit tests.

## [v33.84] — demand arithmetic and base routing extracted to the engine

The most correctness-sensitive numbers the app produces -- monthly pieces, monthly
packs, coverage-scaled target packs, and the base KTC/Kanban decision -- were
inline in the planner page with no test of their own. They now live in
`engine/demand.py`: three scalar primitives (`monthly_pcs`, `monthly_packs`,
`target_packs`) and two DataFrame stages (`compute_demand`, `assign_system_category`).
The page resolves its controls and calls them; the columns produced are unchanged.

The move was proven, not trusted. The output of the old inline block was captured
for three coverage paths -- a Standard/Special split, no Standard/Special column,
and equal coverage windows -- and the new functions reproduced each captured frame
to the value, dtype, and column order, including the detail that the
`Coverage_class` column appears only when coverage is split. The edited page was
then run with fixed inputs and produced an identical frame. Against an actual
planner output, the monthly pieces and monthly packs reproduced to the last digit
across 1075 rows.

Only the base decision moved. The override layers that run after it
(screws/accessories forced to Kanban, system-type routing, special-to-KTC) stay in
the page; they are separate concerns and were not touched. The now-unused
`coverage_days_for` import was removed from the page.

Thirty tests pin the new module across the primitives, the demand columns, the
routing boundary (strictly greater than), the per-tool-class threshold, the empty
frame, and input immutability. The suite grows from 1444 to 1474 passing.

## [v33.83] — test coverage doubled and recent changes validated on real input files

No production code changed in this release. It widens the test suite and confirms
the two preceding extractions (export column shaping in v33.81, the run
fingerprint in v33.82) behave correctly on real customer input, not only on
synthetic fixtures.

Seventy-five tests were added across four files. The export segregation tests
mirror the per-segment column dropping seen in production output: the KTC sheet
keeps both cabinet columns, the Kanban sheet drops both, the Helix sheet drops the
carousel column, and the carousel sheet drops the helix column. The pipeline
integration tests run a small synthetic tool list through the stages the page
chains together (preprocessing, classification, the demand arithmetic, routing,
and export shaping) and check the stages connect and produce the expected numbers;
this is flow-level coverage the suite did not have before. The fingerprint
scenario tests check stability and the conditional folding of the carousel cap and
program map across realistic settings combinations. The demand and routing edge
tests pin the inline demand arithmetic (which had no engine-level test) and the
routing threshold boundary and per-tool-class override matrix.

Validation against real input files backed the work. The export shaper reproduced
the segregated sheets of an actual planner output exactly, to the row and the
column (a 1075-row result split into 364 KTC, 711 Kanban, 124 Helix, 240
Carousel, with the same surviving columns in each). The demand arithmetic
reproduced that output's monthly pieces and monthly packs to the last digit. The
fingerprint, built from that run's recorded settings, computed cleanly, stayed
stable across identical inputs, and invalidated when the threshold or the carousel
cap moved. Six input files spanning three header languages ingested and classified
end to end. None of this real data appears in the suite; the tests are synthetic.

The suite grows from 1369 to 1444 passing.

## [v33.82] — run fingerprint extracted into a typed, tested engine module

The run fingerprint, the value that decides when a displayed plan is stale and a
re-run is required, was a 54-element inline tuple built from 55 inputs. It moved
into `engine/run_fingerprint.py`: a frozen `FingerprintInputs` dataclass that
names every input, and a pure `compute_run_fingerprint` that builds the tuple. The
page resolves its widgets into the dataclass and calls the function; the
invalidation gate, the stored fingerprint, and the reset paths are unchanged.

This is the structural follow-up to v33.71, which fixed the fingerprint contents.
The two failure modes are a dropped input (a control changes but the stale plan is
not invalidated) and silent drift in the tuple (a needless re-run), so the move
was proven rather than trusted. The new function was checked element-for-element
against the tuple captured from the old inline code and matched exactly, and the
edited page was then run with the same fixed inputs and produced an identical
fingerprint. Sixty tests pin it: a golden tuple, a check that every one of the 55
inputs moves the fingerprint (so a future dropped input fails a test), the
conditional folding of the carousel cap and the program map, order-independence of
the threshold and program dictionaries, and the per-field coercions.

The fingerprint only gates re-runs, so nothing downstream is touched: the Excel,
PDF, and PPTX exports, the database, and run-restore are independent of it, and
their suites pass unchanged. The suite grows by the sixty tests.

## [v33.81] — page decomposition slice 4: export column shaping to the engine

Fourth decomposition slice. The column shaper for the user-facing Excel sheets,
`USER_FRIENDLY_COLS` and `_user_view`, moved into `engine/export_shaping.py` as a
pure `user_view`. It trims the segregated sheets (KTC_only, Kanban_only,
Helix_only, Carousel_only, Bulk_Routed, and the listing sheet) to the
identity/classification/demand/plan columns and drops, per sheet, any column that
is entirely empty. The page imports it under its previous name, so the seven
export call sites are unchanged; the Result sheet still carries the full audit
dump.

Because the Excel sheets are a delivered artifact, the move was verified rather
than assumed. The new function was checked frame-for-frame against the old one
across eight cases (full data, all-zero numeric column, all-blank text column,
missing columns, audit-only columns, the SizeIssue flag, an empty frame with
columns, and an empty frame without columns) and produced identical output every
time; a written xlsx was then compared cell-by-cell and matched exactly. The PDF
and PPTX exports take separate data paths (the per-supply-point summary and the
deck stats) and do not call this shaper, and it is absent from the database
layer, so those outputs are unaffected; the persistence, run-restore, and deck
suites confirm it. Twelve tests now pin the shaper directly, including an xlsx
round-trip, where before it had none. The suite grows by the twelve tests.

## [v33.80] — page decomposition slice 3: classification prompt to the engine

Third decomposition slice, and the most delicate one. The batch classification
prompt, an 80-line template, was an inline f-string in the page. It moved into
`build_classification_prompt(items_payload)` in `engine/ai_classifier.py`. The
page still builds the per-item payload (it also feeds the missing-row check) and
now passes it to the builder.

The prompt wording steers the model and is NOT part of the batch cache key, so a
one-character change would silently shift classifications without invalidating
any cached result. To rule that out, the template was lifted by extracting its
exact bytes from the page rather than retyping it, and the move was proven
byte-for-byte: the edited page path reproduces the original prompt with an
identical checksum. The prompt is now pinned by a golden file,
`tests/golden_classification_prompt.txt`, with six tests: an exact match against
the golden, the output being whitespace-stripped, every product category present,
the two CRITICAL rules retained, the appended items JSON parsing back to the same
row ids, and non-ASCII input surviving unescaped. If the prompt is ever changed
on purpose, the golden file is regenerated in the same change. The suite grows by
the six tests.

## [v33.79] — page decomposition slice 2: AI cost/ETA estimation to the engine

Second decomposition slice. The pre-run cost and time estimate (the wave model
and token accounting) was computed inline in the page and had no tests. It moved
into a new `engine/ai_estimate.py` as a pure `estimate_ai_run(n_items, batch_size,
workers, trim_reason)` that returns batches, waves, seconds, token totals, and
cost. The eight pricing and token-rate constants moved with it, since they belong
with the estimator that reads them; the page now imports the two price constants
it still needs for the post-run actual-cost line.

The function is guarded to stay total for inputs the UI cannot produce (a zero
batch size or worker count), but for every valid input it reproduces what the
page computed before. Nine tests cover batch round-up, the wave model scaling
with worker count, time following waves rather than raw batch count, token
accounting, the trim flag lowering output tokens and cost, the cost formula, an
explicit equality check against the original inline arithmetic, all-zero on zero
items, and the degenerate-input guards. The full suite grows by the nine tests.

## [v33.78] — git adoption scaffolding

Tooling and docs only, no code change. The existing `.gitignore` gained the
entries this project specifically needs: the SQLite database (`*.db`, the
journal/WAL siblings, and `.kromi_cabinet_planner/`), the per-build `*.zip`
archives, virtual-environment folders, and Windows/OneDrive noise (`desktop.ini`,
recycle bin, `*.lnk`). The database entries matter most, since keeping the DB out
of version control is the same discipline as keeping it off synced folders.

The README gained a "Version control" section describing the workflow: initialise
the repo, commit once per build, and tag the builds that were previously saved as
zips, so `git checkout vXX.YY` replaces the archive-as-rollback habit. The ignore
rules were checked against a throwaway repository seeded with a database file, a
build zip, runtime folders, and a `.env`: none were staged, while the tracked set
stayed at the real source and test files. A note flags that customer-data
fixtures should not be pushed to a shared repository.

## [v33.77] — page decomposition slice 1: AI plumbing moved to the engine

First step of breaking up the oversized planner page. Two pure helpers that had
no business living in the UI layer moved into a new `engine/ai_classifier.py`:
`make_batch_cache_key` (builds the deterministic key the cached classifier keys
on) and `extract_chat_usage` (pulls token counts off an OpenAI response). Both
are free of Streamlit and I/O, so they now sit in the engine and are unit-tested
directly, where before they were untested page internals.

The page imports them under their previous names, so every call site is
unchanged; only the definitions moved. Eight tests cover key determinism, the
trim flag and model and item fields each changing the key, supplier-code case
folding, whitespace collapsing, and usage extraction returning zeros when usage
is missing or malformed. The cached classifier wrapper and the OpenAI request
itself stay in the page, since they need Streamlit. Behaviour is unchanged; the
full suite grows by the eight new tests and is otherwise identical.

## [v33.76] — renamed the routing-protection flag to Routing_Pinned

The internal flag that marks a row as pinned (so bulk routing and cabinet
consolidation leave it in place) was named `SystemTyp_Forced`, from the days when
only the System type override set it. It is now also set by the special-to-KTC
force, so the System-type name was misleading. It is renamed to `Routing_Pinned`
across the engine, the page, and the tests (33 occurrences), which says what the
flag means rather than where it first came from.

This is an internal rename with no compatibility or output impact: the flag is
not written to any exported sheet and is not part of the saved-run snapshot, so
stored runs and delivered files are unaffected. The rename was done code-first to
confirm the behaviour tests do exercise the flag (they went red on the old
name), then completed in the tests; the full suite passes unchanged, including
the tests that assert pinned rows survive bulk routing and consolidation.

## [v33.75] — removed a pytest deprecation that would break on pytest 10

Test infrastructure only, no app change. One fixture, `kromi_taxonomy` in
`tests/test_taxonomy_alignment.py`, was a class-scoped fixture defined as an
instance method, which pytest reports as `PytestRemovedIn10Warning` and will stop
supporting in pytest 10. It is now a `@staticmethod` (its body never used
`self`), the form pytest recommends, so the suite will keep collecting on a
future pytest. That warning is gone; the suite is unchanged at 1274 passing.

The remaining warnings are third-party pulp 4.0 deprecation notices (direct
`LpVariable` construction and `PULP_CBC_CMD`) raised from inside the pinned
`pulp<4.0` dependency, not from this codebase. They are left alone here: changing
how solver variables are built touches the constraint-solver path and belongs
with an eventual, deliberate pulp 4.0 migration, not a test-hygiene fix.

## [v33.74] — documented the OneDrive/SQLite database caveat

Documentation only, no code behaviour change. The SQLite database that holds
override sets and run history can be corrupted if it lives on a cloud-synced
folder (OneDrive, Dropbox, Google Drive), because SQLite takes short-lived write
locks and a sync client can copy or replace the file mid-write or merge writes
from two machines. The default path already sits in a non-synced dot-folder, but
that constraint was not written down anywhere. The `default_db_path` docstring in
`db/store.py` now explains why the path is non-synced and what to do if
`KROMI_DB_PATH` is pointed inside a synced tree, and the README "Running" section
gained a "Database location" note with the same guidance: keep the database off
synced folders, and never run two instances against the same synced file at once.

## [v33.73] — System type application extracted into a tested engine function

The customer System type (Lagersystem) override was applied by a ~50-line loop
sitting inline in the page, while its sibling, the special-to-KTC force, already
lived in the engine as `force_special_to_ktc`. That asymmetry is now gone: the
loop moved into `engine.cabinet_math.apply_system_type`, which takes the same
routing parameters, mutates the frame in place, and returns
`{"ktc", "locker", "flex"}` counts for the page to report in its caption. The
page now calls the function and keeps only the caption and the no-match warning.

This is a behaviour-preserving refactor: the forcing logic, the exact reason
strings ("System type fixed: KTC (forced vending)" and "System type fixed:
Locker (...)"), the SystemTyp_Forced pinning, and the KTC / Locker / KTC-or-Kanban
handling are unchanged. Six tests pin that behaviour against the engine function
directly, where the inline version had none: KTC forces vending and pins, Locker
forces a size-matched locker, KTC-or-Kanban is counted but left to the threshold,
blank and unrecognised values are untouched, a missing column is a no-op, and a
mixed frame produces the right counts. The two forcing paths now read the same
way and are independently testable.

## [v33.72] — optional "Trim AI reasons" toggle for faster, cheaper AI runs

A new sidebar toggle, "Trim AI reasons", removes the per-item written reason from
the AI classification. The reason is the bulk of each item's output tokens, so
trimming it noticeably cuts AI wall-clock time and cost. The category, tool
class, size, and pack results are unchanged — only the explanation is dropped, so
the "AI reason" column comes back blank. The toggle is off by default, so
existing behaviour is unchanged unless it is switched on.

The classification JSON schema moved out of the page into a new, tested
`engine.ai_schema.build_classification_schema(trim_reason)`. Because the schema
is strict, dropping the reason field from it prevents the model from emitting one
at all, which is where the saving comes from; the prompt is left untouched, which
is harmless since a strict schema cannot return an undeclared field. The toggle
is cooked into the AI cache key (it is a schema variant), into the run
fingerprint, and into the run-restore key list, so cached results, stale-result
invalidation, and reloaded runs all stay correct. The ETA and cost estimate uses
a lower per-item output figure when reasons are trimmed.

Five tests cover the schema builder: the full schema carries reason in properties
and required, the trimmed schema drops it from both, the other classification
fields are identical in both, both stay strict (every property required,
additionalProperties false), and the enums still match the classifier contract.

## [v33.71] — re-run gate now covers operational mode, carousel cap, special→KTC

Three controls that change the plan were missing from the fingerprint that
decides when cached results are stale: the operational mode (Helix / Carousel /
capped), the Max-Carousels cap, and the "Set special tools as KTC" toggle.
Because results are recomputed on every rerun anyway, this did not corrupt any
output, but it made those three controls behave inconsistently: changing them
updated the dashboard live, while changing any other control correctly asked for
a re-run first. It would also have become a real stale-results bug the moment
any result caching was added.

All three are now part of the fingerprint, so changing any of them invalidates
the shown results and prompts a re-run, exactly like every other control. The
carousel cap is folded in only in capped mode, so changing it in a mode where it
has no effect does not needlessly invalidate. The run-restore key list already
covered all three, so saved runs were unaffected and still reload correctly.

This is the bounded, safe part of the "plan-caching" idea. Full result caching
was investigated and set aside: results already survive reruns via `has_results`
and the AI classification is already memoized, so caching the whole inline
pipeline would be a large, risky change for little gain.

## [v33.70] — internal cleanup: shared reason constant and set-label helper

Two small refactors that remove duplication introduced by the v33.67–69 work,
with no behaviour change to routing or sizing.

The "Special tool forced to KTC" reason string is now a single shared constant,
`engine.cabinet_math.SPECIAL_KTC_REASON`. The engine stamps it, and the Excel
export's `Forced_to_KTC` column and the Run_Metadata "Special forced to KTC"
count both read it from there, so the engine and the export can no longer drift
to different strings and silently miscount. A test pins the constant's value.

The override-set picker label is now built by one shared helper,
`db.override_sets.format_override_set_label`, used by both the recompute picker
and the save dialog's update list. Previously each built its own label, and the
two had drifted: one showed a `DB set #` prefix and a raw `T` in the timestamp,
the other a `#` prefix and a space. Both now render the same
`#<id> · <YYYY-MM-DD HH:MM> · <n> tool(s)[ · <reviewer>]`, and a missing
timestamp no longer risks rendering the literal "None". Three tests cover the
helper. The only visible change is the recompute picker dropping its `DB set`
prefix for the shared format.

## [v33.69] — surface Standard/Special and the special→KTC force in the output

The special-tools feature is now visible in the exported workbook, not only on
screen. When the Standard/Special column is mapped, the Result sheet (and the
KTC/Kanban breakdowns) gain two columns: `Std_Special`, the per-row
classification (Standard / Special), and `Forced_to_KTC`, marked "Yes" on the
rows the toggle pushed onto a vending machine. Run_Metadata gains three lines:
whether "Set special tools as KTC" was on, how many rows were marked Special,
and how many were forced to KTC. A run that does not map the column
exports exactly as before — the columns are created only when the column is
mapped, and the empty-column trimmer drops `Forced_to_KTC` when the toggle was
off so nothing was forced.

This closes a v33.68 gap: the force changed the plan but left no trace in the
file, so its effect could not be checked after the fact. The classification and
counts are derived from the same `classify_standard_special` the engine uses, so
the sheet and the metadata always agree with the routing.

## [v33.68] — force special tools to KTC, and the 1/2 Standard-Special encoding

A mapped Standard/Special column can now drive routing, not only coverage. When
the column is mapped, the sidebar shows a new checkbox, "Set special tools as
KTC". Left off (the default), nothing changes: the column still only splits the
on-machine coverage days. Switched on, every tool marked Special is forced onto
a vending machine regardless of its consumption, with the spiral/stockpile
sizing that implies, so the cabinet count and storage rise accordingly. A
caption reports how many rows were forced; if none were marked Special, a
warning says the toggle had no effect.

The force reuses the proven System type = KTC path. `engine.cabinet_math` gains
`force_special_to_ktc(work, ...)`, which re-routes each Special row through
`route_and_size_row(force_ktc=True)` and pins it with `SystemTyp_Forced`, so the
row is protected from bulk routing and cabinet consolidation exactly like a
System-type-fixed or technician-fixed row. System type wins where it applies: a
row already fixed by a mapped System type column is left untouched and is not
re-counted. The page runs the force after the System type block and before bulk
routing, and guards on the column being mapped so a stale toggle from an earlier
file cannot act. The toggle is captured in the run's settings, so a recompute of
a saved run reproduces it. Six tests cover the force: a low-mover forced to KTC,
a standard row left alone, a System-type-fixed row winning, blank/0/unknown
markers ignored, the no-column no-op, and a mixed frame forcing only the
eligible rows.

The Standard/Special numeric encoding changes to 1 = standard, 2 = special.
Previously the binary scheme read 1 = standard, 0 = special; the planner now
reads 2 (not 0) as special, matching the customer encoding in use, and no longer
treats a bare 0 as special (0 becomes unrecognised). The word forms (standard /
special in seven languages) and yes/no / true/false are unchanged. This affects
both the coverage split and the new KTC force, since both read the same
classifier. The binary-token tests were updated to the 1/2 scheme.

## [v33.67] — update an override set in place instead of saving duplicates

Re-saving corrections for a customer and site no longer piles up a fresh
override set every time. The save dialog now offers a destination choice: "Save
as a new set" (the default) or "Update an existing set". When a set exists for
the typed scope and the reviewer picks it, the chosen set is replaced in place,
keeping its id while its corrections and metadata are refreshed. A scope that
held five near-identical sets after five saves now holds one.

The database layer gains `update_override_set(conn, set_id, ...)`. It rebuilds
the set's override rows from the wide frame with the same normalization
`save_override_set` uses, refreshes the set's reviewer, notes, customer, and
site, keeps the original `created_at` so the set's identity stays stable, and
runs as one transaction so a set is never left half-replaced. Updating a
missing id changes nothing and returns False. The function is exported from the
`db` package and covered by five tests: same-id-and-count after update, row
replacement (dropped codes gone, new codes present), metadata refresh, the
missing-set guard, and a round-trip back through `apply_overrides`.

This is a clean reimplementation. It does not restore the reverted v33.67
"one set per source file" approach: there is no migration, no schema change, and
no implicit file-hash matching. The reviewer chooses the destination explicitly.

## [v33.66] — override editor accumulates corrections across filters and pages

The technician override editor now keeps a running set of corrections in the
session, so edits made under one filter or page are no longer lost when the view
changes. Before this, the editor computed its changes only from the slice on
screen. Switching the filter or paging rebuilt the table and discarded the
previous view's edits, and two saves produced two separate sets where only the
last one applied. Now Apply table edits folds the current view's edits into one
accumulated map (keyed by tool code) and recomputes, so the plan and the editor
both reflect every correction gathered so far. A running count sits below the
table with an option to review the full set. Save correction(s) as override set
persists the whole accumulation as one set, and Clear all corrections removes
them and recomputes without them.

The hard 500-row cap is replaced by paging. The editor shows 500 rows at a time
with a page selector, so every row is reachable, and corrections accumulate as
you page through. Apply must be clicked before changing the filter or page, or
that view's un-applied edits are dropped, because a Streamlit form discards
uncommitted edits on any other interaction. The apply path applies the
accumulated map ahead of a picker override choice. A picker reload and a new
uploaded file both clear it.

## [v33.65] — saving an override set applies it in one step

Saving technician corrections as a database override set now applies them to the
current plan in the same action, so the separate "Recompute with overrides"
button is gone. After the file-library save was retired (v33.63), saving a set
stored it but did not apply it to the open run; the corrections only took effect
on a later reload from the run picker. The override editor's save now arms the
just-saved set and forces one recompute, and the apply path gained a branch that
applies an armed set ahead of any picker override choice, since saving is the
more recent and deliberate action. The armed set persists across re-runs of the
same file; the run picker's "Load & recompute" clears it so its own choice
governs; and a newly uploaded file clears it so corrections never bleed onto a
different file. Verified end to end: a saved set overriding a tool's cabinet type
applies on the recompute it triggers.

## [v33.64] — delete saved override sets and individual rows

Saved override sets could be created and superseded but never removed; the only
prune was a soft deactivate that kept every row. A "Manage saved override sets"
panel was added below the technician review: it lists the sets for the current
customer and site, shows the tool rows inside a chosen set, and hard-deletes
either a whole set (behind a confirm step, since it cannot be undone) or one
tool's row on its own. Two database calls back it: ``delete_override_set``, which
removes a set and all its rows in one transaction (explicitly and via the
ON DELETE CASCADE foreign key, so nothing is orphaned), and
``delete_override_set_row``, which removes every stored field row for one tool in
a set and leaves the set in place even when that empties it. Added tests for both
calls (set removal, row removal, scope isolation, missing-id handling) and a
real-page check that drives a row delete and a set delete to completion.

## [v33.63] — override editor batches edits in a form, file-library buttons retired

Every cell edit in the technician override editor re-ran the page and redrew the
whole table, so each correction flashed the screen blank. The editor now sits
inside a form: edits are held until an "Apply table edits" submit, so a batch of
corrections costs one re-run instead of one redraw per cell. The two
file-library buttons ("Save ... to overrides library" and "Show current
library") were removed; the database override set is now the single store for
corrections, reachable from the "Save ... as override set" button, which shows a
spinner while it writes. The editor instructions and the panel label were
updated to match. The override apply and recompute wiring is unchanged, and the
full plan still runs end to end to the dashboard.

## [v33.62] — column mapping heals a seeded collision instead of perpetuating it

A required column-mapping field (Code, Description, Consumption) that was
restored from a saved run, or carried over in the session, was honoured as-is
even when all three pointed at the same source column. A run saved before the
column-collision guard existed stored exactly that (its three required fields
were all written onto the first column), so recomputing it re-seeded the
collision, the conflict warning fired, and the correct auto-detection (and the
AI proposal) lost to the stale value. The required-field resolver now treats a
stored pick that duplicates a column an earlier required field already claimed,
or that names a column the file no longer has, as a stale collision and
re-resolves it to a non-colliding auto-detected column. On a German tool-list
export this resolves automatically to Code -> WZIntNr, Description -> WZBez,
Consumption -> the consumption column, with no manual correction, and old saved
mappings heal on recompute. A genuine, distinct restore or an explicit user
choice is preserved unchanged. Added tests for the resolver and a real-data
check that a bad saved mapping recomputes without a conflict.

## [v33.61] — simpler KROMI article numbers for KTC articles

KTC articles now receive a plain running-counter article number instead of one
built from the tool's class and dimensions. The number is the 3-digit KTC-ID,
the fixed segment "10", a 4-digit counter in the order the articles appear in
the result, and a trailing zero block: for KTC-ID 193 the first article is
193100001000, the second 193100002000, and so on up to 193109999000 at the top
of the range. The counter does not encode dimensions or description; it is a
sequence, which keeps the numbers easy to read and assign and removes the old
limit of 99 articles per shared dimension.

Kanban (and any unclassified) articles are unchanged: they keep the existing
scheme that derives the article number from the tool class and the dimensions
read off the description. The two schemes never collide, because the class
matrix never produces the fixed "10" segment that marks a KTC number. Every
generated number stays 12 digits, ends in zero, and is unique across the
catalogue. Added tests for the new counter, the KTC/Kanban split, and a
real-data check that the export assigns the two schemes correctly.

## [v33.60] — year-column parser no longer crashes on missing values

Importing a file whose Year column is missing or has blank cells could crash the
run with "'float' object has no attribute 'lower'". The year parser assumed that
converting a column to text turned a missing value into the word "nan", which it
then recognised and skipped. Newer pandas keeps a missing value as a number
instead of that text, so a bare number reached the text check and raised. The
parser now recognises missing values directly and treats int, number, and text
year columns the same way. A file with no Year column at all (every cell
missing) parses cleanly instead of stopping the run. Added tests covering an
all-missing column and a mix of missing, numeric, and text years.

## [v33.59] — batched Helix-fit controls and quieter auto-save during manual fixes

The "Problematic size detected" panel used to render one "Treat as Helix-fit (M)"
button per flagged item, and each click re-ran the whole page. Working through a
list of items meant one full re-run, and one screen redraw, per click. The panel
now presents the flagged items as a checklist inside a form: tick the items you
can repackage to fit a Helix spiral and apply them in one go, with a "Select all
and apply" shortcut. Ticking boxes does not re-run the page; only the submit
does, so a batch of fixes costs a single re-run instead of one per item. The
reset control is unchanged.

The database auto-save now stays quiet while manual Helix-fit overrides are
active. Those overrides are a session-only assertion that a tool will be
repackaged to fit a spiral; they do not survive a reload. Previously each
adjusted plan was written as its own run (and, because a fix changes the cabinet
total, every fix click triggered a fresh write). The natural computed plan,
saved on the run before any override, stays the canonical stored run; adjusted
states are shown but no longer persisted. Resetting the overrides returns to
normal saving.

## [v33.58] — file-based run and catalog archives removed; database is the sole store (database Phase 5, steps 2-3)

The file-based run archive and the imported-catalog archive are removed. The
database, which already records every completed run and every imported file, is
now the only store for that history. This follows step 1 (v33.57), which hid
those views behind a flag. The technician overrides library on disk is kept: it
still drives fresh runs and has no database replacement yet.

A reset utility is added to start from a clean history: tools/reset_history.py.
It is dry-run by default and prints what it would remove. Run it once on the
machine that holds the database to flush saved runs:

    python tools/reset_history.py                  # dry run, shows current counts
    python tools/reset_history.py --yes            # flush runs + remove runs/ and catalogs/
    python tools/reset_history.py --full --yes     # wipe the whole database

The default flush deletes the database run records (their snapshot children
cascade) and removes the on-disk runs/ and catalogs/ folders, while keeping
imported files, AI classifications, and overrides so no AI work or corrections
are lost. The utility uses only the Python standard library, so it keeps working
with the file-archive code gone.

Saving a completed run to the database is now automatic and unconditional. In
the previous build the database write sat inside the file-archive save block, so
when the legacy flag was off (the default) a finished run was not written to the
database even though the screen said it was. The database write is now
independent of any file-archive option and runs once per distinct result.

Removed: engine/archive.py, engine/catalog_archive.py, db/import_archives.py,
and the page code that read or wrote the on-disk archives (the "Load past run"
browser, the "Save this run when finished" checkbox, the imported-catalog view,
and the catalog write on import). The KROMI_LEGACY_FILE_FEATURES flag from step 1
is gone with the code it guarded.

## [v33.57] — file-based run archive and catalog list hidden in favour of the database (database Phase 5, step 1)

The on-disk run archive ("Load past run" / "Save this run when finished") and
the imported-catalog list are superseded by the database, which already stores
every completed run and every imported file. This step hides those file-based
views by default and points to the database equivalents. Nothing is removed and
nothing changes in how a plan is computed.

What changes on screen when the file features are hidden: the "Load past run"
browser at the top of the page is gone (use "Start from -> Load a previous run"
in the sidebar, which reads stored runs from the database); the "Save this run
when finished" checkbox is gone (completed runs are written to the database
automatically, as before); and the sidebar "Imported catalog library" view is
replaced by a short note. The override controls are unchanged and still work:
the file-library override toggle stays active for fresh runs and carries a note
that database override sets are taking over that role.

This is reversible. Setting the environment variable KROMI_LEGACY_FILE_FEATURES
to 1 restores every file-based view and the file-archive save exactly as before.
A later step will remove the file paths once database parity is confirmed.

## [v33.56] — column mapping no longer collapses to the first column on recompute

Fixes a column-mapping conflict that appeared when reloading a previous run for
files whose headers the auto-detector does not recognise (for example German
tool-list exports with headers such as WZIntNr and WZBez). On those files the
detector returned nothing for Code and Description, so both fell back to the
first column and tripped the "same column mapped to two fields" guard. A run
that restored its mapping worked the first time, but a later recompute could
re-show the conflict even with the right value visible in the Description
dropdown.

Three changes address it. Header auto-detection now recognises the common German
tool-list names for Code, Description, and Consumption, so those fields fill in
on their own. When auto-detection still finds nothing, the required-field
fallback no longer hands the same column to two fields: it skips a column already
claimed by another required field, so Code and Description cannot land on the
same one by default. And the recompute restore now keeps a run's stored mapping
when the workbook's columns cannot be re-read, instead of dropping it and
re-guessing; the render-time check that a mapped column still exists remains in
place.

The user still confirms or overrides every mapping field, and English headers
resolve exactly as before.

## [v33.55] — recompute restores the run's controls and column mapping

"Load & recompute" now reproduces the run it was started from. Previously the
recompute reused the stored workbook and classifications but left the sidebar
controls at their defaults and re-guessed the column mapping from the file
headers, so the result could diverge from the run on screen and the re-guessed
mapping sometimes pointed two fields at the same column.

Each run now carries a snapshot of its control settings and column mapping in
its saved settings. When that run is recomputed, the snapshot is read back and
applied to the controls and the mapping once, before any of them render, so the
recompute runs on the same inputs and only the engine version differs. The
values stay editable afterwards. The snapshot is validated against the stored
file, so a mapping that names a column the file no longer has is skipped rather
than forced. During a recompute the column mapping is shown in full and no AI
mapping call is made.

Runs saved before this version do not carry the snapshot; they recompute on the
current controls as before, and the faithful plain-snapshot view is unchanged.

## [v33.54] — recompute draws overrides from a chosen database set (database Phase 4, read)

Completes the database override workflow. When loading a previous run with
"Load & recompute", the recompute can now take its corrections from a database
override set instead of the file library. The load screen offers a source choice:
the file library (the default, unchanged), no overrides, or any override set
saved for that run's customer and site. The plain-snapshot load ignores this
choice and still shows exactly what was stored.

The chosen source feeds the same override step the engine already uses, so a
recompute with a database set applies size, cabinet, pack, vending, and product
corrections exactly as a normal run would. Because a database set is a complete
snapshot of corrections rather than a difference, this also removes the earlier
caveat where a recompute could not represent an override that had been taken
away: selecting a set replaces the corrections wholesale.

Every part of this is behind the reload path. A normal run from an uploaded file
takes the file-library branch and behaves exactly as before.

## [v33.53] — save overrides to the database from a modal (database Phase 4, UI)

Adds the modal that writes an override set. In the overrides editor, alongside
the existing button that saves to the file library, a new button opens a small
dialog that captures the reviewer name, the customer and site, and optional
notes, and saves the corrections as a database override set. The set stores the
full snapshot (the current file library plus the pending edits) so it is
self-contained.

The two saves are independent and additive. The file-library save is unchanged
and keeps working exactly as before; the database save is an extra option. The
dialog is guarded so a Streamlit version without the dialog feature simply hides
the button rather than affecting the page.

This is the write side of the database override workflow. Reading a stored set
into a recompute, so loading a run with overrides draws from the database rather
than the file library, is the next step.

## [v33.52] — store override sets in the database (database Phase 4, persistence)

The database foundation for the override modal and for drawing a recompute's
overrides from a stored set instead of a CSV. An override set is a named, scoped,
versioned bundle of technician corrections: who saved it, for which customer and
site, with notes, and the per-tool field changes.

What ships: a module (db/override_sets.py) to save a set, read it back, list sets
by scope, find the newest set for a scope, and deactivate an old one while
keeping its history. Storage is normalized, one row per changed field, and a read
reconstructs the wide shape the engine expects, so a stored set applies through
the same apply_overrides path the file library uses. A test confirms exactly
that: a set saved to the database, reconstructed, and run through the real engine
applies its size and cabinet overrides and leaves untouched tools alone.

No user-facing change yet, and the file-based overrides library is untouched and
still in use. This is the persistence layer the override modal will write to and
the recompute will read from, replacing the file library in a later step.

## [v33.51] — load a run and recompute on the current engine (database Phase 3, recompute)

Completes the load picker with a recompute option. Next to loading a run as a
plain snapshot, a run can now be loaded and recomputed on the current engine. The
recompute reuses the run's saved classifications, so the model is not called, and
the current override library for the run's customer and site applies.

How it works without risking a drift from a normal run: the recompute does not
reimplement the sizing. It replays the run's stored workbook through the real
upload and compute flow, with three gated changes that only take effect in this
mode. The stored workbook bytes stand in for an upload, the AI step is skipped in
favor of the saved classifications matched by code, and the run's own customer
and site are used so the right override library loads. Everything after that, the
sizing, the rebalancer, the plan, and the export, is the same code a fresh run
uses, so a recompute and a fresh run of the same inputs cannot diverge.

Scope: this is available for runs that kept their workbook, which is every run
saved since the database write was added. Older imported runs did not keep the
source file and so offer the plain snapshot only; the button says so. A run
recomputed this way can be saved like any other, recording the current build.

Every change to the page is guarded so that, outside the recompute path, the
upload and compute flow behaves exactly as before.

## [v33.50] — reuse stored classifications by code (database Phase 3, recompute groundwork)

Groundwork for loading a run with overrides, which recomputes rather than just
displaying. The size and product categories for that recompute come from the
classifications already stored for the run's file, so no model is called and the
result stays repeatable.

What ships: a small module (db/classification_reuse.py) that reads the stored
classification for every tool code of a run and applies it to a frame by code.
Matching is by code and never by row position, so the lookup lands each value on
the right tool even when the recompute's rows are reordered or a row is added or
dropped. A code with no stored classification is reported back as a miss rather
than guessed. When a code has been reclassified more than once, the newest entry
wins.

A focused test set locks the by-code behavior: distinct sizes per code make any
positional mix-up fail, and the reorder, add, and drop cases all resolve to the
correct code. No user-facing change and no change to the calculation path; this
is the reuse mechanism the recompute path will build on.

## [v33.49] — load a previous run from the landing page (database Phase 3, UI)

Puts the read-back layer in front of the user. The planner now opens with a
choice: upload a new file, or load a previous run. The default is upload, and
that path is unchanged, so an existing workflow is not affected.

Choosing to load a previous run shows a searchable list of saved runs (filter by
customer and site, newest first, each row showing the file, mode, cabinet count,
build, and save time). Selecting one renders it exactly as it was delivered: the
headline cabinet totals, the plan per bucket, and the full result table, with a
download of the result. The sizing comes from the stored snapshot, not a
recompute, so the view cannot drift from what was delivered. When the run was
saved on an older engine than the one now installed, a notice says so and points
to re-running the file for a fresh computation.

The load view is self-contained and read-only: it opens its own database
connection, renders, and stops before the upload and compute path, so nothing in
the existing flow is touched. Regenerating the full Excel, PDF, and PowerPoint
deliverables from a loaded run is a later step; for now the loaded view offers
the result table and a download, and re-running the file produces the full set.

## [v33.48] — read a stored run back (database Phase 3, read-back layer)

The first half of loading a previous run: the layer that reconstructs a stored
run as the exact result it delivered, and the test gate that proves it before
any screen is built on top.

What ships: a read-back module (db/load_run.py) that rebuilds the per-tool
result table and the plan summary straight from the stored rows, with the
original column names and types, plus a compact run lister for a load picker
(newest first, searchable by customer and site, each row carrying its file name
and grand-total cabinet count). The cabinet-sizing numbers come from the
database, never from re-running the engine, so a plain reload shows what was
delivered and cannot drift from it.

A golden round-trip test persists a run and reads it back, asserting that every
stored field of every row matches, that the plans and grand total match, and
that the split case (one tool spread across two supply points) keeps its
per-row values against a single shared tool record. This gate stays in the suite
so the read path cannot regress.

No user-facing screen yet. The landing page that lets a user pick between
uploading a new file and loading a stored run is the next step, and it hangs off
this proven layer.

## [v33.47] — backfill existing runs into the database (database Phase 2)

Brings past work into the database. A one-time importer walks the existing run
archives under ./runs and replays each through the Phase 1 write path, so runs
saved before the database existed are represented alongside new ones.

What ships: an importer module (db/import_archives.py) with a function to import
one archive, a function to import a whole folder, and a command-line entry point
(python -m db.import_archives [runs_dir] [db_path]). It reuses the archive reader
already in the engine, so it stays in step with the on-disk format. The import
is idempotent: an archive already represented by a run is skipped, so it can be
run repeatedly, and a single unreadable archive is recorded and skipped rather
than stopping the backfill.

Two limits follow from what an archive keeps. The source workbook is not stored
in an archive, so an imported run gets a synthetic content hash and no file
body; everything else comes from the archived result. The rebalance move detail
was never written to archives either, so imported runs carry no rebalance
events. New runs saved from here on record the build version they ran under in
their archive metadata, so a later reload of those can warn on engine drift;
older archives predate that and import with an unknown build version.

The database path is shared with the page through one helper, and both default
to a local per-user file (overridable with KROMI_DB_PATH) so the database is
never placed in a synced folder.

## [v33.46] — write completed runs to the database (database Phase 1)

Builds on the Phase 0 foundation: when a run is saved, a normalized copy is now
also written to the database alongside the existing file archive. The
application stays authoritative. The run computes and exports exactly as before,
the database copy is secondary, and a database failure is caught so it never
affects the run, the archive, or the downloads.

What ships: a dual-write module (db/persist_run.py) that turns the finished run
into rows across the schema in a single transaction, so a run is stored whole or
not at all. It records the workbook (deduplicated by content hash), the tool
records and their size and category classifications (written once per file and
reused when the same catalog is run again, which is what lets a later reload
reuse classifications without a new model call), the run and its settings, the
per-tool cabinet calculations, the plan summary per bucket and grand total, the
rebalance moves, an execution audit row, and one validation row per tool flagged
with a size issue. A second migration adds the run-effective size and category
to the calculation rows so a reload can restore the exact delivered result even
when a technician override changed a value for that run.

The write hooks the existing "save this run when finished" control with its own
once-per-run guard, so a save writes the database copy a single time rather than
on every interaction. The database file lives at a local path under the user
home (overridable with KROMI_DB_PATH) so it is never placed in a synced folder.
Nothing reads from the database yet; that is the next phase.

## [v33.45] — persistence foundation (database Phase 0)

First step of moving persistence from scattered files to a single SQLite
database. This change is foundation only: it adds a standalone data layer and
nothing in the calculation path or the page imports it yet, so the application
behaves exactly as before.

What ships: a normalized schema under db/migrations covering uploaded files,
tool records, AI classifications, analysis runs, cabinet calculations, the plan
summary, rebalance events, engine executions, validation results, a versioned
override library, machine configurations, and AI training feedback. A thin
data-access module (db/store.py) using only the standard library handles the
connection (foreign keys enforced, WAL journaling), runs migrations and tracks
which were applied, seeds the default machine configuration from the engine
constants, and provides the file and run repositories the workflow will use.
Files deduplicate by content hash so re-uploading a catalog reuses its stored
copy and its classifications. The schema uses portable types and surrogate keys
so a later move to PostgreSQL is a dialect change here rather than a rewrite.

Strategy decision recorded for later phases: a reloaded run shows the stored
snapshot of what was delivered, together with the build version it ran under,
and warns when the current engine build differs. The AI classifications are
stored separately and reused on reload, so no OpenAI call is made when a past
run is opened.

## [v33.44] — move the operational mode control to the main screen

The "Cabinet composition" control now sits on the main screen, directly under Run
setup, instead of in the sidebar. It reads as a run-level decision alongside the
KTC-ID and customer, and the selectbox and the Carousel limit are laid out side by
side. Behaviour is unchanged: the same four modes, the same downstream override,
and the same size-fit highlighting.

## [v33.43] — Operational mode: override the cabinet composition

Adds a sidebar control, "Cabinet composition", that governs the cabinet layout
above the per-tool routing. Standard mode is unchanged and remains the default:
every tool still goes to the machine that best fits its size and turnover. The
three new modes override that decision for the whole catalog.

Helix only forces every vending tool into a Helix coil. Carousel only forces
every vending tool into a Carousel slot. Both drop lockers and the other vending
type from the composition, recompute each tool's coil or slot count, and assume
physical fit. Tools that do not fit the chosen cabinet are highlighted rather
than dropped: Helix only flags any tool larger than M (a spiral is small);
Carousel only flags the locker sizes (XXL, XLS, XXLS) that a slot cannot hold.

Helix plus Carousel (capped) keeps the normal routing, lockers included, and adds
a hard limit on the number of Carousels per supply point. When Carousel demand
exceeds the limit, the slowest-moving Helix-eligible tools spill into Helix coils
until the count is within the cap. L and XL tools cannot spill, because a spiral
is too small for them; if they keep the count above the cap they are highlighted
so the planner can repackage them or raise the limit.

The existing "Treat as Helix-fit (M)" convenience override works in every mode:
it reasserts a tool's size as M so it fits a coil. The active mode and the
Carousel cap are recorded in the Run_Metadata sheet, shown as a banner above the
results, and the size-fit highlight reuses the amber Result and Carousel_only row
colouring shipped previously.

Engine additions (engine/cabinet_math.py): apply_operational_mode forces the
single-type composition and recomputes resources; flag_unfit_for_mode marks the
size-unfit tools; apply_carousel_cap performs the capped spill. All three are
pure and never mutate their input. Standard mode runs the unchanged pipeline, so
existing catalogs produce identical results.

## [v33.42] — detect and resolve size-locked items that strand a near-empty Carousel

Closes the residual the previous two fixes left open. An L or XL tool is too big
for a Helix spiral, so it can only live in a Carousel; when a bucket is mostly
Helix items plus one such tool, the planner opens a whole Carousel for that one
tool and the rebalancer cannot fold it into the Helix. The result is a
lightly-used cabinet that is technically correct but wasteful. The planner now
detects this case, surfaces it, and offers a one-click resolution.

Detection is a read-only pass per bucket (`cabinet_math.detect_size_locked_items`):
it takes the Helix-ineligible Carousel items, resizes them to a Helix-fit on a
copy, re-runs the rebalancer, and flags them only if that removes a cabinet. The
comparison runs through the rebalancer, so the empty-cabinet threshold is
honoured automatically and a Carousel that is needed for its volume is never
flagged. The pass never mutates the plan.

Flagged items appear under a "Problematic size detected" heading with a
**Treat as Helix-fit (M)** button. Clicking it records the item in session state
and re-runs; before routing, that item's size is set to M so it routes and
consolidates as a Helix-fit tool, dropping the cabinet. The action only changes
the size the user asserts (it does not force a tool that will not physically fit
a spiral) and is reversible with a Reset control. Flagged rows are also filled
amber in the Result and Carousel_only sheets of the export so the cabinet
allocation / stockpiles view shows them at a glance, and a `SizeIssue` column is
added to those sheets when any item is flagged. Tests cover the lone-L and
lone-XL cases, a well-used Carousel that is correctly not flagged, the
no-candidate and single-cabinet cases, and that detection never mutates input.

## [v33.41] — let the rebalancer relocate XL vending items (no more size-pinned cabinets)

A follow-up to the boring-bar size fix, addressing the underlying mechanism. The
router (`decide_cabinet_type`) sends every non-locker size — S, M, L, and XL —
into vending, but the rebalancer's relocation rule only accepted S/M/L into a
Carousel. So any XL vending item (a large tool, a safety helmet, or
anything mis-sized to XL) was eligible for neither relocation target and pinned
whichever cabinet it sat in, blocking consolidation and leaving lightly loaded
cabinets. The Carousel — the larger vending compartment and the catch-all for
vending-sized tools — now also accepts XL during relocation, so the rebalancer
can fold an XL item into a Carousel instead of stranding it. Helix relocation
stays conservative (S/M only, since a spiral is small), and the true locker
sizes (XXL/XLS/XXLS) remain excluded. On the reference plant this fix alone
collapses the two-cabinet plan to one even if the offending bar had kept its XL
tag, so the two fixes are independent and reinforcing. Engine: the Carousel
branch of the rebalancer's `_is_size_eligible` gains XL. Tests: a rebalancer
case where the only path to one cabinet is relocating an XL item into a Carousel.

## [v33.40] — size boring bars by their measured dimension, not a blanket XL

The size heuristic classified every boring bar as XL regardless of its actual
size, so a thin Ø1.4 x 40 mm bar was tagged XL the same as a 300 mm one. Because
the rebalancer treats XL as too large for a Helix or Carousel, a single
mis-sized boring bar could pin a near-empty Helix open and block consolidation,
leaving two lightly loaded cabinets where one would do. Boring bars are now
sized from the diameter in the description, exactly like other tools (Ø1.42 ->
S, Ø20 -> L, Ø50 -> XL); the XL default applies only when no dimension can be
read, so an unspecified boring bar is still treated as a long, large tool. On
the reference plant this re-sized the offending bar from XL to S and let the
rebalancer fold the Helix into the Carousel, taking the plan from two cabinets
to one. Engine: the early blanket return in `classification.heuristic_size_category`
is removed; boring bars fall through to the existing diameter parser with the XL
fallback moved to the no-dimension case. Tests cover the small-, large-, and
no-dimension boring-bar cases.

## [v33.39] — presentation summary as a three-tier pyramid

The KROMI presentation summary slide now arranges its metric cards as three
stacked, centred tiers instead of a uniform grid: scope on top (supply points,
cabinets total), the cabinet-type breakdown in the middle (Helix / Carousel /
Lockers, only the types in use), and the item split on the bottom (items
managed, KTC items, and Kanban items when present). Each tier is centred, so the
narrower top row sits above the wider item row and the stack reads as a pyramid.
The cabinet tier collapses out only when a plan has no cabinets at all, leaving a
clean two-tier stack. Engine: a new `deck.summary_pyramid` returns the three
tiers as the content model; the renderer centres each tier and keeps the
alternating dark/bright card styling. The flat `summary_cards` helper is
retained. Validation: tests cover the tier grouping, ordering, present-only
cabinet types, the no-cabinet two-tier case, and Kanban hidden at zero.

## [v33.38] — System type override: two corrections to fixed-row handling

Two follow-ups to the v33.37 System type override, after reviewing real plans.

KTC-fixed rows now consolidate again. v33.37 pinned every fixed row (KTC and
Locker) against the rebalancer, which over-restricted: a KTC-fixed row is an
ordinary KTC vending item, and the rebalancer only ever relocates items between
vending cabinets (Helix/Carousel), never to Kanban. Pinning them blocked
legitimate cabinet merges for no benefit. The rebalancer now pins only
Locker-fixed rows (which it would otherwise dissolve into Helix/Carousel);
KTC-fixed rows are consolidated like any other KTC item. Bulk routing still
protects both KTC- and Locker-fixed rows, so the "never Kanban" guarantee for a
fixed KTC row is unchanged.

Forced lockers now consolidate into a single tier. v33.37 assigned each
Locker-fixed position its own size-matched tier, which could open separate
A/B/C lockers. Per the intended rule, all Locker-fixed positions in a bucket now
go into one tier: the one whose compartment fits the LARGEST such position. A
larger compartment holds smaller tools, so the smaller positions share that
locker rather than opening their own, and the per-tier cabinet count collapses
to ceil(positions / capacity). On the reference plan this turned three lockers
(A/B/C, one each) into a single Locker A, and combined with the restored KTC
consolidation reduced the plan from seven cabinets to five.

Engine: the rebalancer's protection test now keys on a fixed row being a Locker,
not on the fixed flag alone. Page: a per-bucket locker-consolidation pass (run
before the rebalancer, which leaves the consolidated locker alone) selects the
single tier from the largest fixed-Locker position and writes it back with an
audit reason. Validation: the System type tests were split into a Locker-pinned
case and a KTC-not-pinned case (identical setups with and without the fix
rebalance the same), and the harness category 8 now asserts a mixed XL+M
Locker set consolidates into one Locker A.

## [v33.37] — customer-specified System type override (Lagersystem)

When a customer states a desired storage system per tool (a "Lagersystem" /
"System type" column), the planner can now honour it instead of deciding
KTC/Kanban purely from consumption. The feature is opt-in: it only acts when
the column is mapped under "System type available (optional)". When it is left
unmapped, nothing in this release changes any plan.

Mapped values are read per row:

- **KTC** forces a vending machine. The row stays KTC even when its consumption
  is below the threshold, and the cabinet (Helix / Carousel / oversize Locker)
  is chosen by the existing `decide_cabinet_type` logic. It can never fall to
  Kanban.
- **KTC or Kanban** keeps the normal monthly-pieces threshold: KTC above it,
  Kanban below.
- **Locker** forces a size-matched locker tier (A 48 / B 72 / C 96), derived
  from the item size the same way the oversize taxonomy maps it, and extended to
  the regular S/M/L/XL sizes a customer may flag. Lockers use no spirals or
  carousel slots and consolidate through the existing per-tier locker counting.

Rows fixed to KTC or Locker are flagged `SystemTyp_Forced` and are protected
from bulk routing and from cabinet consolidation exactly like a technician
cabinet override: neither can move a fixed row. The override is applied after
library/technician overrides (so it is the final routing word for fixed rows)
and before bulk routing, so the protection holds end to end.

Engine: `routing_rules.parse_system_type` (KTC / KTC_OR_KANBAN / LOCKER / "",
German and English spellings); `cabinet_math.locker_for_size` (size -> tier,
consistent with `decide_cabinet_type` for xxl/xxls/xls); a `force_ktc` argument
on `route_and_size_row` that skips the Kanban gate; and a `SystemTyp_Forced`
guard added to `apply_bulk_routing` and to the rebalancer's protection test.
Page: an optional "System type available" column mapping (auto-guessed from
Lagersystem / System type / Storage system and German variants), the override
pass with a per-run summary caption, the System type column surfaced in the
trimmed export views, and a "System type override (Lagersystem): on/off" line
in the PDF parameter snapshot. Mapping plumbing (rename, dedup-preserve,
fingerprint, text cleaning) updated to carry the column. Validation: 21 new
unit tests plus a new end-to-end harness category (category 8), including a
no-op check proving the override OFF is byte-identical to a run without the
column.

## [v33.36] — quiet the runtime log: Arrow display + pandas FutureWarning

Two log-noise fixes surfaced on a recent pandas / pyarrow (Python 3.14) stack.
Neither changed any plan output — both were cosmetic warnings the app already
recovered from.

- **Arrow serialization error on raw previews.** A passthrough column from the
  source file that mixes Python types across rows (e.g. an order-number column
  with some int and some str cells) cannot be inferred by Arrow, so
  `st.dataframe` logged a repeated `ArrowTypeError` before auto-casting to
  string. A new `_arrow_safe` display helper pre-casts only the object columns
  whose values are not all strings to string, leaving numeric/bool/datetime
  columns untouched. It is applied to the two previews that render raw/full
  frames (the upload data preview and the archived-run work dump); curated
  previews were already safe. The table renders identically, without the error.
- **pandas FutureWarning in the stale-year diagnostic.** `preprocessing.py`'s
  `_n_stale_latest` ran `groupby(key_cols).apply(...)`, which pandas >= 2.2
  flags ("apply operated on the grouping columns"). It now selects the two
  columns the check needs (`Year` and the category) after the groupby — those
  are never group keys — which is the cross-version way to silence the warning
  without relying on `include_groups=` (pandas >= 2.2 only). A regression test
  promotes the warning to an error to keep it from returning.

## [v33.35] — per-class thresholds: popup UI + uniform default

Refines the v33.34 per-class thresholds after review.

- **Edited in a popup, not inline.** The per-class threshold fields now open
  from an "Additional threshold controls" button into a modal dialog
  (`st.dialog` where available, with an `st.popover` fallback on Streamlit
  < 1.37), with OK / Cancel, so they no longer crowd the sidebar. Values commit
  to session state only on OK/Apply; Cancel reverts to the standard threshold
  for all classes.
- **Every class defaults to the standard value, inserts included.** There is no
  longer an inserts-specific default of 3. When the controls are active, routing
  diverges only for the classes the user changes; a class left at the standard
  value behaves exactly like the standard threshold. When inactive, the single
  standard threshold runs the whole list (inserts included), unchanged.

## [v33.34] — pieces-based routing, per-class thresholds, regrind

Changes how the KTC/Kanban decision is made and adds reground-tool sizing.

- **KTC/Kanban now decided on monthly pieces, not monthly packs.** The
  routing gate compares each row's `Monthly_pcs` against the threshold
  (`routing_rules.threshold_for_row`); `route_and_size_row` takes a
  `monthly_pcs` argument for the gate and falls back to packs when it is not
  supplied. Physical sizing is unchanged: the Helix-vs-Carousel split, spirals,
  carousel stockpiles, cabinet counts, and the capacity buffer all still use
  packs, because packs are what the machine's physical space holds. The
  standard threshold default is now 1 (pieces); the two threshold inputs and
  the PDF/metadata are relabelled to pieces.
- **Optional per-tool-class thresholds.** A "Show optional thresholds" toggle
  replaces the insert-only switch. Off: the single standard threshold runs the
  whole list, inserts included. On: a threshold field appears per tool class
  (`constants.THRESHOLD_CATEGORIES`); inserts default to 3, every other class
  defaults to the standard value, and a row uses its class threshold when set
  (inserts resolved via the insert-detection fallback). The insert default
  packing-unit control (a sizing standardisation) is unchanged.
- **Regrind handling.** A new optional `Regrind` column (YES/NO) can be mapped.
  A reground tool kept in a Helix is floored to at least two spirals — one for
  new, one for reground, since the two cannot share a coil
  (`cabinet_math.regrind_spiral_floor`). An item that already needs two or more
  spirals is left as-is, and Carousel/Locker sizing is unchanged (the reserve
  already covers the combined new+reground consumption). The floor is applied in
  the main pipeline, the override re-route, and the consolidation rebalancer, so
  cabinet counts stay correct wherever a reground tool lands on a Helix. The
  flag survives deduplication and appears in the exports when present.
- **Tests.** 32 new cases (`test_threshold_pieces_and_regrind.py`) cover the
  per-class resolver, regrind parsing, the spiral floor, and the
  pieces/regrind paths in `route_and_size_row`. Full suite green.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses an internal build-version string defined in
`engine/build_info.py` and surfaced on every output.

## [v33.33] — empty-input crash fix

Fixes a reachable crash when a 0-row planning base reaches the engine.

- **Engine.** `prepare_planning_base` raised `TypeError: int() argument ...
  not 'Series'` on an empty input when a `Year` column was present and dedup was
  active (the default). Root cause: the stale-latest-year diagnostic reduced an
  empty `groupby(...).apply(...)`, whose `.sum()` is a Series rather than a
  scalar, so `int(...)` failed. `_n_stale_latest` now short-circuits to 0 on an
  empty base. The `TestEmptyInput` cases that pinned this behaviour now pass.
- **Page.** Added an early guard after the planning-base summary: an empty
  planning base now stops with a clear message ("no usable rows after
  preprocessing ...") instead of carrying an empty plan through classification,
  sizing, and export. A 0-row base can arise from an upload with headers but no
  data rows, or from a Code column that is entirely blank (those rows are
  dropped upstream).

## [v33.32] — stabilization

Release-readiness pass. No behaviour changes; the focus is making the current
state stable, documented, and verified.

- **Documentation aligned with reality.** README now lists all 20 engine
  modules (adds routing_rules, cabinet_math's route_and_size_row, kromi_numbering,
  invariants, run_prefs, evaluation), reports the current test count (1100), and
  documents the plan-integrity layer as a design principle.
- **Cache-key contract documented in code.** A tripwire comment at
  `_make_batch_cache_key` states the rule that any value affecting a per-item
  classification result must be cooked into the key (and that performance-only
  knobs must not be), so the one realistic future regression in that area fails
  review rather than shipping silently.
- **Verification.** Full suite green (1100 passed, 5 skipped); all 20 engine
  modules import cleanly; pages parse; customer-name and AI-tell scans clean.
  The only runtime warnings are two PuLP deprecations from the optional MILP
  optimizer, already neutralised by the pinned `pulp<4.0`.

## [v33.31]

### Fixed — cross-file session-state leakage (E6)
- **A new file now starts from clean column-mapping auto-detection.** Mapping-
  scoped session state (the optional/manual-mode and standard-special flags and
  the per-field mapping selections) is cleared when the uploaded file changes.
  Previously, once optional columns were hidden in a session, the manual-mode
  flag was never reset, so auto-detection of optional columns (Year, Site,
  ProductCategory, etc.) stayed suppressed for every subsequent file in that
  session — a later file could silently lose Year/Site mapping and produce a
  different plan than the same file would in a fresh session. The reset keys on
  the file's identity, so reruns of the same file are unaffected and the
  within-file hide/un-hide behaviour is unchanged.

### Audit (E6) — no other leakage found
- A dedicated adversarial audit confirmed the rest of the rerun model is clean:
  the plan is recomputed from current settings on every rerun (no cached plan),
  the run fingerprint covers all output-affecting settings, the cached AI/
  column-mapping functions are keyed on full content and return copies, engine
  module globals are read-only constants with no in-place mutation, and stored
  artifacts (PDF bytes, loaded archive) are overwritten or gated each run.

### Tests
- New: reset-mapping-state-on-file-change (6), covering first upload, same-file
  reruns (no reset), new-file reset, non-mapping state preserved, file removal,
  and the specific manual-mode cross-file leak. Total suite now 1100.

## [v33.30]

### Added — further conservation and consistency safeguards
- **Supply-point consumption conservation (E4).** Assigning rows to supply
  points now reconciles total consumption before and after: the partition mode
  reassigns rows and the replication mode divides each row's consumption across
  its copies, so neither may change the total. A mismatch raises a blocking
  error at the assignment step.
- **KROMI article-number uniqueness (E3).** The export step now verifies the
  assigned KROMI numbers are unique and well-formed (12 digits, ending in 0).
  A variant-counter overflow or two fingerprints colliding is surfaced before
  the workbook is used, instead of shipping duplicate article numbers.
- **VendMode / SystemCategory consistency (A5).** The integrity suite flags a
  KTC (in-cabinet) row carrying VendMode 'Bulk/Kanban' (warehouse mode, which
  implies Kanban). The common Kanban-defaults-to-Vending case is not flagged,
  as it is the documented default and not a contradiction.

### Fixed / diagnostics
- **Stale latest-year metadata diagnostic (B4, detection only).** When the
  latest year's ProductCategory or SizeCategory is blank for a code, an earlier
  year's value is retained; the planning-base summary now warns which codes are
  affected so a latest-year re-classification gap is visible. Behavior is
  unchanged (the earlier-year value is still used).
- **Routing reason refreshed on re-route (A4/E5).** When a library override
  re-routes a row across the KTC/Kanban threshold, its SystemCategory_Reason is
  now updated to reflect the new routing instead of keeping the pre-override
  reason.

### Tests
- New: supply-point conservation (5), KROMI uniqueness (5), VendMode
  consistency (4), stale latest-year diagnostic (5). Total suite now 1094.

## [v33.29]

### Fixed — audit follow-ups (export verification, arithmetic reconciliation, site normalization)
- **Export verification now validates the actual exported datasets (D1/D2).**
  The previous partition check compared the SystemCategory split of the plan
  to itself (tautological) and ran before the augment/user-view transforms.
  It now reconciles the real frames being written: the Result sheet must keep
  every plan row, and KTC-only + Kanban-only must partition the Result sheet
  exactly. A row dropped or duplicated by the export transforms is caught.
- **Integrity checks now run on the final state.** The rebalancer and capacity
  buffer mutate the plan after the preview-stage check, so the export step
  re-runs the full integrity suite on the final `work` — the authoritative
  verification of what ships. The export sub-frames (KTC/Kanban/Helix/
  Carousel sheets) are also re-derived from the final state, so their values
  stay consistent with the Result sheet after rebalancing (previously they
  could ship pre-rebalance values).
- **Arithmetic identity reconciliation (E1).** The integrity suite now asserts
  the defining formulas, not just value ranges: Target_packs = Monthly_packs x
  Coverage_days / days-per-month, and Monthly_packs = Consumption_pcs /
  consumption-period / PackUnits. A coverage edit that does not propagate to
  Target_packs, or a broken monthly-rate formula, is now caught.
- **Site normalization before key construction (C2).** Site-aware dedup now
  keys on a normalized label (case- and whitespace-folded, with int/float/
  string spellings of a numeric code unified), so a single physical site is
  never split into pseudo-sites by inconsistent casing or numeric formatting.
  The original Site value is preserved for display.

### Tests
- New: site normalization (6), arithmetic identities incl. via verify_plan (6),
  export-frame reconciliation (4). Total suite now 1075 passing.

## [v33.28]

### Fixed — hidden-miscalculation enforcement (HMA-1/2/3 + export reconciliation)
- **HMA-1: override → routing propagation enforced.** Library overrides that
  change ProductCategory or PackUnits now re-run the KTC/Kanban split and
  re-derive cabinet type and sizing for the affected rows, so routing
  reflects the corrected attributes instead of the decision made before the
  override. Rows whose routing was explicitly set (cabinet-type or vend-mode
  override) keep that forced type — tracked by a new `Routing_Overridden`
  marker. Re-routing reuses the same engine primitives via a new pure
  `engine.cabinet_math.route_and_size_row`. Replaces the prior
  detection-only warning with an actual fix plus a count of rows re-routed.
- **HMA-2: deterministic deduplication.** Before aggregating, rows are sorted
  to a fixed order (latest year, then highest consumption, then a stable
  content order), so the kept value for a conflicting code no longer depends
  on input row order. Equivalent datasets now produce identical plans;
  consumption totals are unchanged.
- **HMA-3: site-aware deduplication.** When a Site column is present it is
  part of the dedup key, so the same code at different sites is never merged
  and its per-site consumption is never misattributed. A blank site is
  treated as its own explicit group rather than inferred into a named site.
  Single-site datasets are unaffected.
- **Export partition enforced at runtime.** The KTC-only and Kanban-only
  result sheets are reconciled against the full plan on every run; a
  mismatch (a dropped or duplicated row) raises a blocking error.

### Tests
- New: `route_and_size_row` (7), `Routing_Overridden` marker (2), override→
  routing propagation integration (4), dedup determinism (3), site-aware
  dedup (2), and the export-partition check. Two lifecycle/aggregation tests
  updated to the new deterministic + site-keying semantics. Total suite now
  1059 passing.

## [v33.27]

### Added — plan integrity / reconciliation layer
- **Every run now self-verifies.** A new `engine/invariants.py` checks the
  conservation rules and state invariants after the plan is built, and a
  "Plan integrity check" panel reports PASS or lists any violation before
  the results. This turns structural miscalculations into visible failures:
  a future change that breaks an invariant (a dropped column, an unapplied
  setting, a stale routing decision) trips a check on the next run instead
  of shipping a wrong plan. Checks: routing partition (every row KTC or
  Kanban, no nulls/unknowns), pack units (>= 1, numeric), coverage (per-row
  days >= 1, Target_packs finite >= 0), sizing consistency (Kanban rows
  carry no vending capacity; Helix >= 1 spiral; Carousel >= 1 stockpile;
  no KTC row typed Kanban), consumption conservation (dedup conserves the
  total; filtering may only reduce it), and row accounting (counts
  non-increasing through filtering and dedup).
- Consumption sums are now tracked through filtering and dedup
  (`consumption_before` / `_after_year` / `_after_dedup` in the planning-base
  info) to feed the conservation check.

### Tests
- `tests/test_invariants.py` covers each check, the happy path (no false
  positives, including Locker rows), and seeded regressions. Total suite now
  1041 passing.

## [v33.26]

### Fixed / hardened
- **Per-listing column validation.** When a selected sheet (typically PPE)
  does not contain a mapped column, the run is now stopped if the missing
  column is critical (Code or Consumption) — those rows would otherwise be
  treated as having no demand and silently under-count the plan — and warns
  for non-critical columns. Previously such columns were silently empty.
- **Year-handling is order/spelling tolerant.** The dedup/year step now
  accepts the UI label as well as the internal value (case- and
  space-insensitive), so a label/value mismatch can never silently skip the
  latest-year filter.

### Added (hidden-miscalculation diagnostics)
- **Deduplication conflict warning.** When rows that merge into one code
  disagree on ProductCategory or PackUnits, the kept value depends on input
  row order, so the same data in a different order could classify or size
  differently (consumption totals are unaffected). The planning-base summary
  now reports how many codes have such conflicts.
- **Override routing-staleness warning.** KTC/Kanban routing is decided
  before library overrides. If an override changes a row's PackUnits or
  ProductCategory enough to move it across the KTC/Kanban threshold but no
  cabinet-type override was given, the split is not re-run — the app now
  reports how many rows are in that state so the stale routing is visible.

### Tests
- Year-mode aliases and dedup conflict detection covered by new tests.
  Total suite now 1025 passing.

## [v33.25]

### Added
- **Insert default packing unit control.** The value used to standardise
  inserts' pack size (previously hardcoded to 10) is now a sidebar control.
  Inserts are sized at this many pieces per pack; set it to match your
  insert box size. Default is 10, so existing behaviour is unchanged. The
  value is part of the change fingerprint.
- **Missing pack-size diagnostic.** After each run, if any rows had no
  usable pack size and were assumed to be 1 piece per pack, a warning now
  reports the count (this assumption inflates the monthly pack rate and can
  push items into KTC and enlarge sizing). Previously the count was only
  visible in the technical sheets.

## [v33.24]

### Fixed (audit follow-ups)
- **Standard/Special markers now accept simple flags.** In addition to the
  words standard/special (seven languages), the classifier recognises the
  binary encodings 1/0 and yes/no (1/yes = standard, 0/no = special;
  numeric 1.0/0.0 are normalised). Codes such as 8 are deliberately not
  mapped — rewrite the column to 1/0, yes/no, or standard/special before
  uploading. Also fixed a value-folding bug where a literal 0/0.0 was
  treated as empty and ignored.
- **Standard/Special and SupplierCode now survive deduplication.** Both
  columns were dropped by the dedup aggregation (StdSpecial always,
  SupplierCode under "Deduplicate by Code"), which silently disabled the
  coverage split and blanked SupplierCode in exports. They are now
  preserved through dedup (and SupplierCode is not double-counted when it
  is also the dedup key).
- **Coverage value no longer resets when mapping/unmapping the
  Standard/Special column.** The single and split coverage inputs now share
  a key, so a value set in single mode carries over to the standard field
  when the split appears (and back).
- **Hardened dedup against a missing Year column** (the aggregation no
  longer references Year unconditionally).

### Added
- **Routing & coverage diagnostics after each run.** The app now reports
  how many rows were classified standard / special / unrecognised, and how
  many inserts the insert threshold re-routed. If a Standard/Special column
  is mapped but nothing matches "special", or the insert threshold is on
  but no inserts exist, a clear warning is shown so a switched-on feature
  can no longer appear active while having no effect.
- **Cache fingerprint completed.** The insert threshold (and its toggle),
  the special coverage value, the Standard/Special and dimensions column
  mappings, the Helix overfill factor, the empty-cabinet threshold, and the
  rebalancer toggle are now part of the change fingerprint, so changing any
  of them triggers the "click Run" prompt consistently.

### Tests
- Binary-token classification, the 0-is-not-empty fix, and dedup survival
  for StdSpecial/SupplierCode/Year-absent are covered by new tests. Total
  suite now 1019 passing.

## [v33.23]

### Added
- **Separate KTC/Kanban threshold for inserts.** A new "Separate threshold
  for inserts" toggle in the sidebar adds a second threshold that applies
  only to inserts. Inserts cost far less than a drill or a mill, so a site
  can require them to move in higher volume (for example 10 packs/month)
  before they earn a vending slot, while every other tool keeps the
  standard threshold. When the toggle is off, the standard threshold runs
  the whole list unchanged. The per-row threshold and the reason string are
  computed by the tested engine.routing_rules helpers.
- **Standard / Special on-machine coverage.** A new optional column mapping,
  "Standard / Special", lets the coverage be split by tool class. When the
  column is mapped, the single "On-machine stock coverage (days)" control
  becomes two — "standard, in days" and "special, in days" — and each tool
  is sized with the coverage for its class. Marker values are recognised in
  French, Polish, German, Spanish, English, Slovak, and Slovenian
  (accent-insensitive; non-standard variants such as "niestandardowy" are
  read as special, not standard). Unrecognised values default to standard.
  When the column is not mapped, the single coverage value applies to every
  tool exactly as before. The Standard/Special field follows the "Hide
  optional columns" toggle like the other optional mappings.

### Tests
- New `tests/test_routing_rules.py` with 65 tests: insert detection,
  per-row threshold selection, standard/special classification across all
  seven languages including the non-standard edge cases and accent folding,
  and per-row coverage selection. Total suite now 994 passing (+65).

## [v33.22]

### Changed
- **Reduced the empty gap at the top of the sidebar.** With the collapse
  arrow hidden (v33.21), the sidebar header area was leaving a large blank
  space above the content. That space is now collapsed, so the "Back to
  picker" button and the "Controls" header sit near the top of the sidebar.

## [v33.21]

### Fixed
- **Sidebar can no longer be collapsed and lost.** The sidebar collapse
  arrow is hidden, so the sidebar stays visible at all times (it still
  starts expanded via the page config). Users reported clicking the arrow,
  losing the sidebar, and being unable to bring it back. Implemented as a
  CSS rule covering the control's markup across Streamlit versions.

## [v33.20]

### Changed
- **Run setup simplified to just Customer name.** The separate "Archive
  label" field is removed; when a run is saved, the archive is labelled
  with the customer name instead. The "Save this run when finished"
  checkbox now sits on its own row (fixes the vertical misalignment).
- **PPE sheet defaults to "— not used —".** A Tools-only catalog now shows
  its content immediately on upload instead of auto-selecting any sheet
  whose name happened to match a PPE pattern (which forced the user to
  clear it manually before the content appeared). A PPE sheet is selected
  explicitly when one exists.

### Fixed
- **Hiding optional columns now clears their assignment.** Previously,
  hiding the optional columns and then unhiding re-applied the
  auto-detected mappings (Site, SupplierCode, etc.), so a column could be
  silently re-assigned and used in a run unnoticed. Hiding now switches
  optional mapping to manual mode: stored picks are cleared and
  auto-detection is suppressed, so re-shown optional fields start
  unassigned and the user re-picks deliberately. Explicit user picks are
  preserved; stale picks from a previously uploaded file are dropped so the
  selectbox cannot crash.

### Tests
- 6 new tests in `tests/test_colmap.py` for the extracted
  `resolve_optional_default` helper that encodes the hide/manual-mode
  decision logic. Total suite now 929 passing (+6).

## [v33.19]

### Fixed
- **Gewindebohrer (taps) no longer misclassified as drills.**
  `normalize_product_category` matched the generic drill keyword "bohrer"
  inside the compound word "Gewindebohrer" and returned "drills", so when a
  catalog supplied "Gewindebohrer" as a product-category value (e.g. mapped
  from a German class-name column) the row was locked to drills and the
  deterministic tap detection was bypassed. In one real catalog this
  mislabeled 60 of 76 thread-tap rows as solid_carbide_drill, giving them
  KROMI code 13 (drills) instead of 15 (thread tools). The normaliser now
  checks the thread-tool keyword lists (thread mills, taps, thread dies)
  before the generic drill/mill match, mirroring the precedence already
  used in classify_with_evidence. Real drill compounds that are not thread
  tools — "Stufenbohrer", "Kernbohrer", plain "Bohrer" — are unaffected and
  still normalise to drills.

### Tests
- 7 new tests in `tests/test_classification.py`: four redirect cases
  (Gewindebohrer→taps, Gewindefräser→thread_mills,
  Gewindebohrfräser→thread_mills, Schneideisen→thread_dies) and three
  controls confirming Stufenbohrer, plain Bohrer, and Schaftfräser keep
  their drill/mill categories. Total suite now 923 passing (+7).

## [v33.18]

### Added
- **Load previous run now restores both the plan output and a
  re-uploadable copy of the data.** The archived-run view (reached via
  "Load past run" at the top of the page) gained a "Download this run's
  data as Excel (re-uploadable)" button. The regenerated workbook carries
  the original input columns plus the plan output, with KROMI numbers and
  the System (KTC/Kanban) column added by the same shared helper the live
  export uses. Re-uploading the file re-runs the plan, so a past run can
  be re-executed with different parameters without re-entering the data.
- New archives record the `ktc_id` and `customer_label` of the run, so a
  reloaded run regenerates KROMI numbers with the correct prefix. Archives
  saved before this build default to KTC-ID 191 on download.

### Changed
- The live Result export and the archived-run download now share a single
  `augment_for_export` helper in `engine/kromi_numbering.py`, so the two
  paths can never drift in which columns they add or how.

### Tests
- 6 new tests for `augment_for_export` (both columns added with a valid
  KTC-ID, System-only fallback when the KTC-ID is invalid or ToolClass is
  absent, Description_2 fallback, oversized-group graceful degradation,
  and original-column preservation). Total suite now 916 passing (+6).

## [v33.17]

### Changed
- **Run setup moved from the sidebar to the main screen.** KTC-ID,
  Customer name / label, the archive label, and the "Save this run when
  finished" option now appear in a "Run setup" section directly below the
  file upload and above the Listings selector. These describe the run
  rather than configuring the calculation, so they belong with the upload
  flow, not among the sidebar thresholds. The sidebar retains Site,
  reviewer name, overrides, and the catalog library.
- **KTC-ID and Customer are remembered per uploaded file.** Re-uploading a
  known catalog pre-fills the KTC-ID and customer entered last time,
  backed by a small JSON store (`runs/file_prefs.json`, override via
  `KROMI_FILE_PREFS_PATH`). New `engine/run_prefs.py` module; all reads
  and writes are defensive so a missing or corrupt store never breaks a
  run. The lookup key is the lower-cased file stem, so the same file from
  a different folder still matches.

### Tests
- New `tests/test_run_prefs.py` with 16 tests: file-key normalisation,
  save/load round-trip, multi-file isolation, value stripping, and
  defensive handling of missing/corrupt/non-dict stores and blank keys.
  Total suite now 910 passing (+16).

## [v33.16]

### Added
- **KROMI article numbers on the exported Result sheets.** Every exported
  Result, Result_Full, KTC_only, Kanban_only, Helix_only, Carousel_only,
  and Bulk_Routed sheet now carries a `Kromi_Art_No` column. Numbers are
  12-digit, all-numeric, end in 0, and unique within the catalog. The
  numbering logic is universal across all customers; only the KTC-ID (the
  first three digits) changes per customer. The anatomy is
  `[KTC-ID 3] + [Kromi code 2] + [dimension 4] + [variant 2] + [0]`, with
  holders using the 5-digit `20008` code and a 1-digit dimension field.
  The variant counter (00-99) disambiguates physically different articles
  that share a dimension fingerprint. Implemented in the new
  `engine/kromi_numbering.py` module with a parameterized `KromiRuleset`
  (single universal ruleset; KTC-ID supplied per run).
- **System column on the exported sheets.** A `System` column showing
  `KTC` (routed to a vending cabinet — Helix, Carousel, or Locker) or
  `Kanban`, derived from the existing SystemCategory / CabinetType
  routing. No new routing logic; the column surfaces what the plan
  already decided.
- **KTC-ID sidebar field** under Scope & overrides. Three-digit input,
  defaults to `191`, env override `KROMI_DEFAULT_KTC_ID`. Drives the
  first three digits of every generated KROMI number. An invalid KTC-ID
  skips KROMI generation with a warning rather than aborting the export.
- **"Hide optional columns" toggle** in the Column mapping section. When
  on, every optional column mapping is hidden and left unassigned (not
  auto-detected); only the required Code, Description, and Consumption
  fields are shown.

### Tests
- New `tests/test_kromi_numbering.py` with 35 contract tests: the four
  invariants (12 digits, all-numeric, ends-in-0, unique), the full
  ToolClass-to-code matrix, the holder special case, step-drill keyword
  override, variant overflow handling, dimension extraction edge cases,
  and ruleset parameterization. Total suite now 894 passing (+35).

## [v33.15]

### Fixed
- **PDF parameter snapshot disagreed with Excel `Run_Metadata` on
  `Tools+PPE handling`.** When the user kept the "Separated" radio
  button selected from a prior run and then uploaded a Tools-only file
  (no PPE sheet), the page silently overrode the effective `calc_mode`
  to "Combined" — which is the right behaviour, since "Separated"
  doesn't mean anything with only one listing. But the PDF parameter
  snapshot read directly from the raw UI selector `calc_mode_ui`, not
  from the overridden `calc_mode`, so it would show "Separated" while
  the engine actually ran Combined and the Excel `Run_Metadata.Calc mode`
  field correctly recorded "Combined". One-line fix at line 3681 of
  `pages/1_Kromi_Planner.py` switches the param snapshot to read the
  effective `calc_mode`, so both surfaces always agree. No engine logic
  touched; test count unchanged at 859 passing.

## [v33.14]

### Fixed
- **Separated Tools+PPE mode — PDF headline reported 0 cabinets.** The
  `build_per_sp_summary` helper in `engine/distribution.py` grouped the
  planning frame by the `SupplyPoint` column, which is `1` for every row
  in Separated mode (Tools and PPE are *listings* within the same supply
  point, not separate supply points in the planning sense). The function
  then looked up cabinet counts in `bucket_plans` by the synthetic "All"
  label, found nothing (Separated-mode bucket plans are keyed by
  listing name), and returned zeros — while the Excel Summary sheet and
  the per-SP detail PDF pages correctly showed the full 6-cabinet plan.
- **Separated Tools+PPE mode — per-SP pie chart and subclass tables
  showed combined totals on every page.** `build_per_sp_distribution`
  and `build_per_sp_subclass_breakdown` had the same SupplyPoint-only
  grouping issue. Result: the Tools PDF page and the PPE PDF page
  rendered the identical Mills + Drills + Others breakdown of the
  combined catalog rather than each listing's actual contents.

### Changed
- The three distribution helpers gained one optional parameter,
  `listings: list[str] | None = None`. When `None` (the default and the
  Combined-mode path used by ~every catalog), behaviour is unchanged.
  When a list of listing names, the helpers group the working frame by
  the `Listing` column instead of `SupplyPoint`, return one entry per
  listing, and (for the summary helper) omit the Grand Total row.
- The planner page passes the new parameter only when the user selects
  Separated mode, computed once at the top of the run as
  `listings_arg = listings_iter if separated_mode else None`. Four call
  sites pass it through: the screen drilldown, the PDF builder, the
  Excel exporter, and the on-screen headline table.
- The PDF builder and the on-screen drilldown grew a small lookup
  fallback: try the bucket label directly first (matches listing-name
  keys in Separated mode), then fall back to the SP-integer parse
  (Combined-mode behaviour), then to the `'__all__'` aggregate.

### Tests
- Eleven new contract tests in `tests/test_distribution.py`:
  `TestBuildPerSpSummarySeparated` (6 tests pinning one-row-per-listing,
  no Grand Total, correct cabinet counts, per-listing consumption
  filtering, and Kanban-only listings still emitting a row),
  `TestBuildPerSpDistributionSeparated` (3 tests pinning that pies are
  filtered per listing), and `TestBuildPerSpSubclassBreakdownSeparated`
  (2 tests pinning that subclass tables exclude the other listing's
  tool classes).
- Three Combined-mode regression tests guard against accidental
  behaviour drift in the dominant case
  (`TestBuildPerSpSummaryCombinedRegression`,
  `TestBuildPerSpDistributionCombinedRegression`).
- Total suite now 859 passing (+14 since v33.13).

## [v33.13]

### Added
- **Column-lifecycle test suite (`tests/test_column_lifecycle.py`).**
  One test class per canonical column the planner accepts —
  `Code`, `Description`, `Description_2`, `Consumption_pcs`, `PackUnits`,
  `ProductCategory`, `SizeCategory`, `Year`, `SupplierCode`, `Program`,
  `Site`, `PackageDimensions`, `Listing`, `SupplyPoint`. Each class
  proves the column survives the preprocessing dedup, that its
  documented aggregation semantics hold (sum for `Consumption_pcs`,
  first-non-empty for free-text columns, first-positive for `PackUnits`,
  max for `Year`, distinct-join for `Program`), and that the column's
  absence does not break preprocessing. A combined-fixture test
  exercises every column together and would have caught the v33.12
  silent fit-check bug at test time. A discipline guard
  (`TestColumnLifecycleDiscipline`) lists the expected column-test class
  names so adding or removing one is a visible diff in code review.
  Thirty-one new tests in total; total suite now 845 passing.
- **Integration test for preprocessing → fit-check
  (`tests/test_fit_wiring.py::TestFitCheckSurvivesDedup`).** Exercises
  the actual path the v33.12 bug travelled — input with duplicate Codes
  → `prepare_planning_base` → `_apply_fitcheck` — and asserts the
  expected dispositions (`ok`, `misfit`, `no-dims`). Unit tests of the
  per-row fit logic were already in place; this one closes the gap
  where the unit tests bypassed dedup entirely.

### Development discipline
- Adding a new canonical column to the rename map or to
  `engine.preprocessing.agg_spec` now requires adding a corresponding
  test class in `tests/test_column_lifecycle.py` and updating
  `EXPECTED_COLUMN_TESTS` in the discipline guard. This is enforced by
  the discipline guard test, which fails when a class listed in
  `EXPECTED_COLUMN_TESTS` is missing.

## [v33.12]

### Fixed
- **Dimensional fit-check silently no-op'd when dedup was on.** The
  `prepare_planning_base` groupby in `engine/preprocessing.py` aggregated
  only the columns named in its `agg_spec` dict. `PackageDimensions` was
  not in that dict, so when deduplication ran (the default for catalogs
  with any duplicate Code) the column was silently dropped. The page's
  fit-check guard `if col_dims and "PackageDimensions" in work.columns`
  then evaluated false and the whole block no-op'd — the user saw no
  `Fit_*` columns and no warning. `Site` had the same issue. Both
  columns are now preserved through dedup via `first_nonempty`
  aggregation when present. Three regression tests in
  `test_preprocessing.py` cover the preservation and the
  no-optional-columns fallback.

### Added
- **Tooltips on the column-mapping dropdowns.** Each of the twelve
  mapping selectors now carries a `help=` string explaining what the
  field is used for, what makes it required, and (for optional fields)
  what the planner does when it is unmapped. Surfaced as the standard
  Streamlit "?" icon next to each label, matching the rest of the
  sidebar.

## [v33.11]

### Changed
- **`.env.example` trimmed to what is actually configured.** The previous
  template documented every environment variable the code reads, including
  internal tuning constants (batch size, timeouts, cost-estimate
  calibration). Those constants have working defaults and are not
  user-facing settings; listing them in the template suggested they needed
  configuring when they do not. The template now contains only
  `OPENAI_API_KEY` and an optional `OPENAI_MODEL` override, matching what
  a real `.env` looks like in practice. The internal tunables remain
  readable from the environment for advanced use and are referenced in
  `pages/1_Kromi_Planner.py`.

## [v33.10]

### Added
- **`.env.example` template.** Ships in the package root with every
  environment variable the app reads, grouped by purpose: the OpenAI key
  and model identifier at the top, then optional batch/timeout tunables,
  cost-estimate calibration, and classifier guardrails. Standard
  `copy .env.example .env` workflow; only `OPENAI_API_KEY` typically needs
  filling in.
- **`.gitignore`.** Protects `.env` and its variants from accidental
  commits, and excludes the runtime directories (`runs/`, `catalogs/`,
  `overrides/`), Python caches, lint/test caches, and common editor/OS
  noise.
- **Launcher detects a missing `.env`.** `run.bat` now checks for the
  file before starting the app. If absent, it prints a one-line notice
  explaining that AI fallback will be disabled and points at
  `.env.example`. The notice is informational only; the app still starts.

## [v33.9]

### Added
- **Windows launcher (`run.bat`).** Double-click in the package root to start
  the app. On first launch the script installs the Python dependencies from
  `requirements.txt` automatically; subsequent launches skip straight to the
  Streamlit start. Removes the need to remember `streamlit run Home.py` for
  reviewers who would rather not open a terminal. The launcher checks for
  Python on `PATH` and prints a clear remediation message if it is missing.

## [v33.8]

### Fixed
- **Customer identifier in a docstring example.** The `_export_name` helper
  on the planner page used a real catalog name as its `<source>` example.
  Replaced with a generic placeholder; the shipped tree (`.py` + `.md`) is
  clean of the known customer/site identifiers.
- **Changelog structure.** The legacy `[Unreleased]` section that sat
  between versioned releases was promoted to `[v32]` to match its shipped
  status. The Keep-a-Changelog ordering convention is now consistent
  across the file.
- **Requirements grouping.** `pulp` was filed under a "test suite (optional)"
  comment but is the MILP backend for the optimizer panel.
  Re-grouped with its real purpose.

## [v33.7]

### Fixed
- **Customer identifier leaked into the shipped README example.** The
  "Output filenames are meaningful" entry used a real customer catalog name as
  its example filename. Replaced with a generic `<catalog>` placeholder and
  re-scanned the full shipped tree (`.py` + `.md`) for the known customer/site
  identifiers — clean.

## [v33.6]

### Fixed
- **Build stamp was missing from Excel exports when the audit toggle was off.**
  The `Run_Metadata` sheet (which carries the `Build` and `Timestamp` rows
  added in v33.5) was gated behind the "include technical/audit" checkbox, so
  a normal export shipped without the stamp on the Excel side — defeating the
  point of the build label. `Run_Metadata` is now always written; only the
  heavier `Audit_Summary` and `Bucket_Compare` sheets remain behind the toggle.

## [v33.5]

### Added
- **Build stamp on every output.** `engine/build_info.BUILD` is the single
  source of truth for the build label, surfaced on the Streamlit sidebar, the
  per-SP PDF cover ("Build v33.5"), the Excel `Run_Metadata` sheet (top row),
  and every deck slide's date footer. Two runs that disagree must carry
  different labels, so opening any file identifies which code produced it. A
  new test (`test_build_info.test_single_source_of_truth`) fails if any source
  file outside `engine/build_info.py` hard-codes a `"vNN"` literal, preventing
  a future drift back to the old single-label state. The patch component of
  the build is incremented for every code change that ships.

## [v33]

### Fixed
- **Rebalancer reported `cost_at_destination = 0` and approved phantom
  consolidations.** Same root cause as the optimizer: a Carousel/Locker item
  carries no `Spiral_capacity`, so the rebalancer's cost-in-Helix helper
  (`_spirals_for`) fed `None` into `compute_helix_spirals_needed` and got 0
  spirals. It therefore "moved" a fast mover (e.g. a 44.5 packs/month insert)
  into a Helix at zero cost, eliminated the source Carousel, and recorded a
  destination cost of 0 — a consolidation that would overfill the Helix in
  reality. `_spirals_for` now derives the spiral capacity from size + category
  when the stored value is missing, so projected promotions use real spiral
  counts and only capacity-feasible consolidations commit. New regression test
  asserts a Carousel→Helix move always costs >= 1 spiral (`test_cabinet_math`).
- **Size category mis-parsed European metric diameters — tiny drills read as
  XL.** `heuristic_size_category`'s diameter regex didn't handle comma decimals,
  leading zeros, or the space after `Ø`, and a bare `d` matched deep-hole
  notation. So `Ø 02,40mm` (2.40 mm) grabbed the `40mm` fragment → 40 mm → XL;
  `Ø 01,02mm … 6xD 130°` matched the `130°` point angle → 130 mm → XL. About
  530 of 1,448 items (mostly 1–6 mm drills) were sized XL. The marker now allows
  a separator and requires `d=` / `D<digits>` (a negative lookbehind excludes
  `…xD` deep-hole depth), and the number captures full decimals, so the real
  value is read. On a real catalog the bogus XL count drops from 530 to 4, and
  a Ø16 mm mill that the AI had sized XXL (forcing its own Locker cabinet) now
  reads L and routes to Carousel — typically removing that cabinet. New
  regression tests cover the European formats and the deep-hole trap
  (`test_classification`, +6).
- **Optimized-allocation panel reported impossible cabinet savings.** The
  solver was fed `helix_units = 0` for every Carousel item, because the
  heuristic only stamps `Spiral_capacity` on rows it routes to Helix (Carousel
  rows carry `None`, and `compute_helix_spirals_needed(tp, None)` returns 0).
  With zero helix cost, CBC packed all Carousel items into a single Helix for
  free and reported phantom savings (e.g. 405 items "collapsing" a 3-cabinet
  plan to 1). The optimizer now derives each item's would-be Helix cost from
  its size + category via a new pure helper `helix_units_for_routing`, so no
  item is weightless. On a real 260-item run the panel now correctly shows
  2 cabinets (a genuine, capacity-feasible saving of 1) instead of 1. New
  regression tests assert helix units are never zero for positive demand and
  that the solver's routing stays within cabinet capacity (`test_optimization`,
  +5).
- **Technician review "Vending only" filter showed Kanban items.** The filter
  tested `VendMode == "Vending"`, but a low mover (`CabinetType == "Kanban"`,
  below the KTC throughput threshold) keeps `VendMode == "Vending"` because
  bulk routing never touched it — so it leaked into the vending view. The filter
  now keys on the row's *disposition* instead. The "Show" control offers three
  mutually exclusive, exhaustive buckets — "In a vending machine
  (Helix / Carousel / Locker)", "Kanban — low movers", and
  "Bulk/Kanban — routed families" — plus All rows / With override / Without
  override. Validated against a real 1,448-row catalog: the vending bucket
  returns the 527 KTC items with zero Kanban rows, and the three dispositions
  partition every row exactly once.

## [v32]

### Added
- **KROMI presentation deck (.pptx).** One-click, KROMI-branded slide deck of a plan: a
  cover, a plan-summary slide of the headline figures (supply points, cabinets, machines by
  type, items), and a cabinet line-up drawn from the real KROMI machine artwork (Carousel,
  Helix Master/Slave, Locker). New pure content model `engine/deck.py` (summary cards +
  line-up groups, unit-tested) and renderer `presentation.py` (python-pptx, kept out of the
  engine); the green logo and machine renders live in `assets/`. New dependency
  `python-pptx`. Fonts render as MetaOT where the corporate font is installed, otherwise a
  system fallback.
- **AI column mapping.** Optional "Suggest column mapping with AI": sends the file's headers
  and a few sample rows to the model and proposes the header→field mapping. New engine module
  `colmap.py` (prompt builder, strict JSON schema, parser that validates suggestions against
  the real columns). Off by default; the deterministic header guesser runs regardless, so AI
  only fills gaps.
- **Inch-dimension size estimation.** `classification.py` now derives a size category from
  inch dimensions in descriptions (e.g. `1/4"`, `.3750"`) instead of sending those rows to AI
  purely to estimate size. Conservative parsing; results tagged `Heuristic`.
- **Cabinet planogram (Excel).** Optional "Planogram" sheet that draws each proposed cabinet
  as a grid, places every tool in a numbered compartment grouped by family, and colours each
  by classification confidence. New engine module `layout.py` (compartment allocation).
- **Standard vs technical Excel.** The workbook now defaults to a clean everyday set
  (Summary, per-supply-point Presentation, a trimmed Result, the KTC/Kanban/Helix/Carousel
  breakdowns, Planogram). A "Include technical / diagnostic sheets" toggle adds the full
  audit Result, run metadata, audit summary, distribution sheets, and the overrides audit.
- **Imported-catalog archiving.** Every unique tool list imported into the
  planner is now recorded in a local `catalogs/` library, deduplicated by
  content hash (re-importing an identical list bumps a counter instead of
  storing a copy). A read-only "Imported catalog library" view in the sidebar
  shows what has been archived (first/last seen, import count, row/column
  counts, source filename). New engine module `catalog_archive.py`; archiving
  is best-effort and never blocks or alters an import.
- **Optional dimensional fit-check.** When a customer document includes a
  package-dimensions column, the planner can verify each item physically fits
  its assigned cabinet and suggest a better one when it doesn't. The feature
  is opt-in: it activates only when that column is mapped, and otherwise the
  planner behaves exactly as before (category-size approximation).
  - New engine module `dimensions.py` — parses package dimensions (W/D/H, Ø×L,
    single values) from free-text columns, with unit conversion and European
    decimal/thousands disambiguation.
  - New engine module `fitting.py` — orientation-free geometric fit against
    real compartment envelopes (Helix coil, Carousel rect/pie slots, Locker
    boxes including the split 72-box model), with validate-and-suggest
    dispositions.
  - Real manufacturer compartment dimensions encoded in `constants.py`, sourced
    from engineering drawings (ACD spirals, Storetec locker sheets, Häwa body
    drawing, carousel drawing K00002535).
  - Fit results appear in a new on-screen panel and in the exported Result /
    KTC sheets; counts and the cabinet plan itself are unaffected.
  - Test coverage: `test_dimensions.py` (29), `test_fitting.py` (38),
    `test_fit_wiring.py` (10).
- Continuous-integration workflow (`.github/workflows/ci.yml`) running lint,
  type-check, and the full test suite on Python 3.10 / 3.11 / 3.12.
- Linter and type-checker configuration (`ruff` + `mypy`) in `pyproject.toml`.
- Project `README.md` documenting architecture and how to run/test.
- This changelog.

### Changed
- AI ETA/cost estimate calibrated to observed gpt-5-mini behaviour (realistic per-batch
  seconds and output-token-per-item figures), and the initial ETA now accounts for parallel
  workers (a wave model) instead of assuming serial batches. Estimate-only — the plan and
  classification are unchanged.
- Test suite grown to 780 as the modules above were added.
- Engine code formatted with `ruff format`; type hints modernized
  (`List`/`Optional` → `list`/`X | None`). No behavioral change — all
  regression checks and tests remain identical.

### Fixed
- Removed real customer/site identifiers that had leaked into tests and a docstring (a
  sample column header and example names); shipped code and docs no longer contain customer
  identifiers.
- Streamlit `st.components.v1.html` deprecation: the combined-download button uses a
  version-safe `st.iframe` / `components.html` shim, so it keeps working after the API is
  removed.
- Removed two dead local variables surfaced by static analysis
  (`total_cabs_before` in the rebalancer, `code_upper` in the classifier).

## Taxonomy alignment

### Added
- Product classification aligned to the full Kromi `VS_PRODUCT_CAT` hierarchy:
  product categories expanded from 10 to 24, tool-class subtypes from 24 to 81.
- New categories: taps, thread mills, thread dies, counterbores, tool holders,
  grinding tools, brushes, broaches, honing tools, gear-cutting tools,
  centre points, welding consumables, punching tools, form steel.
- Multilingual keyword tables (DE/EN/FR/ES/PT/PL/CZ/SK/SL/DK) for the new
  categories, derived from the taxonomy export.
- Second-level (L2) detail in tool-class derivation: e.g. spiral vs. step vs.
  core drills; counterbore subtypes; tool-holder interfaces (HSK/SK/VDI/Capto).
- Test coverage for the new taxonomy (`test_taxonomy_alignment.py`,
  `test_classification_kromi.py`).

### Fixed
- **Taps were misclassified as drills.** German compound words such as
  *Gewindebohrer* matched the generic *bohrer* (drill) keyword by substring.
  Threading-tool detection now runs ahead of the generic drill/mill sweep, so
  taps, thread mills, and thread dies classify correctly.
- Recognized additional vocabulary that previously fell through to the AI
  fallback: insert abbreviation *WSP*, hole cutters (*Bohrkrone*), guide bars,
  and several Kromi accessory/holder sub-names.
- On the reference catalog, deterministic (non-AI) classification coverage rose
  from ~74% to ~100%, and overall taxonomy accuracy to ~96%.

## Engine extraction

### Changed
- Extracted all planning logic out of the Streamlit page into a standalone,
  side-effect-free `engine/` package (constants, text utilities, classification,
  cabinet math + rebalancer, distribution summaries, overrides, run archive,
  preprocessing).
- The main planner page shrank by roughly a third as a result.

### Added
- Comprehensive unit-test suite (~600 tests) covering every engine module, plus
  optional integration tests that validate the classifier against sample
  catalogs.
- JSON-snapshot regression harness used to prove the extraction was
  behaviour-preserving at every step.

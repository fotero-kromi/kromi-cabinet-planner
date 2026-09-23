# Kromi Cabinet Planner - working rules

Read this file completely at the start of every session. It carries the rules the
owner has set over many releases; they are not optional.

## What this is

- An internal KROMI tool. Staff upload a customer's tool list (Excel), map its
  columns, and the app classifies every tool, routes it to KTC vending (Helix
  spirals, Carousel compartments, Lockers) or Kanban, sizes or fits the cabinets
  per supply point, assigns 12-digit KROMI article numbers and exports a result
  workbook, takeover sheets, an article setup sheet and a deck.
- The owner is the Head of Logistics: product owner and technical lead, not a
  professional developer. Explain decisions in plain words.
- Today: Python 3.10 to 3.12, Streamlit 1.58 UI (`Home.py`, `pages/`, `ui/`), a pure
  pandas engine (`engine/`), SQLite (`db/`). A rewrite without Streamlit is being
  prototyped on branch `rewrite/fastapi-react` (see `docs/Rewrite_Decision.md`).

## Commands

```bash
pip install -r requirements-dev.txt          # dependencies (cloud sessions do this at start)
streamlit run Home.py                        # run the app
python tools/check.py                        # lint, types, customer-name scan, wording scan
python tools/check.py --tests                # the same plus the full suite (the release gate)
python tools/synthetic_golden.py --check     # synthetic golden gate on its own
python tools/synthetic_golden.py --update    # only after an intended result change
python tools/package_release.py . kromi_app_vXX.YY.zip   # release zip (allow-list)
```

## Non-negotiable rules

1. **Argue before implementing** anything correctness-sensitive or architectural:
   state the options, the recommendation and the risk, then wait for the owner's go.
2. **Tests first.** Write the test, run it and show it failing, then implement.
3. **Results never change by accident.** The synthetic golden gate
   (`tests/test_synthetic_golden.py`) must stay green. If a change is meant to
   change results, run `--update` and say why in the CHANGELOG.
4. **No customer data in the repository.** Never write a customer name in code,
   docs, tests, commit messages, PR text or issues; `tools/check.py` and
   `tests/test_check_tool.py` enforce it with hashed names. Customer workbooks
   (`*.xlsx`, `*.csv`) are git-ignored; never force-add one.
5. **No runtime state in the repository.** Tests isolate the database, preferences
   and log (`tests/conftest.py`). Ad-hoc scripts must set `KROMI_FILE_PREFS_PATH`,
   `KROMI_DB_PATH` and `KROMI_LOG_PATH` to temporary paths.
6. **The engine stays pure**: nothing in `engine/` imports Streamlit (an AST test
   checks it). New domain logic goes into `engine/`, not into the page.
7. **Wording**: no em dash (use "-"), none of the filler words the check lists.

## Release ceremony (every build)

1. Tests red first, then green.
2. Bump `BUILD` in `engine/build_info.py`; add a CHANGELOG entry at the top (what,
   why, verification with test counts).
3. `python tools/check.py --tests` all green; report passed / skipped / failed.
4. Synthetic golden unchanged, or updated with the reason stated.
5. Private golden gate: it needs a real customer workbook, which never enters the
   repository, so it cannot run in a cloud session. When a change touches the
   planning pipeline or the exports, say so in the PR; the owner runs it in the
   Claude chat project before merging.
6. Commit as `vXX.YY: <summary>`, push the session branch, open a PR to `main`.
   The owner merges it and publishes a GitHub release tagged `vXX.YY` on `main`
   (the release page offers the source zip for the Windows install).
7. Update `docs/Roadmap_Status.md`.

## Git

- `main` is what users run. Never push to `main` directly; work on the session
  branch and open a PR.
- `rewrite/fastapi-react` is the rewrite prototype; its PRs target that branch.
  After each release on `main`, merge `main` into it (through a PR) so engine
  fixes reach it.
- Commit messages end with the attribution lines the environment requires.

## Talking to the owner

- English, concise, bottom line first; no narration of routine steps.
- German deliverables (emails, customer texts): add a literal English translation,
  and use only characters on a German keyboard (no en or em dash, no middle dot).
- Name things in plain words (for example "the supply point", not an internal key).

## Know before you change planning logic

- `docs/Domain_Rules.md`: Helix, Carousel, VPE and takeover arithmetic, the fixed
  configuration, numbering. Most of it is pinned by tests; read it first.
- `README.md`: architecture, module map, operational modes, configuration.
- `docs/Roadmap_Status.md`: what shipped, owner decisions, what is next.
- `docs/Code_Professionalization_Plan.md` and `docs/Principal_Audit_v34.47.md`:
  why the page is structured the way it is and what the audit asked for.
- Streamlit test quirks: `AppTest` optional column-mapping seeds are popped by the
  new-file reset, so select them after the first run; a settings change clears
  results and the new fingerprint is stored only on the next run.

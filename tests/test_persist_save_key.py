"""Guard: the database save key must derive from the full run fingerprint.

The persist block at the end of the planner page saves a completed run once
per distinct run, deduplicated by a session-held key. Up to v34.08 that key
was a hand-picked ten-field tuple that leaned on outcome fields (total
cabinets, row count) as proxies. Two runs whose differences lay outside those
fields (helix threshold, operational mode, overfill, consumption months,
overrides, ...) and whose cabinet totals happened to match collided, and the
second run was silently never archived.

The full run identity already exists: ``_current_fingerprint`` is computed
from the file, sheets, column mapping, and every control
(engine/run_fingerprint.py). This guard pins the save key to it, in the style
of the factor-injection guard: a source-level contract that fails the suite
if the key ever regresses to a hand-rolled subset.
"""

import re
from pathlib import Path

_PAGE = Path(__file__).resolve().parent.parent / "pages" / "1_Kromi_Planner.py"


def _save_key_expression() -> str:
    """The right-hand side of the ``_save_key = (...)`` assignment."""
    src = _PAGE.read_text(encoding="utf-8")
    m = re.search(r"^_save_key = \((.*?)^\)", src, re.DOTALL | re.MULTILINE)
    assert m, "the _save_key assignment was not found in the planner page"
    return m.group(1)


def test_save_key_uses_the_full_run_fingerprint():
    expr = _save_key_expression()
    assert "_current_fingerprint" in expr, (
        "the database save key must include _current_fingerprint so any "
        "settings change produces a distinct archived run"
    )


def test_save_key_has_no_outcome_proxy_fields():
    expr = _save_key_expression()
    for proxy in ("total_cabs", "rows_after_dedup"):
        assert proxy not in expr, (
            f"the save key must not lean on the outcome field {proxy!r}; "
            "outcome proxies let distinct runs collide when their results match"
        )


def test_save_key_covers_the_effective_override_content():
    expr = _save_key_expression()
    assert "_ov_sig" in expr, (
        "the save key must include the override-content signature; the "
        "fingerprint carries only the apply-overrides flag and the scope, so "
        "a run corrected in the live editor, or recomputed against a "
        "different database set, would otherwise share its key with the "
        "uncorrected run and never be archived"
    )

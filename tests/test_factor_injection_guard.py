"""Guard: run-time sizing factors must be passed explicitly, never defaulted.

Two production bugs in the v34 line (the Helix single-spiral overfill mis-sizing)
came from calling a factor-sensitive engine function without forwarding the
run-time factor, so the engine silently fell back to its default constant (1.1).
A token-level diff could not see it, because the call name matched a page shim
that *did* inject the factor while the actual call resolved to the bare engine
function.

This test pins the invariant. For every engine function that exposes a
*defaulted* sizing-factor parameter, every call site that could omit it must pass
it explicitly:

  * ``engine/plan.py`` imports the engine functions under their real names, so a
    call there with the factor missing is a real omission.
  * The page reaches the bare engine functions only through ``_engine_<name>``
    aliases (inside its shim bodies); those calls must forward the factor too.

The page's own shims (same name as the engine function, but no factor parameter)
are the *fix*, not a violation, so they are not checked here; they are what
injects the factor.

Scope note: ``carousel_fill_ceiling`` and ``empty_cabinet_threshold_pct`` are
deliberately excluded. Those controls are not yet wired into the page (0 page
references), so the engine's "off" defaults (1.0 / 0.0) are the intended current
behavior. Whether they should reach the carousel cap is tracked separately as a
correctness question (review item Q5); when resolved, add them to ``FACTOR_SET``.
"""

import ast
import inspect

import engine.cabinet_math as cabinet_math
from tests._paths import PLANNER_PAGE, PLAN_MODULE

# Sizing factors that are wired today and must always be forwarded explicitly.
FACTOR_SET = frozenset({"overfill_factor", "helix_overfill_factor", "carousel_reserve_factor"})

PAGE = PLANNER_PAGE
PLAN = PLAN_MODULE


def _defaulted_factor_funcs(module):
    """Map engine function name -> set of FACTOR_SET params that carry a default."""
    out = {}
    for name, fn in inspect.getmembers(module, inspect.isfunction):
        if getattr(fn, "__module__", "") != module.__name__:
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        defaulted = {
            p for p, param in sig.parameters.items()
            if p in FACTOR_SET and param.default is not inspect.Parameter.empty
        }
        if defaulted:
            out[name] = defaulted
    return out


TARGETS = _defaulted_factor_funcs(cabinet_math)


def _violations(path, resolve):
    """Calls in `path` to a target engine function that omit a defaulted factor.

    `resolve(call_name)` returns the engine function name the call refers to, or
    None if the call is not a bare-engine call we should police.
    """
    tree = ast.parse(open(path).read())
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        engine_name = resolve(node.func.id)
        if engine_name not in TARGETS:
            continue
        passed = {kw.arg for kw in node.keywords if kw.arg is not None}
        missing = TARGETS[engine_name] - passed
        if missing:
            bad.append((node.lineno, node.func.id, sorted(missing)))
    return bad


def test_targets_are_discovered():
    # Sanity: the introspection found the factor-sensitive functions
    # (otherwise the guard would pass vacuously).
    assert TARGETS, "no defaulted sizing-factor functions discovered in engine.cabinet_math"
    assert "compute_helix_spirals_needed" in TARGETS  # the one that bit us


def test_plan_py_forwards_sizing_factors():
    # engine/plan.py imports engine functions under their real names.
    bad = _violations(PLAN, resolve=lambda n: n)
    assert not bad, (
        "engine/plan.py calls a factor-sensitive engine function without forwarding "
        f"the run-time factor (would silently use the default): {bad}"
    )


def test_page_engine_shims_forward_sizing_factors():
    # The page reaches bare engine functions only via _engine_<name> aliases.
    def resolve(name):
        return name[len("_engine_"):] if name.startswith("_engine_") else None
    bad = _violations(PAGE, resolve=resolve)
    assert not bad, (
        "a page _engine_ shim calls the bare engine function without forwarding the "
        f"run-time factor: {bad}"
    )

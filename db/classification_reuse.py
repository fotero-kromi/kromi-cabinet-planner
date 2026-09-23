"""Reuse stored classifications on a recompute (Phase 3, load with overrides).

When a stored run is recomputed -- to apply an override set, for instance -- the
size and product categories come from the classifications already stored for the
run's file, not from a fresh model call. That keeps a recompute deterministic
and avoids re-spending on the AI provider.

The reuse is keyed by tool code, never by row position, so it stays correct even
when the recompute's row set differs from the original: a row added or removed,
or the same rows in a different order. A code with no stored classification is
reported back to the caller as a miss rather than guessed at.

This module is a pure database read plus a dictionary lookup. It never calls a
model, which is the property that makes a reload cheap and repeatable.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


def _record(r) -> Dict[str, Any]:
    return {
        "size_category": r["size_category"],
        "product_category": r["product_category"],
        "source": r["source"],
        "model": r["model"],
        "reason": r["reason"],
        "confidence": r["confidence"],
    }


def classifications_by_code(
    conn, *, file_id: Optional[int] = None, run_id: Optional[int] = None,
    sources: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return the stored classification per tool code.

    With ``run_id``: the classifications that run used (v34.53, audit C8), so a
    recompute reproduces that run rather than whatever the file saw last. A run
    stored without links (older imports) falls back to its file.

    With ``file_id``: the newest classification per code for the file.
    ``sources`` (case-insensitive) limits the candidates first, so the reuse of
    a known workbook can ask for the newest authoritative answer (AI or manual)
    even when a later run classified the code heuristically.

    Each value is a dict with size_category, product_category, source, model,
    reason, and confidence.
    """
    if file_id is None:
        if run_id is None:
            raise ValueError("classifications_by_code requires file_id or run_id")
        row = conn.execute(
            "SELECT file_id FROM analysis_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return {}
        own = conn.execute(
            "SELECT tr.code AS code, cl.size_category, cl.product_category, cl.source, "
            "cl.model, cl.reason, cl.confidence "
            "FROM cabinet_calculations cc "
            "JOIN tool_records tr ON tr.tool_record_id = cc.tool_record_id "
            "JOIN tool_classifications cl ON cl.classification_id = cc.classification_id "
            "WHERE cc.run_id = ? ORDER BY cc.calc_id",
            (run_id,),
        ).fetchall()
        if own:
            out_run: Dict[str, Dict[str, Any]] = {}
            for r in own:
                out_run.setdefault(r["code"], _record(r))
            return out_run
        file_id = row["file_id"]

    rows = conn.execute(
        "SELECT tr.code AS code, cl.size_category, cl.product_category, cl.source, "
        "cl.model, cl.reason, cl.confidence "
        "FROM tool_classifications cl "
        "JOIN tool_records tr ON tr.tool_record_id = cl.tool_record_id "
        "WHERE cl.file_id = ? ORDER BY cl.classification_id",
        (file_id,),
    ).fetchall()
    wanted = ({str(s).strip().lower() for s in sources} if sources is not None else None)

    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        if wanted is not None and str(r["source"] or "").strip().lower() not in wanted:
            continue
        # ORDER BY classification_id ascending, so the last write for a code
        # (the newest) overwrites earlier ones.
        out[r["code"]] = _record(r)
    return out

# The pure applier moved into the engine (the planning pipeline applies it as one
# of its stages); re-exported here unchanged so the db module's public API is
# intact. The database read above stays where the database is.
from engine.classification import apply_stored_classifications  # noqa: E402,F401

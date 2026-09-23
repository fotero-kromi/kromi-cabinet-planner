"""Override sets in the database (Phase 4).

A saved override set is a named, scoped, versioned bundle of technician
corrections: who saved it, for which customer and site, with optional notes, and
the per-tool field changes. It is the database-backed counterpart of the
file-based overrides library, and it is what lets a recompute draw its overrides
from a chosen stored set rather than from a CSV on disk.

Storage is normalized. The override_sets table holds the bundle's metadata; the
overrides table holds one (tool_code, field, value) row per changed field. The
engine's apply_overrides expects a wide frame (one row per code, the override
fields as columns), so this module decomposes a wide set on save and
reconstructs the wide frame on read. Reconstruction yields exactly the column
contract in OVERRIDE_COLUMNS, so a stored set applies through the same engine
path the file library uses.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def format_override_set_label(set_row: Dict[str, Any]) -> str:
    """One consistent picker label for an override set, used everywhere a set is
    listed so the formatting cannot drift between the recompute picker and the
    save dialog. Shape: ``#<id> · <YYYY-MM-DD HH:MM> · <n> tool(s)[ · <reviewer>]``.
    A missing ``created_at`` leaves the date segment blank rather than rendering
    the literal "None".
    """
    created = str(set_row.get("created_at") or "")[:16].replace("T", " ")
    count = set_row.get("override_count", 0)
    label = f"#{set_row.get('set_id')} · {created} · {count} tool(s)"
    reviewer = set_row.get("reviewer_name")
    if reviewer:
        label += f" · {reviewer}"
    return label


def _insert(conn: sqlite3.Connection, table: str, row: Dict[str, Any]) -> int:
    """Insert without committing (the caller's transaction owns the commit)."""
    cols = list(row.keys())
    placeholders = ", ".join("?" for _ in cols)
    cur = conn.execute(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})",
        [row[c] for c in cols],
    )
    rid = cur.lastrowid
    assert rid is not None  # the INSERT above always sets it
    return int(rid)


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    return s == "" or s.lower() == "nan"


def save_override_set(
    conn: sqlite3.Connection,
    *,
    customer: Optional[str],
    site: Optional[str],
    reviewer_name: Optional[str] = None,
    notes: Optional[str] = None,
    overrides_df=None,
) -> int:
    """Save a wide override frame as a new set and return its id.

    ``overrides_df`` is a frame in the OVERRIDE_COLUMNS shape (the same one the
    file library and the override editor use). Each non-blank override field
    becomes a normalized row. The whole save is one transaction.
    """
    from engine.constants import OVERRIDE_COLUMNS

    field_cols = [c for c in OVERRIDE_COLUMNS if c != "code"]
    now = _utc_now()
    with conn:  # atomic: the set and all its rows commit together or not at all
        set_id = _insert(conn, "override_sets", {
            "customer": customer,
            "site": site,
            "reviewer_name": reviewer_name,
            "notes": notes,
            "active": 1,
            "created_at": now,
        })
        if overrides_df is not None and len(overrides_df) > 0:
            for rec in overrides_df.to_dict("records"):
                code = str(rec.get("code", "")).strip()
                if not code:
                    continue
                for field in field_cols:
                    value = rec.get(field)
                    if _is_blank(value):
                        continue
                    _insert(conn, "overrides", {
                        "set_id": set_id,
                        "tool_code": code,
                        "field": field,
                        "value": str(value).strip(),
                        "created_at": now,
                    })
    return set_id


def update_override_set(
    conn: sqlite3.Connection,
    set_id: int,
    *,
    customer: Optional[str],
    site: Optional[str],
    reviewer_name: Optional[str] = None,
    notes: Optional[str] = None,
    overrides_df=None,
) -> bool:
    """Replace an existing set's corrections in place instead of creating a new
    one, so re-saving a reviewed scope updates the same set rather than piling
    up duplicate sets.

    Returns True when a set with ``set_id`` existed and was updated, False when
    no such set was found (in which case nothing is created). The set keeps its
    id and its original ``created_at`` so its identity is stable; its metadata
    is refreshed and its override rows are rebuilt from ``overrides_df`` with the
    same normalization ``save_override_set`` uses. The whole update is one
    transaction, so a set is never left with a half-replaced row collection.
    """
    from engine.constants import OVERRIDE_COLUMNS

    field_cols = [c for c in OVERRIDE_COLUMNS if c != "code"]
    now = _utc_now()
    with conn:  # atomic: metadata refresh and row rebuild commit together
        exists = conn.execute(
            "SELECT 1 FROM override_sets WHERE set_id = ?", (set_id,)
        ).fetchone()
        if exists is None:
            return False
        conn.execute(
            "UPDATE override_sets SET customer = ?, site = ?, reviewer_name = ?, "
            "notes = ? WHERE set_id = ?",
            (customer, site, reviewer_name, notes, set_id),
        )
        conn.execute("DELETE FROM overrides WHERE set_id = ?", (set_id,))
        if overrides_df is not None and len(overrides_df) > 0:
            for rec in overrides_df.to_dict("records"):
                code = str(rec.get("code", "")).strip()
                if not code:
                    continue
                for field in field_cols:
                    value = rec.get(field)
                    if _is_blank(value):
                        continue
                    _insert(conn, "overrides", {
                        "set_id": set_id,
                        "tool_code": code,
                        "field": field,
                        "value": str(value).strip(),
                        "created_at": now,
                    })
    return True


def update_override_set_with_edits(
    conn: sqlite3.Connection,
    set_id: int,
    *,
    edits_df,
    customer: Optional[str],
    site: Optional[str],
    reviewer_name: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    """Merge ``edits_df`` onto the chosen set's OWN rows and store the result.

    v34.50 (audit C12): "Update an existing set" used to replace the chosen
    set's rows with the newest set of the page's scope plus the edits, which
    lost the chosen set's corrections whenever it was not that newest set.
    Edits win per (code, field); untouched rows of the set are kept. Returns
    the number of tools in the updated set, or 0 when the set does not exist.
    """
    import pandas as pd
    from engine.constants import OVERRIDE_COLUMNS

    exists = conn.execute(
        "SELECT 1 FROM override_sets WHERE set_id = ?", (set_id,)).fetchone()
    if exists is None:
        return 0
    base = override_set_as_dataframe(conn, set_id)
    edits = edits_df.reindex(columns=OVERRIDE_COLUMNS).fillna("")
    merged = pd.concat([base.reindex(columns=OVERRIDE_COLUMNS).fillna(""), edits],
                       ignore_index=True)
    update_override_set(conn, set_id, customer=customer, site=site,
                        reviewer_name=reviewer_name, notes=notes,
                        overrides_df=merged)
    return int(override_set_as_dataframe(conn, set_id)["code"].nunique())


def override_set_as_dataframe(conn: sqlite3.Connection, set_id: int):
    """Reconstruct a set as a wide frame in the OVERRIDE_COLUMNS shape, ready for
    the engine's apply_overrides. Codes keep the order they were first stored."""
    import pandas as pd
    from engine.constants import OVERRIDE_COLUMNS

    rows = conn.execute(
        "SELECT tool_code, field, value FROM overrides WHERE set_id = ? ORDER BY override_id",
        (set_id,),
    ).fetchall()

    by_code: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for r in rows:
        code = r["tool_code"]
        if code not in by_code:
            by_code[code] = {"code": code}
            order.append(code)
        by_code[code][r["field"]] = r["value"]

    records = [
        {col: by_code[code].get(col, "") for col in OVERRIDE_COLUMNS}
        for code in order
    ]
    return pd.DataFrame(records, columns=OVERRIDE_COLUMNS)


def get_override_set(conn: sqlite3.Connection, set_id: int) -> Optional[Dict[str, Any]]:
    """The set's metadata plus its overrides as a wide frame, or None if absent."""
    s = conn.execute(
        "SELECT * FROM override_sets WHERE set_id = ?", (set_id,)
    ).fetchone()
    if s is None:
        return None
    return {
        "set_id": int(s["set_id"]),
        "customer": s["customer"],
        "site": s["site"],
        "reviewer_name": s["reviewer_name"],
        "notes": s["notes"],
        "active": int(s["active"]),
        "created_at": s["created_at"],
        "overrides": override_set_as_dataframe(conn, set_id),
    }


def list_override_sets(
    conn: sqlite3.Connection,
    *,
    customer: Optional[str] = None,
    site: Optional[str] = None,
    active_only: bool = True,
) -> List[Dict[str, Any]]:
    """Override sets newest first, optionally filtered by exact scope, each with
    the count of distinct tools it touches. ``customer``/``site`` of None apply
    no filter; an empty string matches sets without a customer/site."""
    clauses: List[str] = []
    params: List[Any] = []
    if active_only:
        clauses.append("active = 1")
    # v34.50: exact, case-insensitive scope matching. The earlier LIKE with
    # the typed text wrapped in wildcards listed other customers' sets for a
    # partial or wildcard name. None = no filter; "" = exactly "no customer".
    if customer is not None:
        clauses.append("LOWER(COALESCE(customer, '')) = ?")
        params.append(customer.strip().lower())
    if site is not None:
        clauses.append("LOWER(COALESCE(site, '')) = ?")
        params.append(site.strip().lower())
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM override_sets {where} ORDER BY created_at DESC, set_id DESC",
        params,
    ).fetchall()

    out: List[Dict[str, Any]] = []
    for s in rows:
        count = conn.execute(
            "SELECT COUNT(DISTINCT tool_code) AS n FROM overrides WHERE set_id = ?",
            (s["set_id"],),
        ).fetchone()["n"]
        out.append({
            "set_id": int(s["set_id"]),
            "customer": s["customer"],
            "site": s["site"],
            "reviewer_name": s["reviewer_name"],
            "notes": s["notes"],
            "created_at": s["created_at"],
            "override_count": int(count),
        })
    return out


def latest_override_set(
    conn: sqlite3.Connection,
    *,
    customer: Optional[str],
    site: Optional[str],
    active_only: bool = True,
) -> Optional[int]:
    """The id of the newest set for an exact customer/site scope, or None."""
    clauses = [
        "LOWER(COALESCE(customer, '')) = ?",
        "LOWER(COALESCE(site, '')) = ?",
    ]
    params: List[Any] = [(customer or "").lower(), (site or "").lower()]
    if active_only:
        clauses.append("active = 1")
    row = conn.execute(
        f"SELECT set_id FROM override_sets WHERE {' AND '.join(clauses)} "
        "ORDER BY created_at DESC, set_id DESC LIMIT 1",
        params,
    ).fetchone()
    return int(row["set_id"]) if row else None


def deactivate_override_set(conn: sqlite3.Connection, set_id: int) -> None:
    """Mark a set inactive so a newer one supersedes it. The rows are kept for
    history."""
    conn.execute("UPDATE override_sets SET active = 0 WHERE set_id = ?", (set_id,))
    conn.commit()


def delete_override_set(conn: sqlite3.Connection, set_id: int) -> bool:
    """Hard-delete a whole override set and every override row it holds.

    Unlike ``deactivate_override_set`` (which only flips the active flag and
    keeps the rows for history), this removes the set permanently. Returns True
    if a set with this id existed and was removed, False if no such set was
    found. The delete is one transaction; the override rows are removed
    explicitly as well as by the ON DELETE CASCADE foreign key, so the set
    leaves no orphaned rows even on a connection where cascade is not enforced.

    Runs that applied the set keep their result and their settings record of
    the set id; only their link is cleared (v34.54: runs now record the set
    they applied, and the link must not block the delete).
    """
    with conn:  # atomic: rows and the set go together or not at all
        conn.execute(
            "UPDATE analysis_runs SET applied_override_set_id = NULL "
            "WHERE applied_override_set_id = ?", (set_id,))
        conn.execute("DELETE FROM overrides WHERE set_id = ?", (set_id,))
        cur = conn.execute("DELETE FROM override_sets WHERE set_id = ?", (set_id,))
    return cur.rowcount > 0


def delete_override_set_row(
    conn: sqlite3.Connection, set_id: int, tool_code: str
) -> int:
    """Delete one tool's override from a set: every stored field row for that
    ``tool_code`` within the set (a single tool can hold several field rows).

    Returns the number of field rows removed, or 0 if the tool was not present
    in the set. The set itself is left in place, even if this removes its last
    row, so an empty set survives until it is deleted on its own.
    """
    code = str(tool_code).strip()
    with conn:
        cur = conn.execute(
            "DELETE FROM overrides WHERE set_id = ? AND tool_code = ?",
            (set_id, code),
        )
    return int(cur.rowcount)

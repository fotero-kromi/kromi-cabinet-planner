"""Database package for the Kromi Cabinet Planner (Phase 0 foundation).

Public entry points are re-exported from ``db.store``. Nothing in the running
application imports this package yet; it is the persistence foundation that
later phases build on.
"""

from db.store import (
    connect,
    migrate,
    current_schema_version,
    init_db,
    default_db_path,
    insert_row,
    insert_rows,
    seed_default_machine_config,
    get_active_machine_config,
    upsert_file,
    get_file,
    get_file_by_hash,
    insert_run,
    get_run,
    search_runs,
)
from db.persist_run import (
    persist_run,
    run_id_by_inputs_hash,
    tools_from_dataframe,
    summary_rows_from_plans,
    rebalance_events_from_audit,
)
from db.load_run import (
    load_run_snapshot,
    list_runs_for_picker,
    reconstruct_work,
    reconstruct_plans,
)
from db.classification_reuse import (
    classifications_by_code,
    apply_stored_classifications,
)
from db.override_sets import (
    save_override_set,
    update_override_set,
    update_override_set_with_edits,
    format_override_set_label,
    get_override_set,
    override_set_as_dataframe,
    list_override_sets,
    latest_override_set,
    deactivate_override_set,
    delete_override_set,
    delete_override_set_row,
)

__all__ = [
    "connect",
    "migrate",
    "current_schema_version",
    "init_db",
    "default_db_path",
    "insert_row",
    "insert_rows",
    "seed_default_machine_config",
    "get_active_machine_config",
    "upsert_file",
    "get_file",
    "get_file_by_hash",
    "insert_run",
    "get_run",
    "search_runs",
    "persist_run",
    "run_id_by_inputs_hash",
    "tools_from_dataframe",
    "summary_rows_from_plans",
    "rebalance_events_from_audit",
    "load_run_snapshot",
    "list_runs_for_picker",
    "reconstruct_work",
    "reconstruct_plans",
    "classifications_by_code",
    "apply_stored_classifications",
    "save_override_set",
    "update_override_set",
    "update_override_set_with_edits",
    "format_override_set_label",
    "get_override_set",
    "override_set_as_dataframe",
    "list_override_sets",
    "latest_override_set",
    "deactivate_override_set",
    "delete_override_set",
    "delete_override_set_row",
]

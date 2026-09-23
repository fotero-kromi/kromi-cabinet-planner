-- 001_initial_schema.sql
-- Initial relational schema for the Kromi Cabinet Planner persistence layer.
--
-- Design notes:
--   * Surrogate INTEGER primary keys throughout (SQLite rowid aliases). When this
--     schema is ported to PostgreSQL the only dialect change is the key
--     declaration (GENERATED ALWAYS AS IDENTITY); the structure is unchanged.
--   * Timestamps are TEXT in ISO-8601 UTC, written by the application layer.
--   * JSON payloads are stored as TEXT (a JSON string); they map to JSONB later.
--   * Booleans are INTEGER (0/1).
--   * File content is BLOB (maps to BYTEA).
--   * Foreign keys are declared; the connection enables enforcement per session.
--     Snapshot children of a run cascade on delete; inputs that runs depend on
--     (machine configs, override sets, files) restrict deletion to protect the
--     audit trail.

-- ---------------------------------------------------------------------------
-- Inputs
-- ---------------------------------------------------------------------------

CREATE TABLE uploaded_files (
    file_id             INTEGER PRIMARY KEY,
    sha256              TEXT NOT NULL UNIQUE,
    original_filename   TEXT,
    byte_size           INTEGER,
    content             BLOB,
    sheet_tools         TEXT,
    sheet_ppe           TEXT,
    row_count           INTEGER,
    first_seen_customer TEXT,
    first_seen_ktc_id   TEXT,
    uploaded_at         TEXT NOT NULL
);

CREATE TABLE machine_configurations (
    config_id              INTEGER PRIMARY KEY,
    name                   TEXT NOT NULL,
    helix_spirals_per_cab  INTEGER NOT NULL,
    carousel_slots_per_cab INTEGER NOT NULL,
    locker_a_capacity      INTEGER NOT NULL,
    locker_b_capacity      INTEGER NOT NULL,
    locker_c_capacity      INTEGER NOT NULL,
    carousel_reserve_factor REAL NOT NULL,
    helix_overfill_factor  REAL NOT NULL,
    days_per_month         REAL NOT NULL,
    active                 INTEGER NOT NULL DEFAULT 1,
    created_at             TEXT NOT NULL
);

CREATE TABLE tool_records (
    tool_record_id  INTEGER PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES uploaded_files(file_id) ON DELETE CASCADE,
    line_no         INTEGER,
    code            TEXT,
    description     TEXT,
    description_2   TEXT,
    supplier_code   TEXT,
    listing         TEXT,
    raw_consumption REAL,
    pack_units      REAL,
    period_months   REAL,
    source_size     TEXT,
    system_typ      TEXT,
    extra_json      TEXT
);

-- ---------------------------------------------------------------------------
-- Classification (kept separate from deterministic calculation; reused across
-- runs of the same file so reload never re-calls the AI provider)
-- ---------------------------------------------------------------------------

CREATE TABLE tool_classifications (
    classification_id INTEGER PRIMARY KEY,
    file_id           INTEGER NOT NULL REFERENCES uploaded_files(file_id) ON DELETE CASCADE,
    tool_record_id    INTEGER NOT NULL REFERENCES tool_records(tool_record_id) ON DELETE CASCADE,
    size_category     TEXT,
    product_category  TEXT,
    source            TEXT,
    model             TEXT,
    prompt_version    TEXT,
    reason            TEXT,
    confidence        REAL,
    classified_at     TEXT NOT NULL,
    superseded_by     INTEGER REFERENCES tool_classifications(classification_id) ON DELETE SET NULL
);

-- ---------------------------------------------------------------------------
-- Override library (versioned: a set is created each time the user saves)
-- ---------------------------------------------------------------------------

CREATE TABLE override_sets (
    set_id        INTEGER PRIMARY KEY,
    customer      TEXT,
    site          TEXT,
    reviewer_name TEXT,
    notes         TEXT,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE overrides (
    override_id INTEGER PRIMARY KEY,
    set_id      INTEGER NOT NULL REFERENCES override_sets(set_id) ON DELETE CASCADE,
    tool_code   TEXT NOT NULL,
    field       TEXT NOT NULL,
    value       TEXT,
    created_at  TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- The hub
-- ---------------------------------------------------------------------------

CREATE TABLE analysis_runs (
    run_id                  INTEGER PRIMARY KEY,
    file_id                 INTEGER NOT NULL REFERENCES uploaded_files(file_id) ON DELETE RESTRICT,
    machine_config_id       INTEGER REFERENCES machine_configurations(config_id) ON DELETE RESTRICT,
    build_version           TEXT,
    customer                TEXT,
    site                    TEXT,
    ktc_id                  TEXT,
    calc_mode               TEXT,
    operational_mode        TEXT,
    max_carousels           INTEGER,
    supply_points           INTEGER,
    sp_mode                 TEXT,
    settings_json           TEXT,
    applied_override_set_id INTEGER REFERENCES override_sets(set_id) ON DELETE RESTRICT,
    status                  TEXT,
    notes                   TEXT,
    created_at              TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Deterministic outputs (the snapshot a reload restores)
-- ---------------------------------------------------------------------------

CREATE TABLE cabinet_calculations (
    calc_id              INTEGER PRIMARY KEY,
    run_id               INTEGER NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    tool_record_id       INTEGER NOT NULL REFERENCES tool_records(tool_record_id) ON DELETE CASCADE,
    classification_id    INTEGER REFERENCES tool_classifications(classification_id) ON DELETE SET NULL,
    system_category      TEXT,
    cabinet_type         TEXT,
    spirals_needed       INTEGER,
    carousel_stockpiles  INTEGER,
    spiral_capacity      INTEGER,
    monthly_packs        REAL,
    target_packs         REAL,
    consumption_pcs      REAL,
    supply_point         INTEGER,
    bucket_label         TEXT,
    size_issue           INTEGER NOT NULL DEFAULT 0,
    size_issue_reason    TEXT,
    override_applied     INTEGER NOT NULL DEFAULT 0,
    override_fields_json TEXT
);

CREATE TABLE cabinet_plan_summary (
    summary_id     INTEGER PRIMARY KEY,
    run_id         INTEGER NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    bucket_label   TEXT,
    helix_cabs     INTEGER,
    carousel_cabs  INTEGER,
    locker_a       INTEGER,
    locker_b       INTEGER,
    locker_c       INTEGER,
    total_cabs     INTEGER,
    total_spirals  INTEGER,
    carousel_slots INTEGER,
    ktc_count      INTEGER,
    kanban_count   INTEGER
);

CREATE TABLE rebalance_events (
    event_id        INTEGER PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    bucket_label    TEXT,
    cabinets_before INTEGER,
    cabinets_after  INTEGER,
    item_code       TEXT,
    from_cabinet    TEXT,
    to_cabinet      TEXT
);

CREATE TABLE engine_executions (
    execution_id     INTEGER PRIMARY KEY,
    run_id           INTEGER NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    build_version    TEXT,
    executed_at      TEXT NOT NULL,
    duration_ms      INTEGER,
    rows_processed   INTEGER,
    rebalance_moves  INTEGER,
    cabinets_saved   INTEGER,
    size_issues_found INTEGER,
    grand_total_cabs INTEGER,
    inputs_hash      TEXT
);

CREATE TABLE validation_results (
    validation_id  INTEGER PRIMARY KEY,
    run_id         INTEGER NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    tool_record_id INTEGER REFERENCES tool_records(tool_record_id) ON DELETE CASCADE,
    issue_type     TEXT,
    severity       TEXT,
    detail         TEXT,
    resolved       INTEGER NOT NULL DEFAULT 0,
    resolved_by    TEXT,
    resolved_at    TEXT
);

-- ---------------------------------------------------------------------------
-- Learning
-- ---------------------------------------------------------------------------

CREATE TABLE ai_training_feedback (
    feedback_id       INTEGER PRIMARY KEY,
    classification_id INTEGER REFERENCES tool_classifications(classification_id) ON DELETE SET NULL,
    tool_record_id    INTEGER REFERENCES tool_records(tool_record_id) ON DELETE SET NULL,
    run_id            INTEGER REFERENCES analysis_runs(run_id) ON DELETE SET NULL,
    field             TEXT,
    original_value    TEXT,
    corrected_value   TEXT,
    reviewer          TEXT,
    created_at        TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Indexes for the search and join paths the application uses
-- ---------------------------------------------------------------------------

CREATE INDEX idx_runs_customer        ON analysis_runs(customer);
CREATE INDEX idx_runs_site            ON analysis_runs(site);
CREATE INDEX idx_runs_created_at      ON analysis_runs(created_at);
CREATE INDEX idx_runs_file            ON analysis_runs(file_id);
CREATE INDEX idx_tool_records_file    ON tool_records(file_id);
CREATE INDEX idx_classifications_file ON tool_classifications(file_id);
CREATE INDEX idx_classifications_tool ON tool_classifications(tool_record_id);
CREATE INDEX idx_calculations_run     ON cabinet_calculations(run_id);
CREATE INDEX idx_calculations_tool    ON cabinet_calculations(tool_record_id);
CREATE INDEX idx_plan_summary_run     ON cabinet_plan_summary(run_id);
CREATE INDEX idx_rebalance_run        ON rebalance_events(run_id);
CREATE INDEX idx_executions_run       ON engine_executions(run_id);
CREATE INDEX idx_validation_run       ON validation_results(run_id);
CREATE INDEX idx_overrides_set        ON overrides(set_id);
CREATE INDEX idx_override_sets_scope  ON override_sets(customer, site);
CREATE INDEX idx_feedback_class       ON ai_training_feedback(classification_id);

"""The first schema: workbooks, runs and their results.

Revision ID: 0001
Revises:
Create Date: 2026-09-23
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workbooks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workbook_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("settings_version", sa.Integer(), nullable=False),
        sa.Column("inputs_hash", sa.String(length=64), nullable=False),
        sa.Column("engine_build", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')",
                           name="ck_runs_status"),
        sa.ForeignKeyConstraint(["workbook_id"], ["workbooks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_workbook_id", "runs", ["workbook_id"])
    op.create_index("ix_runs_inputs_hash", "runs", ["inputs_hash"])
    op.create_table(
        "run_summaries",
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("customer", sa.Text(), nullable=False),
        sa.Column("site", sa.Text(), nullable=False),
        sa.Column("grand", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("base_info", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("restock_info", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("vend_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("override_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation_issues", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("split_coverage", sa.Boolean(), nullable=False),
        sa.Column("listings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rebalance_audit", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("sp_conservation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tool_columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("export_problems", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("export_notes", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "run_buckets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("ktc_count", sa.Integer(), nullable=False),
        sa.Column("kanban_count", sa.Integer(), nullable=False),
        sa.Column("helix_cabinets", sa.Integer(), nullable=False),
        sa.Column("carousel_cabinets", sa.Integer(), nullable=False),
        sa.Column("locker_a_cabinets", sa.Integer(), nullable=False),
        sa.Column("locker_b_cabinets", sa.Integer(), nullable=False),
        sa.Column("locker_c_cabinets", sa.Integer(), nullable=False),
        sa.Column("total_cabinets", sa.Integer(), nullable=False),
        sa.Column("plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "position", name="uq_run_buckets_position"),
    )
    op.create_index("ix_run_buckets_run_id", "run_buckets", ["run_id"])
    op.create_table(
        "run_tools",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("listing", sa.Text(), nullable=True),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("size", sa.Text(), nullable=True),
        sa.Column("pack_units", sa.Float(), nullable=True),
        sa.Column("system_category", sa.Text(), nullable=True),
        sa.Column("cabinet_type", sa.Text(), nullable=True),
        sa.Column("supply_point", sa.Integer(), nullable=True),
        sa.Column("monthly_pcs", sa.Float(), nullable=True),
        sa.Column("monthly_packs", sa.Float(), nullable=True),
        sa.Column("spirals", sa.Integer(), nullable=True),
        sa.Column("compartments", sa.Integer(), nullable=True),
        sa.Column("row", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "line_no", name="uq_run_tools_line"),
    )
    op.create_index("ix_run_tools_run_id", "run_tools", ["run_id"])
    op.create_table(
        "run_files",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
                  nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "kind", name="uq_run_files_kind"),
    )
    op.create_index("ix_run_files_run_id", "run_files", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_run_files_run_id", table_name="run_files")
    op.drop_table("run_files")
    op.drop_index("ix_run_tools_run_id", table_name="run_tools")
    op.drop_table("run_tools")
    op.drop_index("ix_run_buckets_run_id", table_name="run_buckets")
    op.drop_table("run_buckets")
    op.drop_table("run_summaries")
    op.drop_index("ix_runs_inputs_hash", table_name="runs")
    op.drop_index("ix_runs_workbook_id", table_name="runs")
    op.drop_table("runs")
    op.drop_table("workbooks")

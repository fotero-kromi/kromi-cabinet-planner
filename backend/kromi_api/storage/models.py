"""The database tables (schema changes go through Alembic migrations).

* ``workbooks``: each uploaded file once (by content hash), with its bytes.
* ``runs``: one planning run of a workbook with its settings and status.
* ``run_summaries``: the planner's totals and reports for a run.
* ``run_buckets``: one row per bucket ("All", "SP 1", ...).
* ``run_tools``: one row per article: typed columns for the results table
  plus the complete planner row, so nothing is lost.
* ``run_files``: the generated result workbook, so a download is always
  exactly the checked file.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

RUN_STATUSES = ("queued", "running", "succeeded", "failed")


class Base(DeclarativeBase):
    pass


class Workbook(Base):
    __tablename__ = "workbooks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                  server_default=func.now())


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')",
                        name="ck_runs_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workbook_id: Mapped[int] = mapped_column(ForeignKey("workbooks.id", ondelete="RESTRICT"),
                                             index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB)
    settings_version: Mapped[int] = mapped_column(Integer)
    inputs_hash: Mapped[str] = mapped_column(String(64), index=True)
    engine_build: Mapped[str] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_details: Mapped[Any | None] = mapped_column(JSONB)
    notes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    workbook: Mapped[Workbook] = relationship()
    summary: Mapped[RunSummary | None] = relationship(back_populates="run",
                                                      cascade="all, delete-orphan")


class RunSummary(Base):
    __tablename__ = "run_summaries"

    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"),
                                        primary_key=True)
    customer: Mapped[str] = mapped_column(Text)
    site: Mapped[str] = mapped_column(Text)
    grand: Mapped[dict[str, Any]] = mapped_column(JSONB)
    base_info: Mapped[dict[str, Any]] = mapped_column(JSONB)
    restock_info: Mapped[dict[str, Any]] = mapped_column(JSONB)
    vend_stats: Mapped[dict[str, Any]] = mapped_column(JSONB)
    override_stats: Mapped[dict[str, Any]] = mapped_column(JSONB)
    validation_issues: Mapped[list[str]] = mapped_column(JSONB)
    split_coverage: Mapped[bool] = mapped_column(Boolean)
    listings: Mapped[list[str]] = mapped_column(JSONB)
    rebalance_audit: Mapped[list[Any]] = mapped_column(JSONB)
    sp_conservation: Mapped[list[Any]] = mapped_column(JSONB)
    #: The planner row layout: [[column, dtype], ...] in frame order.
    tool_columns: Mapped[list[list[str]]] = mapped_column(JSONB)
    export_problems: Mapped[list[str]] = mapped_column(JSONB, default=list)
    export_notes: Mapped[str] = mapped_column(Text, default="")

    run: Mapped[Run] = relationship(back_populates="summary")


class RunBucket(Base):
    __tablename__ = "run_buckets"
    __table_args__ = (UniqueConstraint("run_id", "position", name="uq_run_buckets_position"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(Text)
    ktc_count: Mapped[int] = mapped_column(Integer)
    kanban_count: Mapped[int] = mapped_column(Integer)
    helix_cabinets: Mapped[int] = mapped_column(Integer)
    carousel_cabinets: Mapped[int] = mapped_column(Integer)
    locker_a_cabinets: Mapped[int] = mapped_column(Integer)
    locker_b_cabinets: Mapped[int] = mapped_column(Integer)
    locker_c_cabinets: Mapped[int] = mapped_column(Integer)
    total_cabinets: Mapped[int] = mapped_column(Integer)
    plan: Mapped[dict[str, Any]] = mapped_column(JSONB)


class RunTool(Base):
    __tablename__ = "run_tools"
    __table_args__ = (UniqueConstraint("run_id", "line_no", name="uq_run_tools_line"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    listing: Mapped[str | None] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    size: Mapped[str | None] = mapped_column(Text)
    pack_units: Mapped[float | None] = mapped_column(Float)
    system_category: Mapped[str | None] = mapped_column(Text)
    cabinet_type: Mapped[str | None] = mapped_column(Text)
    supply_point: Mapped[int | None] = mapped_column(Integer)
    monthly_pcs: Mapped[float | None] = mapped_column(Float)
    monthly_packs: Mapped[float | None] = mapped_column(Float)
    spirals: Mapped[int | None] = mapped_column(Integer)
    compartments: Mapped[int | None] = mapped_column(Integer)
    #: The complete planner row (every column, JSON values).
    row: Mapped[dict[str, Any]] = mapped_column(JSONB)


class RunFile(Base):
    __tablename__ = "run_files"
    __table_args__ = (UniqueConstraint("run_id", "kind", name="uq_run_files_kind"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 server_default=func.now())

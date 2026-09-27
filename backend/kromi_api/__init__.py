"""Kromi Cabinet Planner, new app: FastAPI back end around the shared engine.

Layers (docs/Rewrite_Decision.md):
* ``settings``: the typed request settings, mapped field by field onto
  ``engine.run_settings.RunSettings`` and ``engine.tool_list.ColumnMapping``;
* ``services``: reading a workbook, one planning run, the result workbook;
  they call the engine and nothing else (no web, no database);
* ``storage``: PostgreSQL through SQLAlchemy, migrations by Alembic;
* ``api``: the HTTP endpoints.
"""

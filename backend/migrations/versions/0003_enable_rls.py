"""enable row level security on public tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16

Supabase exposes every table in the public schema through its Data API,
reachable with the anon key the frontend ships. The backend enforces
ownership itself, but that API bypasses the backend entirely — with RLS off,
anyone holding the anon key could read or modify every user's rows.

RLS on with no policies denies all Data API access. The backend is
unaffected: it connects as the tables' owner, and owners are exempt from RLS
unless FORCE ROW LEVEL SECURITY is set (deliberately not set here).

alembic_version is included because it sits in the same schema — writable
by anon, a deleted or altered row would break future migrations.

Any future table needs RLS enabled in its own migration.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLES = ("jobs", "compares", "silt_jobs", "alembic_version")


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

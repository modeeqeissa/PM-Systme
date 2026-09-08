"""persons + case_persons; arrests.suspect_id and statements.person_id become real FKs

docs §9.3.2 (revised): `arrests.suspect_id` was a bare, unvalidated UUID with no
person record behind it. This migration introduces the `persons` master record
and the `case_persons` link table, and turns `suspect_id` into a genuine
`FK → persons.id`. `statements` gains a nullable `person_id` FK alongside the
existing `party_type`, so a statement can point at an identified person while
still supporting anonymous/unidentified sources.

Existing data: dev `case_db` already holds arrests whose `suspect_id` values
have no person behind them. Rather than lose that data (pre-production, but the
arrest rows are real test fixtures other things key on), this migration
**creates a placeholder `persons` row for every orphaned `suspect_id`** — name
"Unknown / (unmigrated suspect)", a `notes` string recording the provenance —
so the new FK holds, and backfills a `('suspect')` `case_persons` link for each
such arrest. Placeholders carry no `national_id`, so they never collide on the
practical dedup key and can be merged/edited later through the normal person
CRUD.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "persons",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("date_of_birth", sa.Date),
        sa.Column("national_id", sa.String(50)),
        sa.Column("gender", sa.String(20)),
        sa.Column("address", sa.Text),
        sa.Column("phone", sa.String(30)),
        sa.Column("notes", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # docs DDL: `national_id VARCHAR(50) UNIQUE` — a plain UNIQUE lets many NULLs
    # coexist, which is exactly "UNIQUE where present".
    op.create_unique_constraint("uq_persons_national_id", "persons", ["national_id"])
    op.create_index("idx_persons_national_id", "persons", ["national_id"])
    # search-by-name (GET /persons?q=) does case-insensitive prefix/substring
    # matching on the two name columns.
    op.create_index(
        "idx_persons_last_name_lower", "persons", [sa.text("lower(last_name)")]
    )
    op.create_index(
        "idx_persons_first_name_lower", "persons", [sa.text("lower(first_name)")]
    )

    op.create_table(
        "case_persons",
        sa.Column(
            "id", pg.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "case_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column(
            "person_id", pg.UUID(as_uuid=True),
            sa.ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
    )
    op.create_check_constraint(
        "ck_case_persons_role", "case_persons", "role IN ('suspect','victim','witness')"
    )
    # the same person may hold different roles across cases, and even two roles
    # in one case (suspect who later turns witness) — but not the same role twice.
    op.create_unique_constraint(
        "uq_case_persons_case_person_role", "case_persons", ["case_id", "person_id", "role"]
    )
    op.create_index("idx_case_persons_case", "case_persons", ["case_id"])
    op.create_index("idx_case_persons_person", "case_persons", ["person_id"])

    # --- backfill placeholder persons for orphaned arrest suspect_ids ---------
    op.execute(
        """
        INSERT INTO persons (id, first_name, last_name, notes)
        SELECT DISTINCT a.suspect_id, 'Unknown', '(unmigrated suspect)',
               'Placeholder created by migration 0004 from arrests.suspect_id '
               || a.suspect_id || ' — predated the persons table. Edit or merge '
               || 'once the real identity is known.'
        FROM arrests a
        LEFT JOIN persons p ON p.id = a.suspect_id
        WHERE p.id IS NULL
        """
    )

    # --- suspect_id is now a real FK ----------------------------------------
    op.create_foreign_key(
        "fk_arrests_suspect", "arrests", "persons", ["suspect_id"], ["id"]
    )
    op.create_index("idx_arrests_suspect", "arrests", ["suspect_id"])

    # --- statements.person_id (nullable FK) -------------------------------
    op.add_column(
        "statements",
        sa.Column("person_id", pg.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_statements_person", "statements", "persons", ["person_id"], ["id"]
    )
    op.create_index("idx_statements_person", "statements", ["person_id"])

    # --- link each migrated arrest's person to its case as a suspect --------
    op.execute(
        """
        INSERT INTO case_persons (case_id, person_id, role)
        SELECT DISTINCT a.case_id, a.suspect_id, 'suspect'
        FROM arrests a
        ON CONFLICT ON CONSTRAINT uq_case_persons_case_person_role DO NOTHING
        """
    )


def downgrade():
    op.drop_index("idx_statements_person", "statements")
    op.drop_constraint("fk_statements_person", "statements", type_="foreignkey")
    op.drop_column("statements", "person_id")

    op.drop_index("idx_arrests_suspect", "arrests")
    op.drop_constraint("fk_arrests_suspect", "arrests", type_="foreignkey")

    op.drop_table("case_persons")
    op.drop_index("idx_persons_first_name_lower", "persons")
    op.drop_index("idx_persons_last_name_lower", "persons")
    op.drop_index("idx_persons_national_id", "persons")
    op.drop_table("persons")

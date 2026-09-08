"""FR-IAM-07: password history + expiry columns.

The current policy check (app.security.passwords) handles length + complexity
but its own docstring flags that history and expiry "need columns identity_db
does not define yet (Section 9.3.1)". This adds them:

- users.password_changed_at  — when the current password was set; expiry
  ("older than IAM_PASSWORD_MAX_AGE_DAYS") is measured from here. Backfilled to
  users.created_at so existing accounts get a sane age.
- password_history            — the last N argon2 hashes per user, so a reset
  can reject reuse (IAM_PASSWORD_HISTORY_COUNT).

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE users SET password_changed_at = created_at")
    op.alter_column(
        "users",
        "password_changed_at",
        nullable=False,
        server_default=sa.text("now()"),
    )

    op.create_table(
        "password_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_password_history_user_changed",
        "password_history",
        ["user_id", "changed_at"],
    )


def downgrade():
    op.drop_index("ix_password_history_user_changed", table_name="password_history")
    op.drop_table("password_history")
    op.drop_column("users", "password_changed_at")

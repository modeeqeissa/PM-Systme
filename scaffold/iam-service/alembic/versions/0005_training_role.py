"""Training domain RBAC (FR-TRAIN-01..03 / docs Section 2.3)

training.cert.read/write have existed as permission codes since 0002, but no
role has ever held them — same gap pattern as hr.discipline.*/hr.transfer.
approve before migration 0004. Adds "Training Officer": docs Section 2.3 —
"Manages course catalog, schedules training, issues/renews certifications |
Full CRUD on Training domain".

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TRAINING_OFFICER_PERMISSIONS = ["training.cert.read", "training.cert.write"]
TRAINING_OFFICER_DESCRIPTION = (
    "Training admin: full CRUD on the Training domain (docs Section 2.3)"
)


def upgrade():
    conn = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table("permissions", meta, autoload_with=conn)
    roles = sa.Table("roles", meta, autoload_with=conn)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=conn)

    perm_id = {
        row.code: row.id
        for row in conn.execute(
            sa.select(permissions.c.id, permissions.c.code).where(
                permissions.c.code.in_(TRAINING_OFFICER_PERMISSIONS)
            )
        )
    }

    training_officer_id = conn.execute(
        roles.insert()
        .values(name="Training Officer", description=TRAINING_OFFICER_DESCRIPTION)
        .returning(roles.c.id)
    ).scalar_one()
    conn.execute(
        role_permissions.insert(),
        [
            {"role_id": training_officer_id, "permission_id": perm_id[c]}
            for c in TRAINING_OFFICER_PERMISSIONS
        ],
    )


def downgrade():
    conn = op.get_bind()
    meta = sa.MetaData()
    roles = sa.Table("roles", meta, autoload_with=conn)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=conn)

    training_officer_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == "Training Officer")
    ).scalar_one()
    conn.execute(
        role_permissions.delete().where(role_permissions.c.role_id == training_officer_id)
    )
    conn.execute(roles.delete().where(roles.c.id == training_officer_id))

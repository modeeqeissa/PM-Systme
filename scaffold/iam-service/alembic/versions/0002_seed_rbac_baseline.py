"""seed baseline permission codes and roles (FR-IAM-03)

roles/permissions are internal lookup data (SRS 8.1); seeding a baseline here
keeps the permission codes other services check (e.g. case.write) authoritative
from day one. New roles still default to zero permissions (NFR-SEC-03).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

PERMISSIONS = [
    "iam.user.read",
    "iam.user.write",
    "iam.role.read",
    "iam.role.write",
    "case.read",
    "case.write",
    "case.approve",
    "case.export",
    "evidence.vault.read",
    "evidence.vault.write",
    "evidence.custody.write",
    "hr.discipline.read",
    "hr.discipline.write",
    "hr.transfer.approve",
    "training.cert.read",
    "training.cert.write",
    "dashboard.view",
    "dashboard.export",
    "audit.read",
]

ROLES = {
    "ICT Admin": (
        "Platform administration: user and role management",
        ["iam.user.read", "iam.user.write", "iam.role.read", "iam.role.write", "audit.read"],
    ),
    "Patrol Officer": (
        "Field officer: file incidents, read evidence",
        ["case.read", "case.write", "evidence.vault.read"],
    ),
    "Investigator": (
        "Case investigator: full case work + evidence handling",
        [
            "case.read",
            "case.write",
            "case.export",
            "evidence.vault.read",
            "evidence.vault.write",
            "evidence.custody.write",
        ],
    ),
    "Station Commander": (
        "Station command: approvals, exports, station dashboard",
        ["case.read", "case.approve", "case.export", "dashboard.view", "hr.transfer.approve"],
    ),
    "Evidence Custodian": (
        "Evidence vault custody",
        ["evidence.vault.read", "evidence.vault.write", "evidence.custody.write"],
    ),
    "Auditor": (
        "Oversight: read audit log and dashboards",
        ["audit.read", "dashboard.view"],
    ),
}


def upgrade():
    conn = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table("permissions", meta, autoload_with=conn)
    roles = sa.Table("roles", meta, autoload_with=conn)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=conn)

    conn.execute(permissions.insert(), [{"code": c} for c in PERMISSIONS])
    perm_id = {
        row.code: row.id
        for row in conn.execute(sa.select(permissions.c.id, permissions.c.code))
    }

    for name, (description, codes) in ROLES.items():
        role_id = conn.execute(
            roles.insert().values(name=name, description=description).returning(roles.c.id)
        ).scalar_one()
        conn.execute(
            role_permissions.insert(),
            [{"role_id": role_id, "permission_id": perm_id[c]} for c in codes],
        )


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM role_permissions"))
    conn.execute(
        sa.text("DELETE FROM roles WHERE name = ANY(:names)"),
        {"names": list(ROLES.keys())},
    )
    conn.execute(
        sa.text("DELETE FROM permissions WHERE code = ANY(:codes)"),
        {"codes": PERMISSIONS},
    )

"""HR domain RBAC (FR-HR-01..08 / docs Section 2.3)

hr-service's Phase 1 seed (0002) already carried hr.discipline.read/write and
hr.transfer.approve, but no role granted them and the HR domain had no
read/write codes for officers, units, assignments, promotions, leave, or
performance reviews at all. Building hr-service for real needs both:

* the missing permission codes, one read/write pair per HR resource
  (hr.transfer.approve and hr.discipline.* already existed and are untouched);
* a role that actually holds them, so RBAC is enforceable rather than
  aspirational — "HR Officer / Admin: Full CRUD on HR domain" per docs
  Section 2.3. ("read-only elsewhere" from that row is NOT modeled here —
  granting read across every other domain is out of scope for this pass.)

Also extends "Station Commander" with hr.transfer.read / hr.leave.read /
hr.leave.approve — Section 2.3 says that role "approves transfers/leave at
station level"; the seed had only granted hr.transfer.approve, missing both
leave approval and the read access needed to review a request before
deciding on it.

discipline_records stays HR-Officer-only (hr.discipline.read/write): Section
2.3 calls it "HR/command" access, but no Commissioner/Command Staff role is
seeded yet (out of scope here) — flagged, not invented.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

NEW_PERMISSIONS = [
    "hr.officer.read",
    "hr.officer.write",
    "hr.unit.read",
    "hr.unit.write",
    "hr.assignment.read",
    "hr.assignment.write",
    "hr.transfer.read",
    "hr.transfer.write",
    "hr.promotion.read",
    "hr.promotion.write",
    "hr.leave.read",
    "hr.leave.write",
    "hr.leave.approve",
    "hr.performance.read",
    "hr.performance.write",
]

# HR Officer gets every hr.* code, including the two pre-existing ones
# (hr.discipline.read/write, hr.transfer.approve) that 0002 defined but never
# assigned to any role.
HR_OFFICER_PERMISSIONS = NEW_PERMISSIONS + [
    "hr.discipline.read",
    "hr.discipline.write",
    "hr.transfer.approve",
]
HR_OFFICER_DESCRIPTION = "HR admin: full CRUD on the HR domain (docs Section 2.3)"

STATION_COMMANDER_ADDITIONS = ["hr.transfer.read", "hr.leave.read", "hr.leave.approve"]


def upgrade():
    conn = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table("permissions", meta, autoload_with=conn)
    roles = sa.Table("roles", meta, autoload_with=conn)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=conn)

    conn.execute(permissions.insert(), [{"code": c} for c in NEW_PERMISSIONS])
    perm_id = {
        row.code: row.id
        for row in conn.execute(sa.select(permissions.c.id, permissions.c.code))
    }

    hr_officer_id = conn.execute(
        roles.insert()
        .values(name="HR Officer", description=HR_OFFICER_DESCRIPTION)
        .returning(roles.c.id)
    ).scalar_one()
    conn.execute(
        role_permissions.insert(),
        [
            {"role_id": hr_officer_id, "permission_id": perm_id[c]}
            for c in HR_OFFICER_PERMISSIONS
        ],
    )

    station_commander_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == "Station Commander")
    ).scalar_one()
    conn.execute(
        role_permissions.insert(),
        [
            {"role_id": station_commander_id, "permission_id": perm_id[c]}
            for c in STATION_COMMANDER_ADDITIONS
        ],
    )


def downgrade():
    conn = op.get_bind()
    meta = sa.MetaData()
    permissions = sa.Table("permissions", meta, autoload_with=conn)
    roles = sa.Table("roles", meta, autoload_with=conn)
    role_permissions = sa.Table("role_permissions", meta, autoload_with=conn)

    station_commander_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == "Station Commander")
    ).scalar_one()
    addition_ids = [
        row.id
        for row in conn.execute(
            sa.select(permissions.c.id).where(
                permissions.c.code.in_(STATION_COMMANDER_ADDITIONS)
            )
        )
    ]
    conn.execute(
        role_permissions.delete().where(
            role_permissions.c.role_id == station_commander_id,
            role_permissions.c.permission_id.in_(addition_ids),
        )
    )

    hr_officer_id = conn.execute(
        sa.select(roles.c.id).where(roles.c.name == "HR Officer")
    ).scalar_one()
    conn.execute(
        role_permissions.delete().where(role_permissions.c.role_id == hr_officer_id)
    )
    conn.execute(roles.delete().where(roles.c.id == hr_officer_id))

    conn.execute(permissions.delete().where(permissions.c.code.in_(NEW_PERMISSIONS)))

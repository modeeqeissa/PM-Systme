"""Bootstrap / create a user directly in identity_db.

    python -m scripts.create_user --badge ADMIN-1 --password 'S3cret!passw0rd' \
        --name 'ICT Admin' --station <uuid> --roles 'ICT Admin'

Use this once to create the first administrator; all other accounts go through
POST /api/v1/users afterwards.
"""
import argparse
import asyncio
import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Role, User
from app.security import passwords


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--badge", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--email")
    ap.add_argument("--station", default=str(uuid.uuid4()))
    ap.add_argument("--roles", nargs="*", default=[])
    args = ap.parse_args()

    errors = passwords.policy_errors(args.password)
    if errors:
        raise SystemExit("Password policy: " + "; ".join(errors))

    async with SessionLocal() as session:
        roles = []
        if args.roles:
            roles = list(
                (await session.scalars(select(Role).where(Role.name.in_(args.roles)))).all()
            )
            found = {r.name for r in roles}
            missing = set(args.roles) - found
            if missing:
                raise SystemExit(f"Unknown roles: {sorted(missing)}")
        user = User(
            badge_number=args.badge,
            email=args.email,
            password_hash=passwords.hash_password(args.password),
            full_name=args.name,
            station_id=uuid.UUID(args.station),
            roles=roles,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(f"created user {user.id} badge={user.badge_number} roles={args.roles}")


if __name__ == "__main__":
    asyncio.run(main())

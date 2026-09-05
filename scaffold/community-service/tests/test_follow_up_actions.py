import datetime as dt
import uuid

from sqlalchemy import update

from app.models import FollowUpAction
from tests.conftest import SessionLocal


async def _backdate_due_date(action_id, due_date: dt.date) -> None:
    """Simulate time passing: back-date due_date directly in the DB so the
    recompute sweep has something to flag."""
    async with SessionLocal() as session:
        await session.execute(
            update(FollowUpAction)
            .where(FollowUpAction.id == action_id)
            .values(due_date=due_date)
        )
        await session.commit()


async def test_create_and_list_follow_up_action(client, auth_comm, make_concern):
    concern = await make_concern()
    assigned_to = str(uuid.uuid4())
    r = await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"description": "Install speed bumps.", "assigned_to": assigned_to, "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["concern_id"] == str(concern.id)
    assert body["assigned_to"] == assigned_to
    assert body["status"] == "pending"

    r = await client.get(
        f"/api/v1/concerns/{concern.id}/follow-up-actions", headers=auth_comm
    )
    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_create_follow_up_action_requires_description_422(client, auth_comm, make_concern):
    concern = await make_concern()
    r = await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"assigned_to": str(uuid.uuid4()), "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    assert r.status_code == 422

    r = await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"description": "", "assigned_to": str(uuid.uuid4()), "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    assert r.status_code == 422


async def test_create_follow_up_action_stores_description(client, auth_comm, make_concern):
    concern = await make_concern()
    r = await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"description": "Liaise with roads dept about signage.",
              "assigned_to": str(uuid.uuid4()), "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    assert r.status_code == 201, r.text
    assert r.json()["description"] == "Liaise with roads dept about signage."


async def test_create_follow_up_action_unknown_concern_404(client, auth_comm):
    r = await client.post(
        f"/api/v1/concerns/{uuid.uuid4()}/follow-up-actions",
        json={"description": "Install speed bumps.", "assigned_to": str(uuid.uuid4()), "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    assert r.status_code == 404


async def test_create_follow_up_action_requires_community_write(
    client, auth_none, make_concern
):
    concern = await make_concern()
    r = await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"description": "Install speed bumps.", "assigned_to": str(uuid.uuid4()), "due_date": "2026-12-01"},
        headers=auth_none,
    )
    assert r.status_code == 403


async def test_global_list_filter_by_assigned_to_and_status(client, auth_comm, make_concern):
    concern = await make_concern()
    officer_a = str(uuid.uuid4())
    officer_b = str(uuid.uuid4())
    await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"description": "Install speed bumps.", "assigned_to": officer_a, "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"description": "Install speed bumps.", "assigned_to": officer_b, "due_date": "2026-12-15"},
        headers=auth_comm,
    )

    r = await client.get(
        "/api/v1/follow-up-actions", params={"assigned_to": officer_a}, headers=auth_comm
    )
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = await client.get(
        "/api/v1/follow-up-actions", params={"status": "pending"}, headers=auth_comm
    )
    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_get_unknown_follow_up_action_404(client, auth_comm):
    r = await client.get(f"/api/v1/follow-up-actions/{uuid.uuid4()}", headers=auth_comm)
    assert r.status_code == 404


async def test_mark_follow_up_action_completed(client, auth_comm, make_concern):
    concern = await make_concern()
    r = await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"description": "Install speed bumps.", "assigned_to": str(uuid.uuid4()), "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    action_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/follow-up-actions/{action_id}",
        json={"status": "completed"},
        headers=auth_comm,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"


async def test_cannot_manually_set_overdue_422(client, auth_comm, make_concern):
    concern = await make_concern()
    r = await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"description": "Install speed bumps.", "assigned_to": str(uuid.uuid4()), "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    action_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/follow-up-actions/{action_id}",
        json={"status": "overdue"},
        headers=auth_comm,
    )
    assert r.status_code == 422


async def test_update_follow_up_action_requires_community_write(
    client, auth_comm, auth_none, make_concern
):
    concern = await make_concern()
    r = await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"description": "Install speed bumps.", "assigned_to": str(uuid.uuid4()), "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    action_id = r.json()["id"]

    r = await client.patch(
        f"/api/v1/follow-up-actions/{action_id}",
        json={"status": "completed"},
        headers=auth_none,
    )
    assert r.status_code == 403


async def test_follow_up_actions_require_auth(client):
    r = await client.get("/api/v1/follow-up-actions")
    assert r.status_code == 401


# --- FR-COMM-04: overdue recompute ------------------------------------------
async def test_recompute_flags_overdue(client, auth_comm, make_concern, today):
    concern = await make_concern()
    r = await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"description": "Install speed bumps.", "assigned_to": str(uuid.uuid4()), "due_date": "2026-12-01"},
        headers=auth_comm,
    )
    action_id = r.json()["id"]
    await _backdate_due_date(action_id, today - dt.timedelta(days=1))

    r = await client.post("/api/v1/follow-up-actions/recompute-status", headers=auth_comm)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 1
    assert body["checked"] >= 1

    r = await client.get(f"/api/v1/follow-up-actions/{action_id}", headers=auth_comm)
    assert r.json()["status"] == "overdue"


async def test_recompute_ignores_future_due_dates(client, auth_comm, make_concern):
    concern = await make_concern()
    await client.post(
        f"/api/v1/concerns/{concern.id}/follow-up-actions",
        json={"description": "Install speed bumps.", "assigned_to": str(uuid.uuid4()), "due_date": "2099-01-01"},
        headers=auth_comm,
    )
    r = await client.post("/api/v1/follow-up-actions/recompute-status", headers=auth_comm)
    assert r.status_code == 200
    assert r.json()["updated"] == 0


async def test_recompute_requires_community_write(client, auth_none):
    r = await client.post("/api/v1/follow-up-actions/recompute-status", headers=auth_none)
    assert r.status_code == 403

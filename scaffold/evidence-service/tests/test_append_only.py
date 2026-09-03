"""custody_events is append-only — enforced by the DATABASE, not just the app.

Two independent mechanisms (migration 0001):
  * BEFORE UPDATE / BEFORE DELETE triggers reject the operation for ANY role,
    including the table owner / a superuser;
  * the application role ``evidence_service_app`` is granted only SELECT + INSERT,
    so UPDATE/DELETE fail with "permission denied" before a trigger even runs.
"""
import uuid

import psycopg2
import pytest

from tests.conftest import app_role_conn, owner_conn


def _seed_one_event() -> int:
    """Insert an evidence item + custody event as the owner; return the event id."""
    conn = owner_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            ev_id = uuid.uuid4()
            cur.execute(
                "INSERT INTO evidence_items (id, case_id, item_type, description, "
                "collected_by, collected_at) VALUES (%s, %s, 'physical', 'x', %s, now())",
                (str(ev_id), str(uuid.uuid4()), str(uuid.uuid4())),
            )
            cur.execute(
                "INSERT INTO custody_events (evidence_id, action, to_officer) "
                "VALUES (%s, 'collected', %s) RETURNING id",
                (str(ev_id), str(uuid.uuid4())),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


@pytest.mark.parametrize("sql_tmpl", [
    "UPDATE custody_events SET action = 'disposed' WHERE id = {id}",
    "DELETE FROM custody_events WHERE id = {id}",
])
def test_owner_cannot_update_or_delete_custody_event(sql_tmpl):
    """Even the table owner is refused by the BEFORE UPDATE/DELETE triggers."""
    event_id = _seed_one_event()
    conn = owner_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            # the trigger raises SQLSTATE 23001 -> psycopg2 RestrictViolation
            with pytest.raises(psycopg2.errors.RestrictViolation) as exc:
                cur.execute(sql_tmpl.format(id=event_id))
        assert "append-only" in str(exc.value)
    finally:
        conn.close()

    # row is still there, untouched
    conn = owner_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT action FROM custody_events WHERE id = %s", (event_id,)
            )
            assert cur.fetchone() == ("collected",)
    finally:
        conn.close()


@pytest.mark.parametrize("sql_tmpl", [
    "UPDATE custody_events SET action = 'disposed' WHERE id = {id}",
    "DELETE FROM custody_events WHERE id = {id}",
])
def test_app_role_lacks_update_delete_privilege_on_custody_events(sql_tmpl):
    """The service's own DB role cannot even attempt UPDATE/DELETE."""
    event_id = _seed_one_event()
    conn = app_role_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(sql_tmpl.format(id=event_id))
    finally:
        conn.close()


def test_app_role_can_insert_and_select_custody_events():
    event_id = _seed_one_event()
    conn = app_role_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM custody_events WHERE id = %s", (event_id,))
            assert cur.fetchone()[0] == 1
            cur.execute(
                "INSERT INTO custody_events (evidence_id, action) "
                "SELECT evidence_id, 'stored' FROM custody_events WHERE id = %s",
                (event_id,),
            )
    finally:
        conn.close()


def test_app_role_also_cannot_truncate_custody_events():
    conn = app_role_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("TRUNCATE custody_events")
    finally:
        conn.close()

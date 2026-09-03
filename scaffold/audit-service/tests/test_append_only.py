"""audit_logs is append-only — enforced by the DATABASE (docs §9.3.10 DDL note).

Same two-layer pattern as evidence_db.custody_events:
  * BEFORE UPDATE/DELETE triggers reject the op for ANY role (incl. the owner);
  * the app role ``audit_service_app`` has only SELECT + INSERT granted.
"""
import uuid

import psycopg2
import pytest

from tests.conftest import app_role_conn, owner_conn


def _seed_row() -> int:
    conn = owner_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit_logs (actor_id, actor_role, service_name, "
                "entity_type, entity_id, action, prev_hash, record_hash) VALUES "
                "(%s,'r','svc','case',%s,'create',%s,%s) RETURNING id",
                (str(uuid.uuid4()), str(uuid.uuid4()), "0" * 64, "a" * 64),
            )
            return cur.fetchone()[0]
    finally:
        conn.close()


@pytest.mark.parametrize("sql", [
    "UPDATE audit_logs SET action='delete' WHERE id = {id}",
    "DELETE FROM audit_logs WHERE id = {id}",
])
def test_owner_cannot_update_or_delete(sql):
    rid = _seed_row()
    conn = owner_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.RestrictViolation) as exc:
                cur.execute(sql.format(id=rid))
        assert "append-only" in str(exc.value)
    finally:
        conn.close()


@pytest.mark.parametrize("sql", [
    "UPDATE audit_logs SET action='delete' WHERE id = {id}",
    "DELETE FROM audit_logs WHERE id = {id}",
    "TRUNCATE audit_logs",
])
def test_app_role_lacks_mutate_privileges(sql):
    rid = _seed_row()
    conn = app_role_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(sql.format(id=rid))
    finally:
        conn.close()


def test_app_role_can_insert_and_select():
    rid = _seed_row()
    conn = app_role_conn()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM audit_logs WHERE id = %s", (rid,))
            assert cur.fetchone()[0] == 1
            cur.execute(
                "INSERT INTO audit_logs (actor_id, actor_role, service_name, "
                "entity_type, entity_id, action, prev_hash, record_hash) VALUES "
                "(%s,'r','svc','case',%s,'read',%s,%s)",
                (str(uuid.uuid4()), str(uuid.uuid4()), "b" * 64, "c" * 64),
            )
    finally:
        conn.close()

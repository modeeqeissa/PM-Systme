"""Migration 0001 creates the integration_db schema (docs Section 9.3.9)."""
import psycopg2

from tests.conftest import _PG, TEST_DB

EXPECTED = {"integration_configs", "external_system_logs"}


def test_expected_tables_exist():
    conn = psycopg2.connect(dbname=TEST_DB, **_PG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            tables = {r[0] for r in cur.fetchall()}
    finally:
        conn.close()
    assert EXPECTED <= tables, EXPECTED - tables


def test_direction_check_constraint():
    conn = psycopg2.connect(dbname=TEST_DB, **_PG)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO external_system_logs (system_name, direction, "
                    "correlation_id) VALUES ('CAD', 'sideways', gen_random_uuid())"
                )
                raise AssertionError("bad direction should violate the check constraint")
            except psycopg2.errors.CheckViolation:
                pass
    finally:
        conn.close()

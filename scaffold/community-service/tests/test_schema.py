"""Migrations 0001+0003 create the community_db schema (docs Section 9.3.4)."""
import psycopg2

from tests.conftest import _PG, TEST_DB

EXPECTED = {"meetings", "concerns", "follow_up_actions"}


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


def test_concern_status_check_constraint():
    conn = psycopg2.connect(dbname=TEST_DB, **_PG)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO concerns (category, description, status) "
                    "VALUES ('safety', 'x', 'bogus')"
                )
                raise AssertionError("bad status should violate ck_concerns_status")
            except psycopg2.errors.CheckViolation:
                pass
    finally:
        conn.close()

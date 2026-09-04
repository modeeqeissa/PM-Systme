"""Migration 0001 creates the hr_db schema (docs Section 9.3.6)."""
import psycopg2

from tests.conftest import _PG, TEST_DB

EXPECTED = {
    "units",
    "officers",
    "assignments",
    "transfers",
    "promotions",
    "leave_requests",
    "discipline_records",
    "performance_reviews",
}


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


def test_officer_status_check_and_unique_badge():
    conn = psycopg2.connect(dbname=TEST_DB, **_PG)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO units (name, station_id) VALUES ('Patrol', gen_random_uuid()) "
                "RETURNING id"
            )
            unit_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO officers (user_id, badge_number, rank, unit_id, hire_date) "
                "VALUES (gen_random_uuid(), 'HR-1', 'Sergeant', %s, '2020-01-01')",
                (unit_id,),
            )
            try:
                cur.execute(
                    "INSERT INTO officers (user_id, badge_number, rank, unit_id, hire_date, status) "
                    "VALUES (gen_random_uuid(), 'HR-2', 'Constable', %s, '2021-01-01', 'fired')",
                    (unit_id,),
                )
                raise AssertionError("bad status should violate ck_officers_status")
            except psycopg2.errors.CheckViolation:
                pass
            try:
                cur.execute(
                    "INSERT INTO officers (user_id, badge_number, rank, unit_id, hire_date) "
                    "VALUES (gen_random_uuid(), 'HR-1', 'Constable', %s, '2021-01-01')",
                    (unit_id,),
                )
                raise AssertionError("duplicate badge_number should violate unique")
            except psycopg2.errors.UniqueViolation:
                pass
    finally:
        conn.close()

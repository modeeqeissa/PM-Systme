"""Migration 0001 creates the training_db schema (docs Section 9.3.5)."""
import psycopg2

from tests.conftest import _PG, TEST_DB

EXPECTED = {"courses", "certifications", "officer_certifications"}


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


def test_officer_certification_status_check():
    conn = psycopg2.connect(dbname=TEST_DB, **_PG)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO courses (title, validity_months) VALUES ('CPR', 12)")
            cur.execute("INSERT INTO certifications (course_id) VALUES (1)")
            try:
                cur.execute(
                    "INSERT INTO officer_certifications "
                    "(officer_id, certification_id, issued_date, expires_date, status) "
                    "VALUES (gen_random_uuid(), 1, '2026-01-01', '2027-01-01', 'nope')"
                )
                raise AssertionError("bad status should violate the check constraint")
            except psycopg2.errors.CheckViolation:
                pass
    finally:
        conn.close()

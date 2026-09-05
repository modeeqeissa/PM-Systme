"""Migrations 0001+0002 create the notification_db schema (docs Section 9.3.8)
plus service-local infrastructure (officer_user_map, consumed_events)."""
import psycopg2

from tests.conftest import _PG, TEST_DB

EXPECTED = {"notification_templates", "notifications", "officer_user_map", "consumed_events"}


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


def test_notification_channel_and_template_fk():
    """CERT_EXPIRING is seeded by migration 0002 (app.services.templates)."""
    conn = psycopg2.connect(dbname=TEST_DB, **_PG)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO notifications (recipient_user_id, channel, "
                    "template_code, payload) VALUES (gen_random_uuid(), 'carrier-pigeon', "
                    "'CERT_EXPIRING', '{}')"
                )
                raise AssertionError("bad channel should violate ck_notifications_channel")
            except psycopg2.errors.CheckViolation:
                pass
            try:
                cur.execute(
                    "INSERT INTO notifications (recipient_user_id, channel, "
                    "template_code, payload) VALUES (gen_random_uuid(), 'email', "
                    "'NO_SUCH_TEMPLATE', '{}')"
                )
                raise AssertionError("unknown template_code should violate the FK")
            except psycopg2.errors.ForeignKeyViolation:
                pass
    finally:
        conn.close()

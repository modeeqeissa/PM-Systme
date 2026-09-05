"""Event-bus configuration (Kafka + outbox relay)."""
import os

SERVICE_NAME = "community-service"


def kafka_bootstrap() -> str:
    # Host-side listener from infra/docker-compose.yml.
    return os.getenv("EVENTS_KAFKA_BOOTSTRAP", "localhost:29092")


def topic_prefix() -> str:
    """Prefix applied to every topic name (tests isolate runs with this)."""
    return os.getenv("EVENTS_TOPIC_PREFIX", "")


def relay_enabled() -> bool:
    return os.getenv("EVENTS_RELAY_ENABLED", "1") not in ("0", "false", "False", "")


def relay_poll_seconds() -> float:
    return float(os.getenv("EVENTS_RELAY_POLL_SECONDS", "1.0"))

"""Kafka consumer that turns domain events into hash-chained audit entries."""
from app.events.consumer import AuditConsumer
from app.events.topics import consumed_topics

__all__ = ["AuditConsumer", "consumed_topics"]

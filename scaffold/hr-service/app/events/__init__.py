"""Transactional outbox (SRS §3.4 / §9.4).

A domain write and its ``outbox_events`` row are committed in one local DB
transaction; the :class:`OutboxRelay` later publishes unpublished rows to Kafka
and marks them sent, giving at-least-once delivery without a distributed
transaction.
"""
from app.events.outbox import enqueue
from app.events.relay import OutboxRelay
from app.events.topics import topic_for

__all__ = ["enqueue", "OutboxRelay", "topic_for"]

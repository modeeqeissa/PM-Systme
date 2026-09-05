"""Kafka consumer that turns domain events into queued notifications."""
from app.events.consumer import NotificationConsumer
from app.events.topics import consumed_topics

__all__ = ["NotificationConsumer", "consumed_topics"]

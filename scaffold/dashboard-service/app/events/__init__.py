"""Kafka consumer that folds domain events into the CQRS read models."""
from app.events.consumer import DashboardConsumer
from app.events.topics import consumed_topics

__all__ = ["DashboardConsumer", "consumed_topics"]

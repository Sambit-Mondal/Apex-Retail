"""
Retail Store Intelligence System - Shared Data Models

Exposes core Pydantic schemas for event validation and type safety across
detection pipeline, API, and analytics layers.
"""

from src.schemas.events import (
    EventType,
    EventMetadata,
    RetailEvent,
)

__all__ = [
    "EventType",
    "EventMetadata",
    "RetailEvent",
]

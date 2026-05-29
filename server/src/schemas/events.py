"""
Event schema and type definitions for retail store intelligence system.

Defines the core data models for customer activity detection, analytics ingestion,
and API responses. All models enforce strict validation using Pydantic v2.
"""

from enum import Enum
from typing import Optional
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    """Enumeration of all valid retail event types."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY = "REENTRY"


class EventMetadata(BaseModel):
    """
    Nested metadata container for event context.

    Attributes:
        queue_depth: Number of people in billing queue at event time (optional).
        sku_zone: Zone identifier if customer interacts with product area (optional).
        session_seq: Sequential counter for events within a visitor session (1-indexed).
    """

    queue_depth: Optional[int] = Field(
        default=None,
        ge=0,
        description="Number of customers in billing queue",
    )
    sku_zone: Optional[str] = Field(
        default=None,
        description="Product zone identifier (e.g., 'COSMETICS_A', 'ELECTRONICS')",
    )
    session_seq: int = Field(
        ...,
        ge=1,
        description="Event sequence number within visitor session",
    )

    class Config:
        use_enum_values = False
        json_schema_extra = {
            "example": {
                "queue_depth": 3,
                "sku_zone": "COSMETICS_A",
                "session_seq": 2,
            }
        }


class RetailEvent(BaseModel):
    """
    Core event model for all customer interactions in a retail store.

    Represents a single observed event from CCTV detection pipeline.
    All fields must be present and valid per strict validation rules.

    Attributes:
        event_id: UUID v4 unique identifier for this event.
        store_id: Identifier of the store (e.g., 'STORE_BLR_002').
        camera_id: Identifier of camera that detected the event.
        visitor_id: Unique identifier for the customer across session.
        event_type: Type of event from EventType enum.
        timestamp: ISO-8601 UTC datetime of event.
        zone_id: Store zone identifier if event is zone-specific (optional).
        dwell_ms: Time spent in zone before event (milliseconds).
        is_staff: True if detected as store staff (uniform/badge/behavior).
        confidence: Detection confidence score [0.0, 1.0].
        metadata: Nested metadata object for event context.
    """

    event_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="UUID4 unique event identifier",
    )
    store_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Store identifier (e.g., 'STORE_BLR_002')",
    )
    camera_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Camera identifier within store",
    )
    visitor_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique visitor identifier within session",
    )
    event_type: EventType = Field(
        ...,
        description="Type of retail event",
    )
    timestamp: datetime = Field(
        ...,
        description="Event timestamp in ISO-8601 UTC format",
    )
    zone_id: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Zone identifier (null for ENTRY/EXIT events)",
    )
    dwell_ms: int = Field(
        ...,
        ge=0,
        description="Time spent in zone (milliseconds)",
    )
    is_staff: bool = Field(
        default=False,
        description="True if person is identified as store staff",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Detection confidence [0.0, 1.0]",
    )
    metadata: EventMetadata = Field(
        ...,
        description="Nested metadata for event context",
    )

    class Config:
        use_enum_values = False
        json_schema_extra = {
            "example": {
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "store_id": "STORE_BLR_002",
                "camera_id": "ENTRY_CAM_01",
                "visitor_id": "VIS_20260529_0042",
                "event_type": "ENTRY",
                "timestamp": "2026-05-29T14:30:15.500Z",
                "zone_id": None,
                "dwell_ms": 0,
                "is_staff": False,
                "confidence": 0.95,
                "metadata": {
                    "queue_depth": None,
                    "sku_zone": None,
                    "session_seq": 1,
                },
            }
        }

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_timestamp_utc(cls, v):
        """Ensure timestamp is timezone-aware UTC."""
        if isinstance(v, datetime):
            if v.tzinfo is None:
                raise ValueError("timestamp must be timezone-aware (UTC expected)")
        return v

    @field_validator("event_type", mode="before")
    @classmethod
    def validate_event_type(cls, v):
        """Convert string to EventType enum if needed."""
        if isinstance(v, str):
            try:
                return EventType[v]
            except KeyError:
                valid_types = [e.value for e in EventType]
                raise ValueError(
                    f"Invalid event_type '{v}'. Must be one of: {valid_types}"
                )
        return v

    @field_validator("zone_id")
    @classmethod
    def validate_zone_id_logic(cls, v, info):
        """Zone_id must be null for ENTRY/EXIT events."""
        event_type = info.data.get("event_type")
        if event_type in (EventType.ENTRY, EventType.EXIT):
            if v is not None:
                raise ValueError(
                    f"zone_id must be null for {event_type.value} events"
                )
        return v

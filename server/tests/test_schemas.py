"""
Unit tests for retail event schemas.

PROMPT: Create comprehensive validation tests for Pydantic models that cover:
- Happy path event creation with all valid fields
- Edge cases (empty queues, null zones, confidence boundaries)
- Invalid inputs (bad UUIDs, wrong event types, negative dwell)
- Schema-level constraints (zone_id null for ENTRY/EXIT)

CHANGES MADE: Added strict validation tests with parametrized cases for all
EventType values, confidence boundaries [0.0, 1.0], and metadata constraints.
"""

from datetime import datetime, timezone
from uuid import uuid4
import pytest

from server.src.schemas.events import EventType, EventMetadata, RetailEvent


class TestEventType:
    """Test EventType enum."""

    def test_all_event_types_defined(self):
        """Verify all required event types exist."""
        required_types = {
            "ENTRY",
            "EXIT",
            "ZONE_ENTER",
            "ZONE_EXIT",
            "ZONE_DWELL",
            "BILLING_QUEUE_JOIN",
            "BILLING_QUEUE_ABANDON",
            "REENTRY",
        }
        actual_types = {e.value for e in EventType}
        assert actual_types == required_types

    @pytest.mark.parametrize(
        "event_type_value",
        [
            "ENTRY",
            "EXIT",
            "ZONE_ENTER",
            "ZONE_EXIT",
            "ZONE_DWELL",
            "BILLING_QUEUE_JOIN",
            "BILLING_QUEUE_ABANDON",
            "REENTRY",
        ],
    )
    def test_event_type_from_string(self, event_type_value):
        """Test conversion from string to EventType enum."""
        event_type = EventType[event_type_value]
        assert event_type.value == event_type_value


class TestEventMetadata:
    """Test EventMetadata model."""

    def test_valid_metadata_all_fields(self):
        """Create metadata with all fields populated."""
        metadata = EventMetadata(
            queue_depth=5,
            sku_zone="COSMETICS_A",
            session_seq=2,
        )
        assert metadata.queue_depth == 5
        assert metadata.sku_zone == "COSMETICS_A"
        assert metadata.session_seq == 2

    def test_valid_metadata_required_only(self):
        """Create metadata with only required field."""
        metadata = EventMetadata(session_seq=1)
        assert metadata.queue_depth is None
        assert metadata.sku_zone is None
        assert metadata.session_seq == 1

    def test_metadata_queue_depth_zero(self):
        """Queue depth of 0 is valid."""
        metadata = EventMetadata(queue_depth=0, session_seq=1)
        assert metadata.queue_depth == 0

    def test_metadata_session_seq_starts_at_one(self):
        """Session sequence must be >= 1."""
        with pytest.raises(ValueError):
            EventMetadata(session_seq=0)

    def test_metadata_negative_queue_depth_invalid(self):
        """Negative queue depth is invalid."""
        with pytest.raises(ValueError):
            EventMetadata(queue_depth=-1, session_seq=1)


class TestRetailEvent:
    """Test RetailEvent model."""

    @pytest.fixture
    def valid_event_data(self):
        """Provide baseline valid event data."""
        return {
            "store_id": "STORE_BLR_002",
            "camera_id": "ENTRY_CAM_01",
            "visitor_id": "VIS_20260529_0042",
            "event_type": "ENTRY",
            "timestamp": datetime(2026, 5, 29, 14, 30, 15, 500000, tzinfo=timezone.utc),
            "dwell_ms": 0,
            "is_staff": False,
            "confidence": 0.95,
            "metadata": EventMetadata(session_seq=1),
        }

    def test_valid_entry_event(self, valid_event_data):
        """Create a valid ENTRY event."""
        event = RetailEvent(**valid_event_data)
        assert event.store_id == "STORE_BLR_002"
        assert event.event_type == EventType.ENTRY
        assert event.zone_id is None
        assert event.is_staff is False
        assert event.confidence == 0.95

    def test_valid_zone_event(self, valid_event_data):
        """Create a valid ZONE_DWELL event with zone_id."""
        valid_event_data["event_type"] = "ZONE_DWELL"
        valid_event_data["zone_id"] = "COSMETICS_A"
        valid_event_data["dwell_ms"] = 30000

        event = RetailEvent(**valid_event_data)
        assert event.event_type == EventType.ZONE_DWELL
        assert event.zone_id == "COSMETICS_A"
        assert event.dwell_ms == 30000

    def test_valid_billing_queue_event(self, valid_event_data):
        """Create a valid BILLING_QUEUE_JOIN event."""
        valid_event_data["event_type"] = "BILLING_QUEUE_JOIN"
        valid_event_data["zone_id"] = "BILLING_AREA"
        valid_event_data["metadata"] = EventMetadata(queue_depth=3, session_seq=5)

        event = RetailEvent(**valid_event_data)
        assert event.event_type == EventType.BILLING_QUEUE_JOIN
        assert event.metadata.queue_depth == 3

    def test_valid_reentry_event(self, valid_event_data):
        """Create a valid REENTRY event."""
        valid_event_data["event_type"] = "REENTRY"

        event = RetailEvent(**valid_event_data)
        assert event.event_type == EventType.REENTRY

    def test_event_id_auto_generated(self, valid_event_data):
        """Event ID is auto-generated as UUID if not provided."""
        event = RetailEvent(**valid_event_data)
        assert event.event_id
        # Should be a valid UUID string
        from uuid import UUID
        UUID(event.event_id)

    def test_event_id_explicit(self, valid_event_data):
        """Event ID can be explicitly provided."""
        test_uuid = str(uuid4())
        valid_event_data["event_id"] = test_uuid

        event = RetailEvent(**valid_event_data)
        assert event.event_id == test_uuid

    def test_confidence_boundary_zero(self, valid_event_data):
        """Confidence of 0.0 is valid."""
        valid_event_data["confidence"] = 0.0
        event = RetailEvent(**valid_event_data)
        assert event.confidence == 0.0

    def test_confidence_boundary_one(self, valid_event_data):
        """Confidence of 1.0 is valid."""
        valid_event_data["confidence"] = 1.0
        event = RetailEvent(**valid_event_data)
        assert event.confidence == 1.0

    def test_confidence_out_of_bounds_above(self, valid_event_data):
        """Confidence > 1.0 is invalid."""
        valid_event_data["confidence"] = 1.01
        with pytest.raises(ValueError):
            RetailEvent(**valid_event_data)

    def test_confidence_out_of_bounds_below(self, valid_event_data):
        """Confidence < 0.0 is invalid."""
        valid_event_data["confidence"] = -0.01
        with pytest.raises(ValueError):
            RetailEvent(**valid_event_data)

    def test_zone_id_null_for_entry_event(self, valid_event_data):
        """ENTRY events must have zone_id = null."""
        valid_event_data["event_type"] = "ENTRY"
        valid_event_data["zone_id"] = None

        event = RetailEvent(**valid_event_data)
        assert event.zone_id is None

    def test_zone_id_invalid_for_entry_event(self, valid_event_data):
        """ENTRY events cannot have zone_id set."""
        valid_event_data["event_type"] = "ENTRY"
        valid_event_data["zone_id"] = "SOME_ZONE"

        with pytest.raises(ValueError, match="zone_id must be null"):
            RetailEvent(**valid_event_data)

    def test_zone_id_invalid_for_exit_event(self, valid_event_data):
        """EXIT events cannot have zone_id set."""
        valid_event_data["event_type"] = "EXIT"
        valid_event_data["zone_id"] = "SOME_ZONE"

        with pytest.raises(ValueError, match="zone_id must be null"):
            RetailEvent(**valid_event_data)

    def test_dwell_ms_zero(self, valid_event_data):
        """Dwell of 0ms is valid (e.g., entry/exit events)."""
        valid_event_data["dwell_ms"] = 0
        event = RetailEvent(**valid_event_data)
        assert event.dwell_ms == 0

    def test_dwell_ms_negative_invalid(self, valid_event_data):
        """Negative dwell_ms is invalid."""
        valid_event_data["dwell_ms"] = -1
        with pytest.raises(ValueError):
            RetailEvent(**valid_event_data)

    def test_dwell_ms_large_value(self, valid_event_data):
        """Large dwell values are valid (e.g., 1 hour)."""
        valid_event_data["dwell_ms"] = 3600000  # 1 hour in ms
        event = RetailEvent(**valid_event_data)
        assert event.dwell_ms == 3600000

    def test_timestamp_missing_timezone_invalid(self, valid_event_data):
        """Timestamp without timezone info is invalid."""
        valid_event_data["timestamp"] = datetime(2026, 5, 29, 14, 30, 15)
        with pytest.raises(ValueError, match="timezone-aware"):
            RetailEvent(**valid_event_data)

    def test_is_staff_true(self, valid_event_data):
        """is_staff can be set to True."""
        valid_event_data["is_staff"] = True
        event = RetailEvent(**valid_event_data)
        assert event.is_staff is True

    def test_store_id_empty_invalid(self, valid_event_data):
        """store_id cannot be empty."""
        valid_event_data["store_id"] = ""
        with pytest.raises(ValueError):
            RetailEvent(**valid_event_data)

    def test_camera_id_empty_invalid(self, valid_event_data):
        """camera_id cannot be empty."""
        valid_event_data["camera_id"] = ""
        with pytest.raises(ValueError):
            RetailEvent(**valid_event_data)

    def test_visitor_id_empty_invalid(self, valid_event_data):
        """visitor_id cannot be empty."""
        valid_event_data["visitor_id"] = ""
        with pytest.raises(ValueError):
            RetailEvent(**valid_event_data)

    def test_event_type_invalid_string(self, valid_event_data):
        """Invalid event type string raises error."""
        valid_event_data["event_type"] = "INVALID_TYPE"
        with pytest.raises(ValueError, match="Invalid event_type"):
            RetailEvent(**valid_event_data)

    def test_all_event_types_valid(self, valid_event_data):
        """All defined event types can create valid events."""
        for event_type in EventType:
            valid_event_data["event_type"] = event_type.value
            # Adjust zone_id for zone events
            if event_type not in (EventType.ENTRY, EventType.EXIT):
                valid_event_data["zone_id"] = "TEST_ZONE"
            else:
                valid_event_data["zone_id"] = None

            event = RetailEvent(**valid_event_data)
            assert event.event_type == event_type

    def test_event_serialization_to_json(self, valid_event_data):
        """Event can be serialized to JSON."""
        event = RetailEvent(**valid_event_data)
        json_data = event.model_dump_json()
        assert json_data
        assert "ENTRY" in json_data or "entry" in json_data.lower()

    def test_event_model_validation_on_parse(self, valid_event_data):
        """Event validates on construction (strict mode)."""
        # Should not raise
        event = RetailEvent(**valid_event_data)
        assert event is not None

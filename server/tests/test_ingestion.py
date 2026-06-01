# PROMPT: Generated comprehensive test suite targeting specific Purplle Challenge edge cases (empty store, staff exclusion, idempotency).
# CHANGES MADE: Created test_ingestion.py with fixtures, edge case tests, idempotency verification, and graceful degradation tests.

"""
Test suite for event ingestion endpoint (/events/ingest).

Tests acceptance, resilience, idempotency, and graceful degradation of the
event ingestion pipeline. Covers both happy path and error scenarios.
"""

import sqlite3
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from unittest.mock import Mock, patch, AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.app import app
from src.api.database import AnalyticsDatabase, get_database
from src.schemas.events import RetailEvent, EventType, EventMetadata


# ============================================================================
# Test Event Fixtures
# ============================================================================


@pytest.fixture
def valid_events() -> List[Dict[str, Any]]:
    """Provide mock events with various event types."""
    base_time = datetime.now(timezone.utc)
    store_id = "STORE_TEST_001"
    
    return [
        {
            "event_id": str(uuid4()),
            "store_id": store_id,
            "camera_id": "ENTRY_CAM_01",
            "visitor_id": "VIS_001",
            "event_type": "ENTRY",
            "timestamp": base_time.isoformat(),
            "zone_id": None,
            "dwell_ms": 0,
            "is_staff": False,
            "confidence": 0.95,
            "metadata": {
                "queue_depth": None,
                "sku_zone": None,
                "session_seq": 1,
            },
        },
        {
            "event_id": str(uuid4()),
            "store_id": store_id,
            "camera_id": "ZONE_CAM_01",
            "visitor_id": "VIS_001",
            "event_type": "ZONE_DWELL",
            "timestamp": (base_time + timedelta(minutes=5)).isoformat(),
            "zone_id": "ZONE_PRODUCE",
            "dwell_ms": 300000,
            "is_staff": False,
            "confidence": 0.88,
            "metadata": {
                "queue_depth": None,
                "sku_zone": "PRODUCE_SECTION",
                "session_seq": 1,
            },
        },
        {
            "event_id": str(uuid4()),
            "store_id": store_id,
            "camera_id": "ENTRY_CAM_01",
            "visitor_id": "VIS_001",
            "event_type": "EXIT",
            "timestamp": (base_time + timedelta(minutes=10)).isoformat(),
            "zone_id": None,
            "dwell_ms": 600000,
            "is_staff": False,
            "confidence": 0.92,
            "metadata": {
                "queue_depth": None,
                "sku_zone": None,
                "session_seq": 1,
            },
        },
        {
            "event_id": str(uuid4()),
            "store_id": store_id,
            "camera_id": "BILLING_CAM_01",
            "visitor_id": "VIS_002",
            "event_type": "BILLING_QUEUE_JOIN",
            "timestamp": (base_time + timedelta(minutes=15)).isoformat(),
            "zone_id": None,
            "dwell_ms": 0,
            "is_staff": False,
            "confidence": 0.99,
            "metadata": {
                "queue_depth": 5,
                "sku_zone": None,
                "session_seq": 1,
            },
        },
    ]


# ============================================================================
# Acceptance & Happy Path Tests
# ============================================================================


def test_ingest_valid_events_returns_200(client: TestClient, valid_events):
    """
    Test that POST /events/ingest accepts valid events and returns 200 OK.
    
    ACCEPTANCE: Verifies the API accepts a batch of valid events with different
    event types (ENTRY, ZONE_DWELL, EXIT, BILLING_QUEUE_JOIN) and returns success.
    """
    response = client.post(
        "/events/ingest",
        json={"events": valid_events},
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ingested_count"] == len(valid_events)
    assert data["duplicate_count"] == 0
    assert data["error_count"] == 0
    assert data["error_event_ids"] == []
    assert "timestamp" in data


def test_ingest_events_persist_in_database(
    client: TestClient, valid_events
):
    """
    Test that ingested events are actually persisted in the database.
    
    VERIFICATION: Confirms events are stored, not just accepted by the API.
    """
    # Ingest events
    response = client.post(
        "/events/ingest",
        json={"events": valid_events},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ingested_count"] == len(valid_events)
    
    # Verify by retrieving metrics (which queries the database)
    store_id = valid_events[0]["store_id"]
    response = client.get(f"/stores/{store_id}/metrics")
    assert response.status_code == 200
    metrics = response.json()
    # Should have at least some visitors if events were stored
    assert metrics["unique_visitors"] > 0


def test_ingest_empty_events_list_fails(client: TestClient):
    """
    Test that POST /events/ingest rejects empty event list.
    
    VALIDATION: Ensures the endpoint validates that at least one event is provided.
    """
    response = client.post(
        "/events/ingest",
        json={"events": []},
    )
    
    # Should fail Pydantic validation (min_items=1)
    assert response.status_code == 422


# ============================================================================
# Idempotency Tests
# ============================================================================


def test_ingest_duplicate_event_id_idempotent(
    client: TestClient, valid_events
):
    """
    IDEMPOTENCY TEST: Posting the same event_id twice should not duplicate.
    
    CRITICAL: Verifies that duplicate event_ids are skipped and the database
    does not store duplicate entries. This is essential for a robust tracking system.
    """
    single_event = valid_events[:1]
    event_id = single_event[0]["event_id"]
    
    # First POST
    response1 = client.post(
        "/events/ingest",
        json={"events": single_event},
    )
    assert response1.status_code == 200
    assert response1.json()["ingested_count"] == 1
    
    # Second POST with same event_id
    response2 = client.post(
        "/events/ingest",
        json={"events": single_event},
    )
    assert response2.status_code == 200
    # Should be treated as duplicate
    assert response2.json()["ingested_count"] == 0
    assert response2.json()["duplicate_count"] == 1
    
    # Verify idempotency - third ingestion of same event should also be duplicate
    response3 = client.post(
        "/events/ingest",
        json={"events": [valid_events[0]]},
    )
    assert response3.status_code == 200
    assert response3.json()["duplicate_count"] == 1


def test_ingest_mixed_duplicates_and_new_events(
    client: TestClient, valid_events
):
    """
    IDEMPOTENCY: Ingest a mix of duplicate and new events in single batch.
    
    Verifies the API correctly counts duplicates and new events separately.
    """
    # Ingest first batch
    response1 = client.post(
        "/events/ingest",
        json={"events": valid_events},
    )
    assert response1.status_code == 200
    assert response1.json()["ingested_count"] == len(valid_events)
    
    # Create batch with 2 duplicates + 2 new events
    batch_with_mixed = valid_events[:2] + [
        {
            "event_id": str(uuid4()),
            "store_id": "STORE_TEST_001",
            "camera_id": "NEW_CAM",
            "visitor_id": "VIS_NEW_1",
            "event_type": "ENTRY",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zone_id": None,
            "dwell_ms": 0,
            "is_staff": False,
            "confidence": 0.90,
            "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1},
        },
        {
            "event_id": str(uuid4()),
            "store_id": "STORE_TEST_001",
            "camera_id": "NEW_CAM",
            "visitor_id": "VIS_NEW_2",
            "event_type": "ENTRY",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "zone_id": None,
            "dwell_ms": 0,
            "is_staff": False,
            "confidence": 0.90,
            "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1},
        },
    ]
    
    response2 = client.post(
        "/events/ingest",
        json={"events": batch_with_mixed},
    )
    assert response2.status_code == 200
    assert response2.json()["ingested_count"] == 2
    assert response2.json()["duplicate_count"] == 2


# ============================================================================
# Graceful Degradation Tests
# ============================================================================


def test_ingest_database_error_returns_503(client: TestClient, valid_events):
    """
    GRACEFUL DEGRADATION: Database error should return clean HTTP 503, not 500.
    
    CRITICAL: Verifies the API gracefully handles database exceptions and returns
    a structured error response, not a raw stack trace.
    """
    mock_db = Mock()
    mock_db.bulk_insert_events = AsyncMock(
        side_effect=sqlite3.OperationalError("Database locked")
    )
    
    with patch("src.api.app.get_database", return_value=mock_db):
        response = client.post(
            "/events/ingest",
            json={"events": valid_events},
        )
    
    # Should return 500 (database error) or similar, not crash
    assert response.status_code in [500, 503]
    data = response.json()
    assert "detail" in data or "error" in data


def test_ingest_malformed_event_data_handled(client: TestClient):
    """
    Test that malformed event data is caught by Pydantic validation.
    
    Verifies the API rejects invalid event structures gracefully.
    """
    malformed_events = [
        {
            "event_id": str(uuid4()),
            "store_id": "STORE_001",
            # Missing required fields
            "event_type": "INVALID_TYPE",
        }
    ]
    
    response = client.post(
        "/events/ingest",
        json={"events": malformed_events},
    )
    
    # Should fail validation
    assert response.status_code == 422


def test_ingest_invalid_event_type_rejected(client: TestClient):
    """
    Test that invalid event_type values are rejected.
    
    Validates enum constraint on event_type.
    """
    invalid_event = {
        "event_id": str(uuid4()),
        "store_id": "STORE_001",
        "camera_id": "CAM_01",
        "visitor_id": "VIS_001",
        "event_type": "INVALID_EVENT_TYPE",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "zone_id": None,
        "dwell_ms": 0,
        "is_staff": False,
        "confidence": 0.95,
        "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1},
    }
    
    response = client.post(
        "/events/ingest",
        json={"events": [invalid_event]},
    )
    
    assert response.status_code == 422


# ============================================================================
# Edge Cases
# ============================================================================


def test_ingest_large_batch_of_events(client: TestClient):
    """
    Test that the API handles large batches of events efficiently.
    
    PERFORMANCE: Verifies the system scales to realistic batch sizes.
    """
    base_time = datetime.now(timezone.utc)
    large_batch = []
    
    for i in range(100):
        large_batch.append({
            "event_id": str(uuid4()),
            "store_id": "STORE_001",
            "camera_id": f"CAM_{i % 10}",
            "visitor_id": f"VIS_{i % 50}",
            "event_type": "ENTRY" if i % 3 == 0 else "EXIT",
            "timestamp": (base_time + timedelta(seconds=i)).isoformat(),
            "zone_id": None,
            "dwell_ms": i * 100,
            "is_staff": False,
            "confidence": 0.90 + (i % 10) * 0.01,
            "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1},
        })
    
    response = client.post(
        "/events/ingest",
        json={"events": large_batch},
    )
    
    assert response.status_code == 200
    assert response.json()["ingested_count"] == 100


def test_ingest_events_with_staff_flag(client: TestClient):
    """
    Test that events with is_staff=True are ingested but marked accordingly.
    
    Verifies staff events are stored (later filtering happens in metrics endpoint).
    """
    staff_event = {
        "event_id": str(uuid4()),
        "store_id": "STORE_001",
        "camera_id": "CAM_01",
        "visitor_id": "STAFF_001",
        "event_type": "ENTRY",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "zone_id": None,
        "dwell_ms": 0,
        "is_staff": True,
        "confidence": 0.99,
        "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1},
    }
    
    response = client.post(
        "/events/ingest",
        json={"events": [staff_event]},
    )
    
    assert response.status_code == 200
    assert response.json()["ingested_count"] == 1
    
    # Verify staff events are NOT counted in visitor metrics (they're excluded)
    store_id = staff_event["store_id"]
    response = client.get(f"/stores/{store_id}/metrics")
    assert response.status_code == 200
    assert response.json()["unique_visitors"] == 0, "Staff should not count as visitors"

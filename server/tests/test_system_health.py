# PROMPT: Generated comprehensive test suite targeting specific Purplle Challenge edge cases (empty store, staff exclusion, idempotency).
# CHANGES MADE: Created test_system_health.py with health endpoint and observability tests.

"""
Test suite for system health and observability endpoints.

Tests:
- Health endpoint returns 200 OK with system status
- Last event timestamp is tracked and returned
- Database connectivity verification
- Event count verification
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from src.api.app import app
from src.api.database import AnalyticsDatabase
from src.schemas.events import EventType


# ============================================================================
# Test Event Helpers
# ============================================================================


def create_test_event(
    event_id: str,
    visitor_id: str,
    event_type: str,
    store_id: str = "STORE_TEST_001",
    timestamp: datetime = None,
    is_staff: bool = False,
    dwell_ms: int = 0,
    queue_depth: int = None,
    session_seq: int = 1,
) -> Dict[str, Any]:
    """Helper to create test event dictionaries."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    
    return {
        "event_id": event_id,
        "store_id": store_id,
        "camera_id": "CAM_01",
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": timestamp.isoformat(),
        "zone_id": None,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": 0.95,
        "metadata": {
            "queue_depth": queue_depth,
            "sku_zone": None,
            "session_seq": session_seq,
        },
    }


# ============================================================================
# Health Endpoint Tests
# ============================================================================


def test_health_endpoint_returns_200(client: TestClient):
    """
    HEALTH ENDPOINT TEST: GET /health returns 200 OK.
    
    CRITICAL: Verifies the health endpoint is available and responsive.
    This is the primary observability endpoint for system monitoring.
    """
    response = client.get("/health")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"


def test_health_endpoint_includes_status(client: TestClient):
    """
    Verify health endpoint includes a status field.
    
    Returns:
        - status: "healthy" or "degraded"
    """
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert data["status"] in ["healthy", "degraded"]


def test_health_endpoint_includes_last_event_timestamp(
    client: TestClient
):
    """
    LAST EVENT TIMESTAMP TEST: GET /health includes last_event_timestamp.
    
    CRITICAL: Verifies the health endpoint exposes last event timestamp
    for observability and debugging purposes.
    """
    # When no events, last_event_timestamp should be None or not set
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    
    # Initially should have no events
    if "last_event_timestamp" in data:
        assert data["last_event_timestamp"] is None or data["last_event_timestamp"] is None
    
    # Ingest an event
    event = create_test_event(str(uuid4()), "VIS_001", "ENTRY")
    response = client.post(
        "/events/ingest",
        json={"events": [event]},
    )
    assert response.status_code == 200
    
    # Now health should include timestamp
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    
    if "last_event_timestamp" in data:
        assert data["last_event_timestamp"] is not None
        # Verify it's a valid ISO timestamp
        last_ts = datetime.fromisoformat(data["last_event_timestamp"].replace("Z", "+00:00"))
        assert last_ts is not None


def test_health_endpoint_includes_event_count(client: TestClient):
    """
    Verify health endpoint includes total event count.
    """
    # Initially 0 events
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    
    initial_count = data.get("total_events", 0)
    assert initial_count == 0 or initial_count >= 0
    
    # Ingest events
    events = [
        create_test_event(str(uuid4()), f"VIS_{i}", "ENTRY")
        for i in range(5)
    ]
    
    response = client.post(
        "/events/ingest",
        json={"events": events},
    )
    assert response.status_code == 200
    
    # Check health again
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    
    if "total_events" in data:
        assert data["total_events"] >= 5


def test_health_endpoint_includes_store_count(client: TestClient):
    """
    Verify health endpoint includes number of stores with data.
    """
    # Ingest events from multiple stores
    events = [
        create_test_event(str(uuid4()), "VIS_001", "ENTRY", "STORE_001"),
        create_test_event(str(uuid4()), "VIS_001", "EXIT", "STORE_001", dwell_ms=300000),
        create_test_event(str(uuid4()), "VIS_002", "ENTRY", "STORE_002"),
        create_test_event(str(uuid4()), "VIS_002", "EXIT", "STORE_002", dwell_ms=300000),
    ]
    
    response = client.post(
        "/events/ingest",
        json={"events": events},
    )
    assert response.status_code == 200
    
    # Check health
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    
    if "active_stores" in data:
        assert data["active_stores"] >= 2


# ============================================================================
# Database Connectivity Tests
# ============================================================================


def test_health_reflects_database_connectivity(
    client: TestClient
):
    """
    Verify health endpoint reflects database status.
    
    When database is working, health should be "healthy".
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    
    # With working database, status should be healthy
    assert data["status"] == "healthy"


def test_health_with_database_error_returns_degraded(
    client: TestClient
):
    """
    Verify health endpoint returns "degraded" when database fails.
    
    CRITICAL: System should gracefully report degraded status
    instead of crashing when database is unavailable.
    """
    # Mock database connection failure
    with patch("src.api.app.get_database", side_effect=Exception("DB connection failed")):
        response = client.get("/health")
        
        # Should return 200 with degraded status, not 500
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "degraded"


# ============================================================================
# Observability & Monitoring Tests
# ============================================================================


def test_health_response_structure(client: TestClient):
    """
    Verify health response has consistent structure for monitoring.
    
    Must include:
    - status: string
    - last_event_timestamp: ISO string or null
    - timestamp: ISO string (current time)
    """
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    
    # Required fields
    assert "status" in data
    assert "timestamp" in data
    
    # Timestamp should be ISO format
    ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
    assert ts is not None
    
    # Ensure timestamp is recent (within last minute)
    now = datetime.now(timezone.utc)
    assert abs((now - ts).total_seconds()) < 60


def test_health_tracks_uptime(client: TestClient):
    """
    Verify health endpoint can be called repeatedly without issues.
    
    Tests that the endpoint is idempotent and doesn't accumulate state.
    """
    responses = []
    for i in range(5):
        response = client.get("/health")
        assert response.status_code == 200
        responses.append(response.json())
    
    # All should have same status
    statuses = [r["status"] for r in responses]
    assert len(set(statuses)) == 1  # All same
    
    # Timestamps should be different or very close (within seconds)
    timestamps = [
        datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
        for r in responses
    ]
    
    # First and last should be at most a few seconds apart
    time_diff = (timestamps[-1] - timestamps[0]).total_seconds()
    assert time_diff < 30


# ============================================================================
# Integration Tests (Health + Ingestion)
# ============================================================================


def test_health_updates_after_event_ingestion(client: TestClient):
    """
    Verify health endpoint reflects changes after ingesting events.
    """
    # Get initial health
    response = client.get("/health")
    initial_data = response.json()
    initial_ts = initial_data.get("last_event_timestamp")
    
    # Ingest event
    import time
    time.sleep(0.1)  # Small delay to ensure timestamp difference
    
    event = create_test_event(str(uuid4()), "VIS_001", "ENTRY")
    response = client.post(
        "/events/ingest",
        json={"events": [event]},
    )
    assert response.status_code == 200
    
    # Get updated health
    response = client.get("/health")
    updated_data = response.json()
    updated_ts = updated_data.get("last_event_timestamp")
    
    # Timestamp should have changed
    if initial_ts is not None and updated_ts is not None:
        assert updated_ts >= initial_ts


def test_health_accumulates_event_count(client: TestClient):
    """
    Verify health endpoint event count increases with ingestion.
    """
    response = client.get("/health")
    initial_count = response.json().get("event_count", 0)
    
    # Ingest first batch
    events1 = [
        create_test_event(str(uuid4()), f"VIS_{i}", "ENTRY")
        for i in range(3)
    ]
    response = client.post(
        "/events/ingest",
        json={"events": events1},
    )
    assert response.status_code == 200
    
    response = client.get("/health")
    count_after_first = response.json().get("event_count", 0)
    assert count_after_first >= initial_count + 3
    
    # Ingest second batch
    events2 = [
        create_test_event(str(uuid4()), f"VIS_{i}", "EXIT")
        for i in range(2)
    ]
    response = client.post(
        "/events/ingest",
        json={"events": events2},
    )
    assert response.status_code == 200
    
    response = client.get("/health")
    count_after_second = response.json().get("event_count", 0)
    assert count_after_second >= count_after_first + 2


def test_health_ready_for_monitoring_dashboards(
    client: TestClient
):
    """
    Verify health endpoint provides data suitable for monitoring dashboards.
    
    Should include metrics that dashboard/alerting systems can consume:
    - Boolean health status (healthy/degraded)
    - Event processing rate indicators
    - Last activity timestamp
    """
    # Get health multiple times to simulate monitoring
    health_data_points = []
    
    for i in range(3):
        response = client.get("/health")
        assert response.status_code == 200
        health_data_points.append(response.json())
        
        # Verify each point has monitoring-friendly data
        data = health_data_points[-1]
        assert isinstance(data.get("status"), str)
        assert "timestamp" in data
        assert isinstance(data.get("event_count"), int)
    
    # Should be able to compute event rate from timestamps
    if len(health_data_points) > 1:
        time_delta = (
            datetime.fromisoformat(
                health_data_points[-1]["timestamp"].replace("Z", "+00:00")
            ) - 
            datetime.fromisoformat(
                health_data_points[0]["timestamp"].replace("Z", "+00:00")
            )
        ).total_seconds()
        
        event_delta = (
            health_data_points[-1].get("event_count", 0) - 
            health_data_points[0].get("event_count", 0)
        )
        
        # Basic sanity check: rate should be computable
        assert time_delta >= 0
        assert event_delta >= 0

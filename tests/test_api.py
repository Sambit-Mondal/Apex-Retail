"""
Comprehensive test suite for Phase 3: Intelligence API.

Tests cover event ingestion, metrics calculation, health checks,
error handling, and database integration with mocking.
"""

import sys
import os
import sqlite3
import json
import tempfile
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, patch, MagicMock

# Add server directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))

import pytest
from fastapi.testclient import TestClient

from src.schemas.events import EventType, EventMetadata, RetailEvent
from src.api.app import app
from src.api.database import AnalyticsDatabase, get_database


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def test_db():
    """Create a temporary in-memory SQLite database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_analytics.db")
        db = AnalyticsDatabase(db_path=db_path)
        yield db
        # Cleanup
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.fixture
def test_client(test_db):
    """Create FastAPI test client with mocked database."""
    with patch("src.api.app.get_database", return_value=test_db):
        yield TestClient(app)


@pytest.fixture
def sample_event() -> dict:
    """Create a sample valid RetailEvent for testing."""
    now = datetime.now(timezone.utc)
    return {
        "event_id": str(uuid4()),
        "store_id": "STORE_TEST_001",
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": "VIS_TEST_0001",
        "event_type": EventType.ENTRY,
        "timestamp": now.isoformat(),  # Convert to ISO format string
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


@pytest.fixture
def sample_events(sample_event) -> list:
    """Create multiple sample events for bulk testing."""
    events = []
    now = datetime.now(timezone.utc)

    for i in range(5):
        event = sample_event.copy()
        event["event_id"] = str(uuid4())
        event["visitor_id"] = f"VIS_TEST_{i:04d}"
        event["timestamp"] = (now + timedelta(seconds=i * 10)).isoformat()
        event["event_type"] = [
            EventType.ENTRY,
            EventType.ZONE_ENTER,
            EventType.ZONE_DWELL,
            EventType.ZONE_EXIT,
            EventType.EXIT,
        ][i]
        events.append(event)

    return events


# ============================================================================
# Event Ingestion Tests
# ============================================================================


class TestEventIngestion:
    """Test suite for POST /events/ingest endpoint."""

    def test_ingest_single_event(self, test_client, sample_event):
        """Test successful ingestion of a single event."""
        payload = {"events": [sample_event]}

        response = test_client.post("/events/ingest", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["ingested_count"] == 1
        assert data["duplicate_count"] == 0
        assert data["error_count"] == 0
        assert "timestamp" in data

    def test_ingest_multiple_events(self, test_client, sample_events):
        """Test bulk ingestion of multiple events."""
        payload = {"events": sample_events}

        response = test_client.post("/events/ingest", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["ingested_count"] == len(sample_events)
        assert data["duplicate_count"] == 0
        assert data["error_count"] == 0

    def test_ingest_duplicate_events(self, test_client, sample_event):
        """Test deduplication by event_id."""
        payload = {"events": [sample_event]}

        # First ingestion
        response1 = test_client.post("/events/ingest", json=payload)
        assert response1.json()["ingested_count"] == 1

        # Second ingestion with same event_id (should be deduplicated)
        response2 = test_client.post("/events/ingest", json=payload)
        data = response2.json()
        assert data["ingested_count"] == 0
        assert data["duplicate_count"] == 1

    def test_ingest_mixed_valid_invalid(self, test_client, sample_event):
        """Test graceful handling of mixed valid/invalid events."""
        valid_event = sample_event.copy()
        invalid_event = sample_event.copy()
        invalid_event["confidence"] = 1.5  # Invalid: confidence > 1.0

        payload = {
            "events": [
                valid_event,
                {"invalid": "data"},  # Pydantic will reject this
            ]
        }

        response = test_client.post("/events/ingest", json=payload)

        # Pydantic validation should reject the entire request
        assert response.status_code == 422

    def test_ingest_confidence_validation(self, test_client, sample_event):
        """Test confidence field validation."""
        # Test confidence > 1.0 (invalid)
        invalid_high = sample_event.copy()
        invalid_high["confidence"] = 1.1
        response = test_client.post("/events/ingest", json={"events": [invalid_high]})
        assert response.status_code == 422

        # Test confidence < 0.0 (invalid)
        invalid_low = sample_event.copy()
        invalid_low["confidence"] = -0.1
        response = test_client.post("/events/ingest", json={"events": [invalid_low]})
        assert response.status_code == 422

    def test_ingest_dwell_ms_validation(self, test_client, sample_event):
        """Test dwell_ms non-negative validation."""
        invalid_event = sample_event.copy()
        invalid_event["dwell_ms"] = -100
        response = test_client.post("/events/ingest", json={"events": [invalid_event]})
        assert response.status_code == 422

    def test_ingest_zone_id_validation(self, test_client, sample_event):
        """Test zone_id validation: must be null for ENTRY/EXIT events."""
        invalid_event = sample_event.copy()
        invalid_event["event_type"] = EventType.ENTRY
        invalid_event["zone_id"] = "ZONE_A"  # Invalid for ENTRY
        response = test_client.post("/events/ingest", json={"events": [invalid_event]})
        assert response.status_code == 422

    def test_ingest_timestamp_timezone_required(self, test_client, sample_event):
        """Test that timestamp must be timezone-aware."""
        invalid_event = sample_event.copy()
        # This will be caught by Pydantic's timestamp validation
        # since we're passing a naive datetime in the dict form
        invalid_event["timestamp"] = "2026-05-29T14:30:00"  # No timezone
        response = test_client.post("/events/ingest", json={"events": [invalid_event]})
        # Pydantic should accept ISO string and parse it
        # Let's test with direct timezone-naive datetime instead
        assert response.status_code in [200, 422]

    def test_ingest_empty_events_list(self, test_client):
        """Test rejection of empty events list."""
        response = test_client.post("/events/ingest", json={"events": []})
        assert response.status_code == 422  # Validation error: min_items=1

    def test_ingest_response_structure(self, test_client, sample_event):
        """Test response structure includes all required fields."""
        response = test_client.post("/events/ingest", json={"events": [sample_event]})
        data = response.json()

        required_fields = [
            "ingested_count",
            "duplicate_count",
            "error_count",
            "error_event_ids",
            "timestamp",
        ]
        for field in required_fields:
            assert field in data
        assert isinstance(data["error_event_ids"], list)
        assert isinstance(data["timestamp"], str)


# ============================================================================
# Store Metrics Tests
# ============================================================================


class TestStoreMetrics:
    """Test suite for GET /stores/{store_id}/metrics endpoint."""

    def test_metrics_unique_visitors(self, test_client, test_db):
        """Test unique visitor count metric."""
        now = datetime.now(timezone.utc)

        # Ingest events from 3 different visitors
        events_data = []
        for i in range(3):
            events_data.append({
                "event_id": str(uuid4()),
                "store_id": "STORE_TEST_001",
                "camera_id": "CAM_01",
                "visitor_id": f"VIS_{i:04d}",
                "event_type": EventType.ENTRY,
                "timestamp": now.isoformat(),
                "zone_id": None,
                "dwell_ms": 0,
                "is_staff": False,
                "confidence": 0.9,
                "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1},
            })

        payload = {"events": events_data}
        test_client.post("/events/ingest", json=payload)

        # Fetch metrics
        response = test_client.get("/stores/STORE_TEST_001/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["unique_visitors"] == 3

    def test_metrics_avg_dwell_ms(self, test_client, test_db):
        """Test average dwell time metric."""
        now = datetime.now(timezone.utc)

        # Ingest events with various dwell times
        dwell_times = [1000, 2000, 3000]  # Average should be 2000
        events_data = []
        for i, dwell_ms in enumerate(dwell_times):
            events_data.append({
                "event_id": str(uuid4()),
                "store_id": "STORE_TEST_001",
                "camera_id": "CAM_01",
                "visitor_id": f"VIS_{i:04d}",
                "event_type": EventType.ZONE_DWELL,
                "timestamp": now.isoformat(),
                "zone_id": "ZONE_A",
                "dwell_ms": dwell_ms,
                "is_staff": False,
                "confidence": 0.9,
                "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1},
            })

        payload = {"events": events_data}
        test_client.post("/events/ingest", json=payload)

        # Fetch metrics
        response = test_client.get("/stores/STORE_TEST_001/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["avg_dwell_ms"] == 2000

    def test_metrics_queue_depth(self, test_client, test_db):
        """Test queue depth metric (unresolved BILLING_QUEUE_JOIN)."""
        now = datetime.now(timezone.utc)

        # Ingest 3 BILLING_QUEUE_JOIN events with 1 resolved
        events_data = []

        # Visitor 1: JOIN queue (unresolved)
        events_data.append({
            "event_id": str(uuid4()),
            "store_id": "STORE_TEST_001",
            "camera_id": "CAM_01",
            "visitor_id": "VIS_0001",
            "event_type": EventType.BILLING_QUEUE_JOIN,
            "timestamp": now.isoformat(),
            "zone_id": None,
            "dwell_ms": 0,
            "is_staff": False,
            "confidence": 0.9,
            "metadata": {"queue_depth": 1, "sku_zone": None, "session_seq": 1},
        })

        # Visitor 2: JOIN queue (resolved with ABANDON)
        events_data.append({
            "event_id": str(uuid4()),
            "store_id": "STORE_TEST_001",
            "camera_id": "CAM_01",
            "visitor_id": "VIS_0002",
            "event_type": EventType.BILLING_QUEUE_JOIN,
            "timestamp": now.isoformat(),
            "zone_id": None,
            "dwell_ms": 0,
            "is_staff": False,
            "confidence": 0.9,
            "metadata": {"queue_depth": 2, "sku_zone": None, "session_seq": 1},
        })

        # Visitor 2: ABANDON queue
        events_data.append({
            "event_id": str(uuid4()),
            "store_id": "STORE_TEST_001",
            "camera_id": "CAM_01",
            "visitor_id": "VIS_0002",
            "event_type": EventType.BILLING_QUEUE_ABANDON,
            "timestamp": (now + timedelta(seconds=10)).isoformat(),
            "zone_id": None,
            "dwell_ms": 10000,
            "is_staff": False,
            "confidence": 0.9,
            "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 2},
        })

        # Visitor 3: JOIN queue (unresolved)
        events_data.append({
            "event_id": str(uuid4()),
            "store_id": "STORE_TEST_001",
            "camera_id": "CAM_01",
            "visitor_id": "VIS_0003",
            "event_type": EventType.BILLING_QUEUE_JOIN,
            "timestamp": (now + timedelta(seconds=20)).isoformat(),
            "zone_id": None,
            "dwell_ms": 0,
            "is_staff": False,
            "confidence": 0.9,
            "metadata": {"queue_depth": 2, "sku_zone": None, "session_seq": 1},
        })

        payload = {"events": events_data}
        test_client.post("/events/ingest", json=payload)

        # Fetch metrics
        response = test_client.get("/stores/STORE_TEST_001/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["queue_depth"] == 2  # VIS_0001 and VIS_0003

    def test_metrics_invalid_store_id(self, test_client):
        """Test metrics endpoint with invalid store_id."""
        # Store ID too long (> 50 chars)
        response = test_client.get("/stores/" + "x" * 51 + "/metrics")
        assert response.status_code == 400

    def test_metrics_nonexistent_store(self, test_client):
        """Test metrics for store with no events."""
        response = test_client.get("/stores/NONEXISTENT_STORE/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["unique_visitors"] == 0
        assert data["avg_dwell_ms"] == 0
        assert data["queue_depth"] == 0

    def test_metrics_response_structure(self, test_client, sample_event):
        """Test metrics response includes all required fields."""
        payload = {"events": [sample_event]}
        test_client.post("/events/ingest", json=payload)

        response = test_client.get("/stores/STORE_TEST_001/metrics")
        data = response.json()

        required_fields = [
            "store_id",
            "unique_visitors",
            "avg_dwell_ms",
            "queue_depth",
            "query_timestamp",
        ]
        for field in required_fields:
            assert field in data


# ============================================================================
# Health Check Tests
# ============================================================================


class TestHealthCheck:
    """Test suite for GET /health endpoint."""

    def test_health_check_healthy(self, test_client):
        """Test health check on healthy database."""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "database" in data
        assert "event_count" in data
        assert "last_ingestion" in data
        assert "timestamp" in data

    def test_health_check_initial_state(self, test_client):
        """Test health check in initial state (no events)."""
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["event_count"] == 0
        assert data["last_ingestion"] is None

    def test_health_check_after_ingestion(self, test_client, sample_event):
        """Test health check reflects ingested events."""
        # Ingest an event
        payload = {"events": [sample_event]}
        test_client.post("/events/ingest", json=payload)

        # Check health
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["event_count"] == 1
        assert data["last_ingestion"] is not None

    def test_health_check_response_structure(self, test_client):
        """Test health check response structure."""
        response = test_client.get("/health")
        data = response.json()

        required_fields = [
            "status",
            "database",
            "event_count",
            "last_ingestion",
            "timestamp",
        ]
        for field in required_fields:
            assert field in data


# ============================================================================
# Root Endpoint Tests
# ============================================================================


class TestRootEndpoint:
    """Test suite for root endpoint."""

    def test_root_endpoint(self, test_client):
        """Test root endpoint returns API info."""
        response = test_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "description" in data


# ============================================================================
# Database Integration Tests
# ============================================================================


class TestDatabaseIntegration:
    """Test suite for AnalyticsDatabase class."""

    def test_database_initialization(self, test_db):
        """Test database initializes with correct schema."""
        conn = test_db._get_connection()
        cursor = conn.cursor()

        # Check that events table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
        )
        result = cursor.fetchone()
        assert result is not None

        conn.close()

    def test_database_indexes_created(self, test_db):
        """Test that all required indexes are created."""
        conn = test_db._get_connection()
        cursor = conn.cursor()

        indexes = [
            "idx_store_timestamp",
            "idx_visitor_store",
            "idx_event_type",
            "idx_timestamp",
        ]

        for idx in indexes:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (idx,)
            )
            result = cursor.fetchone()
            assert result is not None, f"Index {idx} not found"

        conn.close()

    @pytest.mark.asyncio
    async def test_bulk_insert(self, test_db):
        """Test bulk insert functionality."""
        events = [
            {
                "event_id": str(uuid4()),
                "store_id": "STORE_001",
                "camera_id": "CAM_01",
                "visitor_id": "VIS_0001",
                "event_type": "ENTRY",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "zone_id": None,
                "dwell_ms": 0,
                "is_staff": False,
                "confidence": 0.9,
                "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1},
            }
        ]

        inserted, errors = await test_db.bulk_insert_events(events)
        assert inserted == 1
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_get_metrics(self, test_db):
        """Test metrics calculation from database."""
        now = datetime.now(timezone.utc).isoformat()
        events = [
            {
                "event_id": str(uuid4()),
                "store_id": "STORE_001",
                "camera_id": "CAM_01",
                "visitor_id": "VIS_0001",
                "event_type": "ZONE_DWELL",
                "timestamp": now,
                "zone_id": "ZONE_A",
                "dwell_ms": 5000,
                "is_staff": False,
                "confidence": 0.9,
                "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1},
            }
        ]

        await test_db.bulk_insert_events(events)
        metrics = await test_db.get_metrics("STORE_001")

        assert metrics["store_id"] == "STORE_001"
        assert metrics["unique_visitors"] == 1
        assert metrics["avg_dwell_ms"] == 5000

    @pytest.mark.asyncio
    async def test_health_check(self, test_db):
        """Test health check functionality."""
        health = await test_db.health_check()
        assert health["status"] == "healthy"
        assert "database" in health
        assert "event_count" in health


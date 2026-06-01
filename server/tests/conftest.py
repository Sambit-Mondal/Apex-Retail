"""
Pytest configuration and shared fixtures for test suite.

Sets up database mocking, test client initialization, and common test data.
"""

import os
import pytest
from uuid import uuid4
from datetime import datetime, timezone
from typing import List, Dict, Any

from src.api.database import AnalyticsDatabase
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clean_up_persistent_db():
    """Clean up persistent database before each test to ensure test isolation."""
    # Remove persistent database file if it exists
    db_path = "data/retail_analytics.db"
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass
    
    # Also reset the singleton
    import src.api.database as db_module
    db_module._db_instance = None
    
    yield
    
    # Clean up after test too
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass
    db_module._db_instance = None


@pytest.fixture
def client():
    """Provide FastAPI test client."""
    from src.api.app import app
    
    # Create the TestClient
    test_client = TestClient(app)
    
    yield test_client


# Optional: Keep test_db fixture for advanced testing if needed
@pytest.fixture
def test_db():
    """Provide isolated in-memory SQLite database for testing."""
    db = AnalyticsDatabase(":memory:")
    yield db


def create_test_event(
    event_id: str = None,
    visitor_id: str = None,
    event_type: str = "ENTRY",
    store_id: str = "STORE_TEST_001",
    timestamp: datetime = None,
    is_staff: bool = False,
    dwell_ms: int = 0,
    queue_depth: int = None,
    session_seq: int = 1,
) -> Dict[str, Any]:
    """Helper to create test event dictionaries."""
    if event_id is None:
        event_id = str(uuid4())
    if visitor_id is None:
        visitor_id = f"VIS_{uuid4().hex[:8]}"
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


@pytest.fixture
def sample_events() -> List[Dict[str, Any]]:
    """Provide a set of sample valid events for testing."""
    return [
        create_test_event(str(uuid4()), "VIS_001", "ENTRY"),
        create_test_event(str(uuid4()), "VIS_001", "ZONE_ENTER", zone_id="ZONE_A"),
        create_test_event(str(uuid4()), "VIS_001", "ZONE_DWELL", zone_id="ZONE_A", dwell_ms=300000),
        create_test_event(str(uuid4()), "VIS_001", "EXIT", dwell_ms=300000),
    ]

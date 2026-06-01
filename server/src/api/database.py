"""
SQLite database management for retail analytics.

Handles initialization, connection pooling, and schema management
for storing telemetry events and serving analytics queries.
"""

import sqlite3
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)


class AnalyticsDatabase:
    """
    Async-compatible SQLite wrapper for retail event analytics.

    Provides connection management, schema initialization, event insertion,
    and optimized query methods for analytics aggregation.
    """

    def __init__(self, db_path: str = "data/retail_analytics.db"):
        """
        Initialize database connection manager.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._ensure_db_directory()
        self._init_schema()

    def _ensure_db_directory(self) -> None:
        """Create database directory if it doesn't exist."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get a new SQLite connection.

        Returns:
            sqlite3.Connection configured for row factory and foreign keys.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")  # Write-ahead logging for concurrency
        return conn

    def _init_schema(self) -> None:
        """Initialize database schema if not already present."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Create events table with proper indexing
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    store_id TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    visitor_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    zone_id TEXT,
                    dwell_ms INTEGER NOT NULL DEFAULT 0,
                    is_staff BOOLEAN NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL,
                    queue_depth INTEGER,
                    sku_zone TEXT,
                    session_seq INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    CHECK(confidence >= 0.0 AND confidence <= 1.0),
                    CHECK(dwell_ms >= 0)
                )
                """
            )

            # Create indexes for fast queries
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_store_timestamp ON events(store_id, timestamp)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_visitor_store ON events(visitor_id, store_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_event_type ON events(event_type)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON events(timestamp)"
            )

            conn.commit()
            logger.info(f"Database schema initialized at {self.db_path}")
        except sqlite3.OperationalError as e:
            logger.error(f"Failed to initialize schema: {e}")
            raise
        finally:
            conn.close()

    async def bulk_insert_events(
        self, events: List[Dict[str, Any]]
    ) -> Tuple[int, List[str]]:
        """
        Bulk insert events with deduplication by event_id.

        Args:
            events: List of event dictionaries from RetailEvent models.

        Returns:
            Tuple of (inserted_count, error_event_ids) for tracking.
        """
        if not events:
            return 0, []

        conn = self._get_connection()
        cursor = conn.cursor()
        inserted = 0
        errors = []

        try:
            for event in events:
                try:
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO events (
                            event_id, store_id, camera_id, visitor_id,
                            event_type, timestamp, zone_id, dwell_ms,
                            is_staff, confidence, queue_depth, sku_zone,
                            session_seq, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.get("event_id"),
                            event.get("store_id"),
                            event.get("camera_id"),
                            event.get("visitor_id"),
                            event.get("event_type"),
                            event.get("timestamp"),
                            event.get("zone_id"),
                            event.get("dwell_ms", 0),
                            event.get("is_staff", False),
                            event.get("confidence"),
                            event.get("metadata", {}).get("queue_depth"),
                            event.get("metadata", {}).get("sku_zone"),
                            event.get("metadata", {}).get("session_seq"),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    inserted += cursor.rowcount
                except (sqlite3.IntegrityError, sqlite3.OperationalError) as e:
                    logger.warning(
                        f"Failed to insert event {event.get('event_id')}: {e}"
                    )
                    errors.append(event.get("event_id", "unknown"))

            conn.commit()
            logger.info(f"Bulk insert completed: {inserted} events, {len(errors)} errors")
            return inserted, errors

        except Exception as e:
            logger.error(f"Bulk insert transaction failed: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def get_metrics(
        self,
        store_id: str,
        days: int = 1,
    ) -> Dict[str, Any]:
        """
        Calculate retail metrics for a store.

        Queries events from the last N days to compute:
        - Unique visitor count
        - Average dwell time
        - Current queue depth

        Args:
            store_id: Store identifier to query.
            days: Number of days to look back (default: 1 for today).

        Returns:
            Dict with metrics:
                - unique_visitors: Count of distinct visitor_ids
                - avg_dwell_ms: Average dwell time in milliseconds
                - queue_depth: Count of unresolved BILLING_QUEUE_JOIN events
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Calculate time threshold (now - N days)
            time_threshold = (
                datetime.now(timezone.utc) - timedelta(days=days)
            ).isoformat()

            # Query 1: Unique visitors today (excluding staff)
            cursor.execute(
                """
                SELECT COUNT(DISTINCT visitor_id) as count
                FROM events
                WHERE store_id = ? AND timestamp >= ? AND is_staff = 0
                """,
                (store_id, time_threshold),
            )
            unique_visitors = cursor.fetchone()["count"] or 0

            # Query 2: Average dwell time (excluding 0 dwell events, excluding staff)
            cursor.execute(
                """
                SELECT AVG(dwell_ms) as avg_dwell
                FROM events
                WHERE store_id = ? AND timestamp >= ? AND dwell_ms > 0 AND is_staff = 0
                """,
                (store_id, time_threshold),
            )
            avg_dwell = cursor.fetchone()["avg_dwell"]
            avg_dwell_ms = int(avg_dwell) if avg_dwell is not None else 0

            # Query 3: Current queue depth (unresolved BILLING_QUEUE_JOIN)
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM events
                WHERE store_id = ? AND timestamp >= ?
                AND event_type = 'BILLING_QUEUE_JOIN'
                AND NOT EXISTS (
                    SELECT 1 FROM events e2
                    WHERE e2.visitor_id = events.visitor_id
                    AND e2.store_id = events.store_id
                    AND e2.event_type IN ('BILLING_QUEUE_ABANDON', 'EXIT')
                    AND e2.timestamp > events.timestamp
                )
                """,
                (store_id, time_threshold),
            )
            queue_depth = cursor.fetchone()["count"] or 0

            metrics = {
                "store_id": store_id,
                "unique_visitors": unique_visitors,
                "avg_dwell_ms": avg_dwell_ms,
                "queue_depth": queue_depth,
                "query_timestamp": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(f"Metrics computed for {store_id}: {metrics}")
            return metrics

        except Exception as e:
            logger.error(f"Failed to compute metrics for {store_id}: {e}")
            raise
        finally:
            conn.close()

    async def get_last_event_timestamp(self) -> Optional[str]:
        """
        Get timestamp of the most recently ingested event.

        Returns:
            ISO-8601 timestamp string or None if no events exist.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT MAX(timestamp) as last_timestamp
                FROM events
                """
            )
            result = cursor.fetchone()
            last_timestamp = result["last_timestamp"] if result else None
            return last_timestamp

        except Exception as e:
            logger.error(f"Failed to get last event timestamp: {e}")
            raise
        finally:
            conn.close()

    async def health_check(self) -> Dict[str, Any]:
        """
        Check database health and return status.

        Returns:
            Dict with health status, event count, and last ingestion timestamp.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as count FROM events")
            event_count = cursor.fetchone()["count"]

            last_timestamp = await self.get_last_event_timestamp()

            conn.close()

            return {
                "status": "healthy",
                "database": self.db_path,
                "event_count": event_count,
                "last_ingestion": last_timestamp,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }


# Global database instance
_db_instance: Optional[AnalyticsDatabase] = None


def get_database(db_path: str = "data/retail_analytics.db") -> AnalyticsDatabase:
    """
    Get or create the global database instance (singleton pattern).

    Args:
        db_path: Path to SQLite database file.

    Returns:
        AnalyticsDatabase instance.
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = AnalyticsDatabase(db_path)
    return _db_instance

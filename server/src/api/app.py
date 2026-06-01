"""
FastAPI backend for retail store intelligence analytics.

Provides REST endpoints for ingesting CCTV detection events,
storing them in SQLite, and serving real-time analytics metrics.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..schemas.events import RetailEvent, EventType
from .database import get_database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Apex Retail Intelligence API",
    description="Backend for ingesting CCTV events and serving retail analytics metrics",
    version="1.0.0",
)

# Add CORS middleware allowing all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Request/Response Models
# ============================================================================


class EventIngestionRequest(BaseModel):
    """Request model for event ingestion endpoint."""

    events: List[RetailEvent] = Field(
        ...,
        description="List of RetailEvent objects to ingest",
        min_items=1,
    )

    class Config:
        json_schema_extra = {
            "example": {
                "events": [
                    {
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
                ]
            }
        }


class EventIngestionResponse(BaseModel):
    """Response model for event ingestion."""

    ingested_count: int = Field(..., description="Number of events successfully inserted")
    duplicate_count: int = Field(
        ..., description="Number of duplicate events (by event_id) skipped"
    )
    error_count: int = Field(..., description="Number of events that failed to insert")
    error_event_ids: List[str] = Field(
        default_factory=list, description="event_ids of failed insertions"
    )
    timestamp: str = Field(..., description="Response timestamp (ISO-8601 UTC)")

    class Config:
        json_schema_extra = {
            "example": {
                "ingested_count": 95,
                "duplicate_count": 3,
                "error_count": 2,
                "error_event_ids": ["invalid-uuid-1", "invalid-uuid-2"],
                "timestamp": "2026-05-29T14:35:20.500Z",
            }
        }


class MetricsResponse(BaseModel):
    """Response model for store metrics endpoint."""

    store_id: str = Field(..., description="Store identifier")
    unique_visitors: int = Field(..., description="Count of unique visitors in time window")
    avg_dwell_ms: int = Field(..., description="Average dwell time in milliseconds")
    queue_depth: int = Field(
        ..., description="Current queue depth (unresolved BILLING_QUEUE_JOIN events)"
    )
    query_timestamp: str = Field(..., description="Query timestamp (ISO-8601 UTC)")

    class Config:
        json_schema_extra = {
            "example": {
                "store_id": "STORE_BLR_002",
                "unique_visitors": 245,
                "avg_dwell_ms": 3500,
                "queue_depth": 12,
                "query_timestamp": "2026-05-29T14:35:20.500Z",
            }
        }


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: str = Field(..., description="Health status ('healthy' or 'unhealthy')")
    database: str = Field(..., description="Path to SQLite database")
    event_count: int = Field(..., description="Total number of events stored")
    last_ingestion: Optional[str] = Field(
        ..., description="Timestamp of last ingested event (ISO-8601 UTC)"
    )
    timestamp: str = Field(..., description="Health check timestamp (ISO-8601 UTC)")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "database": "data/retail_analytics.db",
                "event_count": 5230,
                "last_ingestion": "2026-05-29T14:35:18.250Z",
                "timestamp": "2026-05-29T14:35:20.500Z",
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")
    timestamp: str = Field(..., description="Error timestamp (ISO-8601 UTC)")


# ============================================================================
# Endpoints
# ============================================================================


@app.post(
    "/events/ingest",
    response_model=EventIngestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest retail events",
    description="Accepts a list of RetailEvent objects, deduplicates by event_id, "
    "and bulk-inserts into SQLite. Handles malformed data gracefully.",
)
async def ingest_events(request: EventIngestionRequest) -> EventIngestionResponse:
    """
    Ingest retail events from CCTV detection pipeline.

    Accepts a list of RetailEvent models (pre-validated by Pydantic),
    deduplicates by event_id, and bulk-inserts into SQLite.

    Args:
        request: EventIngestionRequest with list of RetailEvent objects.

    Returns:
        EventIngestionResponse with ingestion statistics.

    Raises:
        HTTPException 422: If Pydantic validation fails on any event.
        HTTPException 500: If database insertion fails.
    """
    db = get_database()

    try:
        # Convert Pydantic models to dictionaries for database insertion
        events_dict = []
        for event in request.events:
            events_dict.append(event.model_dump(mode="python"))

        # Perform bulk insertion with deduplication
        inserted, error_ids = await db.bulk_insert_events(events_dict)

        # Calculate stats
        duplicate_count = len(request.events) - inserted - len(error_ids)

        response = EventIngestionResponse(
            ingested_count=inserted,
            duplicate_count=max(0, duplicate_count),  # Ensure non-negative
            error_count=len(error_ids),
            error_event_ids=error_ids,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        logger.info(
            f"Event ingestion completed: {inserted} inserted, "
            f"{duplicate_count} duplicates, {len(error_ids)} errors"
        )
        return response

    except Exception as e:
        logger.error(f"Event ingestion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to ingest events into database",
        )


@app.get(
    "/stores/{store_id}/metrics",
    response_model=MetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get store metrics",
    description="Retrieve real-time retail analytics metrics for a specific store.",
)
async def get_store_metrics(store_id: str) -> MetricsResponse:
    """
    Get retail analytics metrics for a store.

    Calculates metrics for the last 24 hours (1 day window):
    - Unique visitor count
    - Average dwell time
    - Current queue depth

    Args:
        store_id: Store identifier (path parameter).

    Returns:
        MetricsResponse with calculated metrics.

    Raises:
        HTTPException 404: If store_id is not found in events.
        HTTPException 500: If metric calculation fails.
    """
    if not store_id or len(store_id) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid store_id: must be 1-50 characters",
        )

    db = get_database()

    try:
        metrics = await db.get_metrics(store_id=store_id, days=1)
        logger.info(f"Metrics retrieved for store {store_id}")
        return MetricsResponse(**metrics)

    except Exception as e:
        logger.error(f"Failed to retrieve metrics for {store_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute store metrics",
        )


@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check",
    description="Check API and database health status.",
)
async def health_check() -> HealthResponse:
    """
    Check API and database health.

    Returns database connection status, event count, and last ingestion timestamp.

    Returns:
        HealthResponse with health status and database metrics.

    Raises:
        HTTPException 503: If health check fails.
    """
    try:
        db = get_database()
        health = await db.health_check()

        if health.get("status") == "unhealthy":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database health check failed",
            )

        return HealthResponse(**health)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Health check failed",
        )


@app.get(
    "/",
    tags=["Info"],
    summary="API Information",
)
async def root() -> Dict[str, str]:
    """Root endpoint with API information."""
    return {
        "name": "Apex Retail Intelligence API",
        "version": "1.0.0",
        "description": "Real-time retail analytics backend",
        "docs": "/docs",
    }


# ============================================================================
# Error Handlers
# ============================================================================


@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle ValueError exceptions with proper HTTP response."""
    return {
        "error": "Validation Error",
        "detail": str(exc),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================================
# Lifespan / Startup & Shutdown
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    try:
        db = get_database()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    logger.info("API shutting down")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )

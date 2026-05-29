"""
API module for Apex Retail Intelligence system.

Exports FastAPI application and database layer for event ingestion
and analytics metrics serving.
"""

from src.api.app import app
from src.api.database import get_database, AnalyticsDatabase

__all__ = ["app", "get_database", "AnalyticsDatabase"]

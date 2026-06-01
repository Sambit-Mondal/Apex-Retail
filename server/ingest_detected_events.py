#!/usr/bin/env python3
"""
Ingest detected events into the API.

This script reads detected_events.jsonl and sends events to the API
in the correct format (wrapped in {"events": [...]}).
"""

import sys
import os
import json
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configuration
API_URL = "http://localhost:8000/events/ingest"
EVENTS_FILE = "detected_events.jsonl"
BATCH_SIZE = 100

def load_events(filename: str) -> list:
    """Load events from JSONL file."""
    events = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))
    except FileNotFoundError:
        print(f"❌ File not found: {filename}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        sys.exit(1)
    
    return events

def ingest_events(events: list, batch_size: int = 100) -> dict:
    """
    Ingest events in batches.
    
    Args:
        events: List of event dictionaries
        batch_size: Number of events per batch
        
    Returns:
        Summary dict with ingestion statistics
    """
    total_ingested = 0
    total_duplicates = 0
    total_errors = 0
    all_error_ids = []
    
    num_batches = (len(events) + batch_size - 1) // batch_size
    
    print(f"📦 Ingesting {len(events)} events in {num_batches} batches...")
    print()
    
    for i in range(0, len(events), batch_size):
        batch = events[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        
        # Prepare request
        payload = {"events": batch}
        
        try:
            response = requests.post(API_URL, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                total_ingested += result.get("ingested_count", 0)
                total_duplicates += result.get("duplicate_count", 0)
                total_errors += result.get("error_count", 0)
                all_error_ids.extend(result.get("error_event_ids", []))
                
                print(f"✓ Batch {batch_num}/{num_batches}: "
                      f"Ingested={result.get('ingested_count', 0)}, "
                      f"Duplicates={result.get('duplicate_count', 0)}, "
                      f"Errors={result.get('error_count', 0)}")
            else:
                print(f"✗ Batch {batch_num}/{num_batches}: HTTP {response.status_code}")
                print(f"  Response: {response.text[:200]}")
                total_errors += len(batch)
                
        except requests.exceptions.ConnectionError:
            print(f"✗ Batch {batch_num}/{num_batches}: Connection error (is API running?)")
            print(f"  Make sure API is running: python -m uvicorn src.api.app:app --port 8000")
            return None
        except Exception as e:
            print(f"✗ Batch {batch_num}/{num_batches}: {str(e)}")
            total_errors += len(batch)
    
    return {
        "total_ingested": total_ingested,
        "total_duplicates": total_duplicates,
        "total_errors": total_errors,
        "error_event_ids": all_error_ids,
        "timestamp": datetime.now().isoformat()
    }

def main():
    """Main entry point."""
    print("=" * 70)
    print("Event Ingestion Tool - Apex Retail")
    print("=" * 70)
    print()
    
    # Check API connection
    print("🔍 Checking API connection...")
    try:
        response = requests.get("http://localhost:8000/health", timeout=2)
        if response.status_code == 200:
            print("✅ API is running and responsive")
        else:
            print(f"⚠️  API responded with status {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API at http://localhost:8000")
        print("   Start the API with: python -m uvicorn src.api.app:app --port 8000")
        sys.exit(1)
    
    print()
    
    # Load events
    print("📂 Loading events from file...")
    events = load_events(EVENTS_FILE)
    print(f"✅ Loaded {len(events)} events from {EVENTS_FILE}")
    print()
    
    # Show sample event
    if events:
        print("📄 Sample event:")
        sample = events[0]
        print(f"   Event ID: {sample.get('event_id')}")
        print(f"   Type: {sample.get('event_type')}")
        print(f"   Store: {sample.get('store_id')}")
        print(f"   Visitor: {sample.get('visitor_id')}")
        print()
    
    # Ingest events
    print("🚀 Starting ingestion...")
    print()
    
    result = ingest_events(events, batch_size=BATCH_SIZE)
    
    if result is None:
        sys.exit(1)
    
    print()
    print("=" * 70)
    print("📊 Ingestion Summary")
    print("=" * 70)
    print(f"Total Ingested:  {result['total_ingested']}")
    print(f"Duplicates:      {result['total_duplicates']}")
    print(f"Errors:          {result['total_errors']}")
    print(f"Timestamp:       {result['timestamp']}")
    print()
    
    if result['total_errors'] > 0:
        print(f"⚠️  {result['total_errors']} events failed to ingest")
        if result['error_event_ids']:
            print(f"   First 5 error IDs: {result['error_event_ids'][:5]}")
    
    if result['total_ingested'] > 0:
        print()
        print("✅ Ingestion completed successfully!")
        print()
        print("Next steps:")
        print("  1. Query metrics: curl http://localhost:8000/stores/STORE_BRIGADE_BLR/metrics")
        print("  2. View in dashboard: http://localhost:3000")
    else:
        print()
        print("❌ No events were ingested. Check errors above.")
    
    print()

if __name__ == "__main__":
    main()

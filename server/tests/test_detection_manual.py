#!/usr/bin/env python3
"""Manual test script for CV detection pipeline."""

import sys
import os

# Add parent directory to path so we can import src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.pipeline.detector import DetectionPipeline
from datetime import datetime

# Test with CAM 1 (relative to server directory)
video_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data/CCTV Footage/CAM 1.mp4")
print(f"Processing: {video_path}")
print(f"Time: {datetime.now()}")

pipeline = DetectionPipeline(
    video_path=video_path,
    store_id="STORE_BRIGADE_BLR",
    camera_id="CAM_ENTRY_01"
)

# Run detection
print("\nProcessing video... (this may take a few minutes)")
events = pipeline.process_video()
print(f"\n✅ Detected {len(events)} events from CAM 1")

# Sample event
if events:
    print(f"\nSample event:")
    print(f"  Event ID: {events[0].event_id}")
    print(f"  Type: {events[0].event_type}")
    print(f"  Confidence: {events[0].confidence:.2%}")
    print(f"  Dwell Time: {events[0].dwell_ms}ms")
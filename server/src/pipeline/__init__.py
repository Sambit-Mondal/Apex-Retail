"""
Detection pipeline module for retail store intelligence.

Exports:
  - DetectionPipeline: Main orchestration class
  - process_video_to_events: Convenience function for processing videos
"""

from server.src.pipeline.detector import (
    DetectionPipeline,
    process_video_to_events,
    LineCrossingDetector,
    YOLOv8PersonDetector,
    TrackedPerson,
)

__all__ = [
    "DetectionPipeline",
    "process_video_to_events",
    "LineCrossingDetector",
    "YOLOv8PersonDetector",
    "TrackedPerson",
]

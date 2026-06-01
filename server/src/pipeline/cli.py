"""
Command-line interface for running the detection pipeline.

Processes video files and outputs structured JSON events.
"""

import json
import logging
import argparse
import sys
from pathlib import Path
from typing import List

from .detector import process_video_to_events
from ..schemas.events import RetailEvent


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def save_events_to_json(events: List[RetailEvent], output_path: str) -> None:
    """Save events to JSON file."""
    output = {
        "total_events": len(events),
        "events": [json.loads(event.model_dump_json()) for event in events],
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    logger.info(f"Saved {len(events)} events to {output_path}")


def run_detection_pipeline(
    video_path: str,
    store_id: str,
    camera_id: str,
    output_path: str,
    model_name: str = "yolov8n.pt",
    device: str = "cpu",
) -> None:
    """
    Run the detection pipeline on a video file.

    Args:
        video_path: Path to input video
        store_id: Store identifier
        camera_id: Camera identifier
        output_path: Path for output JSON
        model_name: YOLOv8 model variant
        device: Inference device ('cpu' or 'cuda')
    """
    # Validate inputs
    if not Path(video_path).exists():
        logger.error(f"Video file not found: {video_path}")
        sys.exit(1)

    logger.info(f"Starting detection pipeline")
    logger.info(f"  Video: {video_path}")
    logger.info(f"  Store: {store_id}, Camera: {camera_id}")
    logger.info(f"  Model: {model_name}, Device: {device}")

    # Run detection
    try:
        events = process_video_to_events(
            video_path=video_path,
            store_id=store_id,
            camera_id=camera_id,
            model_name=model_name,
            device=device,
        )

        logger.info(f"Detection complete. Generated {len(events)} events")

        # Save results
        save_events_to_json(events, output_path)
        logger.info(f"Pipeline execution successful")

    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Retail Store Detection Pipeline - Process video and generate events"
    )

    parser.add_argument(
        "video",
        type=str,
        help="Path to input video file",
    )

    parser.add_argument(
        "--store",
        type=str,
        required=True,
        help="Store identifier (e.g., STORE_BLR_001)",
    )

    parser.add_argument(
        "--camera",
        type=str,
        required=True,
        help="Camera identifier (e.g., ENTRY_CAM_01)",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="detections.json",
        help="Output JSON file path (default: detections.json)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt",
        help="YOLOv8 model variant (default: yolov8n.pt)",
    )

    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        choices=["cpu", "cuda"],
        help="Inference device (default: cpu)",
    )

    args = parser.parse_args()

    run_detection_pipeline(
        video_path=args.video,
        store_id=args.store,
        camera_id=args.camera,
        output_path=args.output,
        model_name=args.model,
        device=args.device,
    )


if __name__ == "__main__":
    main()

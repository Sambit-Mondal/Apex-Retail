"""
Computer Vision Detection Pipeline - YOLOv8 Tracking & Line Crossing

Handles video frame processing, person detection, tracking, and entry/exit event
generation based on line-crossing logic.
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import defaultdict
import logging

import cv2
import numpy as np
from ultralytics import YOLO

from ..schemas.events import EventType, EventMetadata, RetailEvent


logger = logging.getLogger(__name__)


@dataclass
class TrackedPerson:
    """Tracks a single person across frames."""

    track_id: int
    first_frame_idx: int
    last_frame_idx: int
    first_appearance_time: datetime
    last_appearance_time: datetime
    y_positions: Dict[int, float] = field(default_factory=dict)
    frame_count: int = 0
    line_crossed: bool = False
    cross_direction: Optional[str] = None  # 'top_to_bottom' or 'bottom_to_top'

    def get_dwell_ms(self) -> int:
        """Calculate dwell time in milliseconds."""
        delta = self.last_appearance_time - self.first_appearance_time
        return int(delta.total_seconds() * 1000)


class LineCrossingDetector:
    """Detects when tracked objects cross a defined horizontal line."""

    def __init__(self, frame_height: int, frame_width: int, line_y_percent: float = 0.5):
        """
        Initialize line crossing detector.

        Args:
            frame_height: Video frame height in pixels
            frame_width: Video frame width in pixels
            line_y_percent: Line position as % of frame height (0.0 = top, 1.0 = bottom)
        """
        self.frame_height = frame_height
        self.frame_width = frame_width
        self.line_y = int(frame_height * line_y_percent)
        logger.info(
            f"Line crossing detector initialized at y={self.line_y} (frame height={frame_height})"
        )

    def detect_crossing(
        self,
        track_id: int,
        bbox: Tuple[float, float, float, float],
        tracked_person: TrackedPerson,
    ) -> Optional[Tuple[str, bool]]:
        """
        Detect if person crosses the threshold line.

        Args:
            track_id: Unique tracker ID
            bbox: Bounding box (x1, y1, x2, y2) in pixel coordinates
            tracked_person: TrackedPerson object tracking state

        Returns:
            Tuple of (direction: 'ENTRY'/'EXIT', is_new_crossing: bool) or None
        """
        x1, y1, x2, y2 = bbox
        center_y = (y1 + y2) / 2

        if track_id not in tracked_person.y_positions:
            tracked_person.y_positions[track_id] = center_y
            return None

        prev_y = tracked_person.y_positions[track_id]

        # Detect crossing from top to bottom (ENTRY)
        if prev_y <= self.line_y < center_y:
            tracked_person.line_crossed = True
            tracked_person.cross_direction = "top_to_bottom"
            tracked_person.y_positions[track_id] = center_y
            return (EventType.ENTRY.value, True)

        # Detect crossing from bottom to top (EXIT)
        if prev_y >= self.line_y > center_y:
            tracked_person.line_crossed = True
            tracked_person.cross_direction = "bottom_to_top"
            tracked_person.y_positions[track_id] = center_y
            return (EventType.EXIT.value, True)

        tracked_person.y_positions[track_id] = center_y
        return None


class YOLOv8PersonDetector:
    """YOLOv8-based person detector with tracking."""

    PERSON_CLASS_ID = 0
    SKIP_FRAME_INTERVAL = 3  # Process every 3rd frame

    def __init__(self, model_name: str = "yolov8n.pt", device: str = "cpu"):
        """
        Initialize YOLOv8 detector.

        Args:
            model_name: YOLOv8 model variant (nano = 'yolov8n.pt')
            device: Device to run inference on ('cpu' or 'cuda')
        """
        logger.info(f"Loading YOLOv8 model: {model_name} on device={device}")
        self.model = YOLO(model_name)
        self.device = device
        self.model.to(device)

    def detect_and_track(
        self,
        frame: np.ndarray,
        frame_idx: int,
        conf_threshold: float = 0.5,
    ) -> List[Tuple[int, Tuple[float, float, float, float], float]]:
        """
        Detect persons and track them across frames.

        Args:
            frame: Input frame (BGR)
            frame_idx: Frame index in video
            conf_threshold: Confidence threshold for detections

        Returns:
            List of (track_id, bbox, confidence) tuples
        """
        # Skip frames for performance
        if frame_idx % self.SKIP_FRAME_INTERVAL != 0:
            return []

        results = self.model.track(
            frame,
            persist=True,
            conf=conf_threshold,
            classes=[self.PERSON_CLASS_ID],
            verbose=False,
        )

        detections = []
        if results[0].boxes is not None:
            boxes = results[0].boxes
            for box in boxes:
                if box.id is None:
                    continue

                track_id = int(box.id.item())
                bbox = tuple(map(float, box.xyxy[0].tolist()))
                confidence = float(box.conf.item())

                detections.append((track_id, bbox, confidence))

        return detections


class DetectionPipeline:
    """Main pipeline orchestrating video processing and event generation."""

    def __init__(
        self,
        video_path: str,
        store_id: str,
        camera_id: str,
        model_name: str = "yolov8n.pt",
        device: str = "cpu",
        line_y_percent: float = 0.5,
    ):
        """
        Initialize detection pipeline.

        Args:
            video_path: Path to input video file
            store_id: Identifier for the retail store
            camera_id: Identifier for the camera
            model_name: YOLOv8 model variant
            device: Device for inference ('cpu' or 'cuda')
            line_y_percent: Horizontal line position (0.0-1.0)
        """
        self.video_path = video_path
        self.store_id = store_id
        self.camera_id = camera_id
        self.device = device

        self.detector = YOLOv8PersonDetector(model_name, device)
        
        # Will be initialized after reading first frame
        self.line_detector: Optional[LineCrossingDetector] = None
        self.line_y_percent = line_y_percent

        # Track persons and events
        self.tracked_persons: Dict[int, TrackedPerson] = {}
        self.events: List[RetailEvent] = []
        self.session_seq_counter: Dict[int, int] = defaultdict(int)

    def process_video(self) -> List[RetailEvent]:
        """
        Process entire video and generate events.

        Returns:
            List of RetailEvent objects
        """
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            logger.error(f"Failed to open video: {self.video_path}")
            return []

        frame_count = 0
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_time_ms = 1000 / fps if fps > 0 else 33.33

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Initialize line detector on first frame
                if self.line_detector is None:
                    height, width = frame.shape[:2]
                    self.line_detector = LineCrossingDetector(
                        height, width, self.line_y_percent
                    )

                # Run detection
                detections = self.detector.detect_and_track(frame, frame_count)

                # Process detections and generate events
                current_time = datetime.now(timezone.utc)
                frame_timestamp = current_time  # Can be adjusted based on frame_count

                for track_id, bbox, confidence in detections:
                    self._process_detection(
                        track_id, bbox, confidence, frame_count, frame_timestamp
                    )

                frame_count += 1
                if frame_count % 100 == 0:
                    logger.info(f"Processed {frame_count} frames")

        finally:
            cap.release()

        # Finalize tracked persons (calculate dwell times)
        self._finalize_tracking()

        logger.info(f"Generated {len(self.events)} events from video")
        return self.events

    def _process_detection(
        self,
        track_id: int,
        bbox: Tuple[float, float, float, float],
        confidence: float,
        frame_idx: int,
        frame_timestamp: datetime,
    ) -> None:
        """Process a single detection and update tracking state."""
        # Initialize tracked person if new
        if track_id not in self.tracked_persons:
            self.tracked_persons[track_id] = TrackedPerson(
                track_id=track_id,
                first_frame_idx=frame_idx,
                first_appearance_time=frame_timestamp,
                last_appearance_time=frame_timestamp,
                last_frame_idx=frame_idx,
            )
            self.session_seq_counter[track_id] = 0

        person = self.tracked_persons[track_id]
        person.last_frame_idx = frame_idx
        person.last_appearance_time = frame_timestamp
        person.frame_count += 1

        # Check for line crossing
        if self.line_detector is not None:
            crossing_result = self.line_detector.detect_crossing(
                track_id, bbox, person
            )

            if crossing_result is not None:
                event_type_str, _ = crossing_result
                self.session_seq_counter[track_id] += 1

                # Create and add event
                event = self._create_event(
                    event_type_str,
                    track_id,
                    confidence,
                    frame_timestamp,
                    self.session_seq_counter[track_id],
                )
                self.events.append(event)
                logger.debug(
                    f"Event: {event_type_str} for visitor {track_id} at {frame_timestamp}"
                )

    def _create_event(
        self,
        event_type: str,
        visitor_id: int,
        confidence: float,
        timestamp: datetime,
        session_seq: int,
    ) -> RetailEvent:
        """Create a RetailEvent from detection data."""
        metadata = EventMetadata(session_seq=session_seq)

        event = RetailEvent(
            store_id=self.store_id,
            camera_id=self.camera_id,
            visitor_id=f"VIS_{self.store_id}_{visitor_id:06d}",
            event_type=event_type,
            timestamp=timestamp,
            zone_id=None,  # Entry/Exit events don't have zone
            dwell_ms=0,  # Will be calculated on finalization
            is_staff=False,  # Can be enhanced with uniform detection
            confidence=confidence,
            metadata=metadata,
        )

        return event

    def _finalize_tracking(self) -> None:
        """Finalize tracking and calculate final dwell times."""
        for track_id, person in self.tracked_persons.items():
            dwell_ms = person.get_dwell_ms()
            logger.debug(
                f"Tracked person {track_id}: {person.frame_count} frames, dwell={dwell_ms}ms"
            )


def process_video_to_events(
    video_path: str,
    store_id: str,
    camera_id: str,
    model_name: str = "yolov8n.pt",
    device: str = "cpu",
) -> List[RetailEvent]:
    """
    Main entry point: process video and return structured events.

    Args:
        video_path: Path to input video file
        store_id: Store identifier
        camera_id: Camera identifier
        model_name: YOLOv8 model variant
        device: Inference device

    Returns:
        List of RetailEvent objects
    """
    pipeline = DetectionPipeline(
        video_path=video_path,
        store_id=store_id,
        camera_id=camera_id,
        model_name=model_name,
        device=device,
    )
    return pipeline.process_video()

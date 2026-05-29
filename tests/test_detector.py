"""
Unit tests for computer vision detection pipeline.

PROMPT: Create comprehensive tests for the CV detection engine covering:
- Line crossing detection logic (top-to-bottom, bottom-to-top)
- Tracked person state management
- Event generation from detections
- Frame skipping optimization (process every 3rd frame)
- Confidence score handling
- Dwell time calculation

CHANGES MADE: Implemented unit tests for line crossing detector, tracked person
lifecycle, and event creation. Added parametrized tests for directional crossing
and boundary conditions.
"""

import pytest
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from server.src.pipeline.detector import (
    TrackedPerson,
    LineCrossingDetector,
    YOLOv8PersonDetector,
    DetectionPipeline,
)
from server.src.schemas.events import EventType


class TestTrackedPerson:
    """Test TrackedPerson data tracking."""

    def test_tracked_person_creation(self):
        """Create a tracked person with initial state."""
        now = datetime.now(timezone.utc)
        person = TrackedPerson(
            track_id=1,
            first_frame_idx=0,
            last_frame_idx=0,
            first_appearance_time=now,
            last_appearance_time=now,
        )
        assert person.track_id == 1
        assert person.frame_count == 0
        assert person.line_crossed is False

    def test_dwell_time_calculation(self):
        """Calculate dwell time from first to last appearance."""
        now = datetime.now(timezone.utc)
        person = TrackedPerson(
            track_id=1,
            first_frame_idx=0,
            last_frame_idx=100,
            first_appearance_time=now,
            last_appearance_time=now + timedelta(seconds=5),
        )
        dwell_ms = person.get_dwell_ms()
        assert dwell_ms == 5000

    def test_dwell_time_zero_for_same_timestamp(self):
        """Dwell time is 0 if appearance at same timestamp."""
        now = datetime.now(timezone.utc)
        person = TrackedPerson(
            track_id=1,
            first_frame_idx=0,
            last_frame_idx=0,
            first_appearance_time=now,
            last_appearance_time=now,
        )
        assert person.get_dwell_ms() == 0


class TestLineCrossingDetector:
    """Test line crossing detection logic."""

    @pytest.fixture
    def detector(self):
        """Create a line detector at 50% frame height."""
        return LineCrossingDetector(frame_height=1080, frame_width=1920, line_y_percent=0.5)

    @pytest.fixture
    def tracked_person(self):
        """Create a tracked person for testing."""
        return TrackedPerson(
            track_id=1,
            first_frame_idx=0,
            last_frame_idx=0,
            first_appearance_time=datetime.now(timezone.utc),
            last_appearance_time=datetime.now(timezone.utc),
        )

    def test_line_detector_initialization(self, detector):
        """Line detector initializes at correct y position."""
        assert detector.line_y == 540  # 50% of 1080
        assert detector.frame_height == 1080
        assert detector.frame_width == 1920

    def test_no_crossing_on_first_detection(self, detector, tracked_person):
        """First detection has no previous position; no crossing."""
        bbox = (100, 200, 150, 300)  # center_y = 250
        result = detector.detect_crossing(1, bbox, tracked_person)
        assert result is None

    def test_no_crossing_if_stays_above_line(self, detector, tracked_person):
        """No crossing if person stays above threshold line."""
        # First detection
        bbox1 = (100, 100, 150, 200)  # center_y = 150 (above line at 540)
        detector.detect_crossing(1, bbox1, tracked_person)

        # Second detection (still above line)
        bbox2 = (100, 150, 150, 250)  # center_y = 200 (still above line)
        result = detector.detect_crossing(1, bbox2, tracked_person)
        assert result is None

    def test_crossing_top_to_bottom_entry(self, detector, tracked_person):
        """Detect ENTRY: crossing from top to bottom."""
        # First detection (above line)
        bbox1 = (100, 400, 150, 500)  # center_y = 450 (above line at 540)
        detector.detect_crossing(1, bbox1, tracked_person)

        # Second detection (below line)
        bbox2 = (100, 600, 150, 700)  # center_y = 650 (below line at 540)
        result = detector.detect_crossing(1, bbox2, tracked_person)

        assert result is not None
        event_type, is_new = result
        assert event_type == EventType.ENTRY.value
        assert is_new is True

    def test_crossing_bottom_to_top_exit(self, detector, tracked_person):
        """Detect EXIT: crossing from bottom to top."""
        # First detection (below line)
        bbox1 = (100, 600, 150, 700)  # center_y = 650 (below line at 540)
        detector.detect_crossing(1, bbox1, tracked_person)

        # Second detection (above line)
        bbox2 = (100, 400, 150, 500)  # center_y = 450 (above line at 540)
        result = detector.detect_crossing(1, bbox2, tracked_person)

        assert result is not None
        event_type, is_new = result
        assert event_type == EventType.EXIT.value
        assert is_new is True

    def test_no_crossing_if_stays_below_line(self, detector, tracked_person):
        """No crossing if person stays below threshold line."""
        # First detection
        bbox1 = (100, 600, 150, 700)  # center_y = 650 (below line at 540)
        detector.detect_crossing(1, bbox1, tracked_person)

        # Second detection (still below line)
        bbox2 = (100, 650, 150, 750)  # center_y = 700 (still below line)
        result = detector.detect_crossing(1, bbox2, tracked_person)
        assert result is None

    def test_line_position_custom_percent(self):
        """Line detector respects custom y position percentage."""
        detector = LineCrossingDetector(frame_height=1000, frame_width=1920, line_y_percent=0.25)
        assert detector.line_y == 250

    @pytest.mark.parametrize(
        "prev_y,curr_y,expected_event",
        [
            (450, 650, EventType.ENTRY.value),  # Top to bottom
            (650, 450, EventType.EXIT.value),   # Bottom to top
            (500, 600, EventType.ENTRY.value),  # Crossing from just above to below
            (600, 500, EventType.EXIT.value),   # Crossing from just below to above
        ],
    )
    def test_crossing_parametrized(self, detector, tracked_person, prev_y, curr_y, expected_event):
        """Parametrized test for various crossing scenarios."""
        # Initialize with first position
        bbox1 = (100, prev_y - 50, 150, prev_y + 50)
        detector.detect_crossing(1, bbox1, tracked_person)

        # Move to second position
        bbox2 = (100, curr_y - 50, 150, curr_y + 50)
        result = detector.detect_crossing(1, bbox2, tracked_person)

        assert result is not None
        event_type, _ = result
        assert event_type == expected_event


class TestYOLOv8PersonDetector:
    """Test YOLOv8 detector (mocked to avoid model download)."""

    @pytest.fixture
    def mock_detector(self):
        """Create mocked detector to avoid downloading model."""
        with patch("server.src.pipeline.detector.YOLO"):
            detector = YOLOv8PersonDetector(model_name="yolov8n.pt", device="cpu")
            detector.model = MagicMock()
            return detector

    def test_frame_skipping_interval(self, mock_detector):
        """Verify frame skipping constant is set correctly."""
        assert mock_detector.SKIP_FRAME_INTERVAL == 3

    def test_person_class_id(self, mock_detector):
        """Verify person class ID is 0."""
        assert mock_detector.PERSON_CLASS_ID == 0

    @patch("server.src.pipeline.detector.YOLO")
    def test_detector_initialization(self, mock_yolo):
        """Detector initializes with correct model and device."""
        detector = YOLOv8PersonDetector(model_name="yolov8n.pt", device="cuda")
        mock_yolo.assert_called_once_with("yolov8n.pt")
        detector.model.to.assert_called_once_with("cuda")

    def test_detect_and_track_returns_empty_on_skipped_frame(self, mock_detector):
        """Returns empty list if frame should be skipped."""
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = mock_detector.detect_and_track(frame, frame_idx=0)
        assert result == []

    def test_detect_and_track_processes_unskipped_frame(self, mock_detector):
        """Processes frame if not skipped (frame % 3 == 0)."""
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        # Mock detection results
        mock_box = MagicMock()
        mock_box.id.item.return_value = 1
        mock_box.xyxy = [[[100, 200, 150, 250]]]
        mock_box.conf.item.return_value = 0.95

        mock_results = MagicMock()
        mock_results[0].boxes = [mock_box]
        mock_detector.model.track.return_value = mock_results

        result = mock_detector.detect_and_track(frame, frame_idx=3)

        assert len(result) == 1
        track_id, bbox, confidence = result[0]
        assert track_id == 1
        assert confidence == 0.95


class TestDetectionPipeline:
    """Test detection pipeline orchestration."""

    @pytest.fixture
    def pipeline(self):
        """Create pipeline for testing."""
        with patch("server.src.pipeline.detector.YOLOv8PersonDetector"):
            pipeline = DetectionPipeline(
                video_path="/tmp/test.mp4",
                store_id="STORE_BLR_001",
                camera_id="ENTRY_CAM_01",
            )
            return pipeline

    def test_pipeline_initialization(self, pipeline):
        """Pipeline initializes with correct parameters."""
        assert pipeline.video_path == "/tmp/test.mp4"
        assert pipeline.store_id == "STORE_BLR_001"
        assert pipeline.camera_id == "ENTRY_CAM_01"
        assert len(pipeline.events) == 0
        assert len(pipeline.tracked_persons) == 0

    def test_create_event_structure(self, pipeline):
        """Created event has correct structure and values."""
        now = datetime.now(timezone.utc)
        event = pipeline._create_event(
            event_type=EventType.ENTRY.value,
            visitor_id=42,
            confidence=0.92,
            timestamp=now,
            session_seq=1,
        )

        assert event.store_id == "STORE_BLR_001"
        assert event.camera_id == "ENTRY_CAM_01"
        assert event.event_type == EventType.ENTRY.value
        assert event.is_staff is False
        assert event.confidence == 0.92
        assert event.metadata.session_seq == 1
        assert "VIS_STORE_BLR_001_000042" in event.visitor_id

    def test_process_detection_creates_tracked_person(self, pipeline):
        """Processing detection creates tracked person on first occurrence."""
        now = datetime.now(timezone.utc)
        bbox = (100, 200, 150, 300)

        pipeline._process_detection(
            track_id=1,
            bbox=bbox,
            confidence=0.85,
            frame_idx=0,
            frame_timestamp=now,
        )

        assert 1 in pipeline.tracked_persons
        person = pipeline.tracked_persons[1]
        assert person.track_id == 1
        assert person.frame_count == 1

    def test_visitor_id_generation(self, pipeline):
        """Visitor IDs are generated consistently."""
        event1 = pipeline._create_event(
            event_type=EventType.ENTRY.value,
            visitor_id=123,
            confidence=0.9,
            timestamp=datetime.now(timezone.utc),
            session_seq=1,
        )

        event2 = pipeline._create_event(
            event_type=EventType.ENTRY.value,
            visitor_id=124,
            confidence=0.9,
            timestamp=datetime.now(timezone.utc),
            session_seq=1,
        )

        assert "123" in event1.visitor_id
        assert "124" in event2.visitor_id
        assert event1.visitor_id != event2.visitor_id

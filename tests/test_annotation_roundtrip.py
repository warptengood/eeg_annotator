"""
Tests for the annotation save<->load round-trip in EEGAnnotator (JSON backend).

Strategy: construct EEGAnnotator with a fixed identity, load a real EDF via
load_edf_file on the plot widget (bypassing the file dialog), inject annotations
directly into the annotation layer, then exercise save_annotations /
load_annotations. QMessageBox modals are patched to no-ops so the suite never
blocks.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.annotation_repository import JsonFileAnnotationRepository
from src.core.user_session import UserSession
from src.views.main_window import EEGAnnotator
from src.views.plot_widget import AnnotationROI

pytestmark = pytest.mark.needs_edf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_roi(channels, start_time, stop_time, onset):
    """Return a mock AnnotationROI whose .data matches the stored dict shape."""
    mock_roi = MagicMock(spec=AnnotationROI)
    mock_roi.data = {
        "channels": list(channels),
        "start_time": start_time,
        "stop_time": stop_time,
        "onset": onset,
    }
    return mock_roi


def _inject(window, annotation_list):
    """Replace the annotation layer's items with mock ROIs."""
    window.eeg_plot_widget._annotation_layer.annotation_items = [
        _make_roi(**ann) for ann in annotation_list
    ]


def _json_path(window):
    return JsonFileAnnotationRepository().document_path(window.filename)


@pytest.fixture
def annotator(tmp_edf_copy, qtbot):
    """Create a fully initialised EEGAnnotator with a fixed identity + AV EDF."""
    user = UserSession()
    user._name = "tester"  # avoid touching real QSettings
    user._role = "labeler"
    with (
        patch("PyQt6.QtWidgets.QMessageBox.information"),
        patch("PyQt6.QtWidgets.QMessageBox.warning"),
        patch("PyQt6.QtWidgets.QMessageBox.critical"),
    ):
        window = EEGAnnotator(user_session=user)
        qtbot.addWidget(window)
        window.filename = tmp_edf_copy
        window.eeg_plot_widget.load_edf_file(
            filename=str(tmp_edf_copy),
            montage_name=window.state.montage_name,
            filter_params=window.state.filter,
        )
        yield window


# ---------------------------------------------------------------------------
# JSON document structure
# ---------------------------------------------------------------------------


def test_save_writes_single_json_document(annotator):
    channels = ["FP1-AV", "F7-AV", "T3-AV"]
    _inject(
        annotator,
        [
            {
                "channels": channels,
                "start_time": 12.34,
                "stop_time": 15.78,
                "onset": "SEIZ",
            }
        ],
    )

    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    path = _json_path(annotator)
    assert path.exists()

    doc = JsonFileAnnotationRepository().load(annotator.filename)
    assert len(doc.annotations) == 1
    ann = doc.annotations[0]
    # One annotation = one object carrying its channel list (no per-channel rows)
    assert ann.channels == channels
    assert ann.montage == annotator.state.montage_name


def test_save_stamps_author_and_submitted_status(annotator):
    _inject(
        annotator,
        [{"channels": ["FP1-AV"], "start_time": 1.5, "stop_time": 3.0, "onset": "AR"}],
    )
    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    ann = JsonFileAnnotationRepository().load(annotator.filename).annotations[0]
    assert ann.author == "tester"
    assert ann.review.status.value == "submitted"
    assert ann.id  # uuid assigned


def test_save_preserves_subsecond_times(annotator):
    _inject(
        annotator,
        [
            {
                "channels": ["FP1-AV"],
                "start_time": 3.21,
                "stop_time": 7.89,
                "onset": "BCKG",
            }
        ],
    )
    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    ann = JsonFileAnnotationRepository().load(annotator.filename).annotations[0]
    assert ann.start_time == 3.21
    assert ann.stop_time == 7.89
    assert ann.start_time != int(ann.start_time)  # not rounded


# ---------------------------------------------------------------------------
# Round-trip: save then reload
# ---------------------------------------------------------------------------


def test_roundtrip_single_annotation(annotator):
    _inject(
        annotator,
        [
            {
                "channels": ["FP1-AV"],
                "start_time": 5.5,
                "stop_time": 10.25,
                "onset": "SEIZ",
            }
        ],
    )
    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    annotator.eeg_plot_widget._annotation_layer.annotation_items = []
    with (
        patch("PyQt6.QtWidgets.QMessageBox.information"),
        patch("PyQt6.QtWidgets.QMessageBox.warning"),
    ):
        annotator.load_annotations()

    loaded = annotator.eeg_plot_widget.get_annotations()
    assert len(loaded) == 1
    assert loaded[0]["onset"] == "SEIZ"
    assert loaded[0]["start_time"] == 5.5
    assert loaded[0]["stop_time"] == 10.25
    assert "FP1-AV" in loaded[0]["channels"]


def test_roundtrip_multi_channel_kept_as_one(annotator):
    channels = ["FP1-AV", "F7-AV"]
    _inject(
        annotator,
        [{"channels": channels, "start_time": 0.5, "stop_time": 5.5, "onset": "AR"}],
    )
    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    annotator.eeg_plot_widget._annotation_layer.annotation_items = []
    with (
        patch("PyQt6.QtWidgets.QMessageBox.information"),
        patch("PyQt6.QtWidgets.QMessageBox.warning"),
    ):
        annotator.load_annotations()

    loaded = annotator.eeg_plot_widget.get_annotations()
    assert len(loaded) == 1
    assert set(loaded[0]["channels"]) == set(channels)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_save_empty_does_not_create_file(annotator):
    annotator.eeg_plot_widget._annotation_layer.annotation_items = []
    path = _json_path(annotator)
    if path.exists():
        path.unlink()

    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    assert not path.exists()


def test_load_no_file_is_noop(annotator):
    path = _json_path(annotator)
    if path.exists():
        path.unlink()
    with patch("PyQt6.QtWidgets.QMessageBox.warning"):
        annotator.load_annotations()
    assert annotator.eeg_plot_widget.get_annotations() == []

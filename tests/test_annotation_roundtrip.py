"""
Tests for the annotation save↔load round-trip in EEGAnnotator.

Strategy: construct EEGAnnotator, load a real EDF via load_edf_file on the
plot widget (bypassing the file dialog), inject annotations directly into
plot_widget.annotation_items, then call save_annotations / load_annotations.
QMessageBox modals are patched to no-ops so the test suite never blocks.
"""
import csv
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.views.main_window import EEGAnnotator
from src.views.plot_widget import EEGPlotWidget, AnnotationROI


pytestmark = pytest.mark.needs_edf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_annotation(channels, start_time, stop_time, onset):
    """Return a mock AnnotationROI whose .data matches the expected format."""
    mock_roi = MagicMock(spec=AnnotationROI)
    mock_roi.data = {
        "channels": channels,
        "start_time": start_time,
        "stop_time": stop_time,
        "onset": onset,
    }
    return mock_roi


def _inject_annotations(window, annotation_list):
    """Replace plot widget's annotation_items with mock ROIs."""
    window.eeg_plot_widget.annotation_items = [
        _make_annotation(**ann) for ann in annotation_list
    ]


@pytest.fixture
def annotator(tmp_edf_copy, qtbot):
    """Create a fully initialised EEGAnnotator with the AV EDF loaded."""
    with patch("PyQt6.QtWidgets.QMessageBox.information"), \
         patch("PyQt6.QtWidgets.QMessageBox.warning"), \
         patch("PyQt6.QtWidgets.QMessageBox.critical"):
        window = EEGAnnotator()
        qtbot.addWidget(window)
        # Load EDF without the file dialog
        window.filename = tmp_edf_copy
        window.eeg_plot_widget.load_edf_file(
            filename=str(tmp_edf_copy),
            montage_name=window.state.montage_name,
            filter_params=window.state.filter,
        )
        yield window


# ---------------------------------------------------------------------------
# CSV structure tests
# ---------------------------------------------------------------------------

def test_save_produces_one_row_per_channel(annotator, tmp_path):
    channels = ["FP1-AV", "F7-AV", "T3-AV"]
    _inject_annotations(annotator, [
        {"channels": channels, "start_time": 0, "stop_time": 5, "onset": "SEIZ"},
    ])

    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    montage_slug = annotator.state.montage_name.replace(" ", "_")
    csv_path = annotator.filename.parent / f"{annotator.filename.stem}_{montage_slug}.csv"
    assert csv_path.exists()

    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(channels)
    row_channels = [r["channels"] for r in rows]
    assert set(row_channels) == set(channels)


def test_save_correct_columns_and_values(annotator):
    _inject_annotations(annotator, [
        {"channels": ["FP1-AV"], "start_time": 10, "stop_time": 20, "onset": "AR"},
    ])

    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    montage_slug = annotator.state.montage_name.replace(" ", "_")
    csv_path = annotator.filename.parent / f"{annotator.filename.stem}_{montage_slug}.csv"
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 1
    assert rows[0]["channels"] == "FP1-AV"
    assert int(rows[0]["start_time"]) == 10
    assert int(rows[0]["stop_time"]) == 20
    assert rows[0]["onset"] == "AR"


def test_filename_derivation(annotator):
    _inject_annotations(annotator, [
        {"channels": ["FP1-AV"], "start_time": 0, "stop_time": 5, "onset": "BCKG"},
    ])

    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    expected_name = (
        f"{annotator.filename.stem}_"
        f"{annotator.state.montage_name.replace(' ', '_')}.csv"
    )
    csv_path = annotator.filename.parent / expected_name
    assert csv_path.exists()


# ---------------------------------------------------------------------------
# Round-trip: save then reload
# ---------------------------------------------------------------------------

def test_roundtrip_single_channel(annotator):
    original = [
        {"channels": ["FP1-AV"], "start_time": 5, "stop_time": 10, "onset": "SEIZ"},
    ]
    _inject_annotations(annotator, original)

    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    # Wipe in-memory annotations and reload from CSV
    annotator.eeg_plot_widget.annotation_items = []
    with patch("PyQt6.QtWidgets.QMessageBox.information"), \
         patch("PyQt6.QtWidgets.QMessageBox.warning"):
        annotator.load_annotations()

    loaded = annotator.eeg_plot_widget.get_annotations()
    assert len(loaded) == 1
    assert loaded[0]["onset"] == "SEIZ"
    assert loaded[0]["start_time"] == 5
    assert loaded[0]["stop_time"] == 10
    assert "FP1-AV" in loaded[0]["channels"]


def test_roundtrip_multi_channel_regrouped(annotator):
    channels = ["FP1-AV", "F7-AV"]
    original = [
        {"channels": channels, "start_time": 0, "stop_time": 5, "onset": "AR"},
    ]
    _inject_annotations(annotator, original)

    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    annotator.eeg_plot_widget.annotation_items = []
    with patch("PyQt6.QtWidgets.QMessageBox.information"), \
         patch("PyQt6.QtWidgets.QMessageBox.warning"):
        annotator.load_annotations()

    loaded = annotator.eeg_plot_widget.get_annotations()
    # Two channels should be merged back into one annotation
    assert len(loaded) == 1
    assert set(loaded[0]["channels"]) == set(channels)


def test_roundtrip_multiple_annotations(annotator):
    original = [
        {"channels": ["FP1-AV"], "start_time": 0, "stop_time": 5, "onset": "SEIZ"},
        {"channels": ["F7-AV", "T3-AV"], "start_time": 10, "stop_time": 15, "onset": "AR"},
    ]
    _inject_annotations(annotator, original)

    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    annotator.eeg_plot_widget.annotation_items = []
    with patch("PyQt6.QtWidgets.QMessageBox.information"), \
         patch("PyQt6.QtWidgets.QMessageBox.warning"):
        annotator.load_annotations()

    loaded = annotator.eeg_plot_widget.get_annotations()
    assert len(loaded) == 2

    onsets = {a["onset"] for a in loaded}
    assert onsets == {"SEIZ", "AR"}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_save_empty_annotations_does_not_create_file(annotator):
    annotator.eeg_plot_widget.annotation_items = []
    montage_slug = annotator.state.montage_name.replace(" ", "_")
    csv_path = annotator.filename.parent / f"{annotator.filename.stem}_{montage_slug}.csv"
    if csv_path.exists():
        csv_path.unlink()

    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    assert not csv_path.exists()


def test_load_annotations_no_file_is_noop(annotator):
    montage_slug = annotator.state.montage_name.replace(" ", "_")
    csv_path = annotator.filename.parent / f"{annotator.filename.stem}_{montage_slug}.csv"
    if csv_path.exists():
        csv_path.unlink()

    # Should not raise
    with patch("PyQt6.QtWidgets.QMessageBox.warning"):
        annotator.load_annotations()


# ---------------------------------------------------------------------------
# Integer rounding — pins current behaviour (documents the known precision loss)
# ---------------------------------------------------------------------------

def test_start_stop_times_are_integers_in_csv(annotator):
    """Annotation times are rounded to whole seconds when persisted."""
    _inject_annotations(annotator, [
        {"channels": ["FP1-AV"], "start_time": 3, "stop_time": 7, "onset": "BCKG"},
    ])

    with patch("PyQt6.QtWidgets.QMessageBox.information"):
        annotator.save_annotations()

    montage_slug = annotator.state.montage_name.replace(" ", "_")
    csv_path = annotator.filename.parent / f"{annotator.filename.stem}_{montage_slug}.csv"
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    # Values should be whole-number representable
    for row in rows:
        assert float(row["start_time"]) == int(float(row["start_time"]))
        assert float(row["stop_time"]) == int(float(row["stop_time"]))

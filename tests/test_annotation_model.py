"""Tests for the Pydantic annotation models and their JSON (de)serialization."""

import pytest
from pydantic import ValidationError

from src.domain.annotation import (
    Annotation,
    AnnotationDocument,
    ReviewStatus,
)


def _ann(**overrides):
    base = dict(
        montage="AVERAGE",
        channels=["FP1-AV", "F7-AV"],
        start_time=12.34,
        stop_time=15.78,
        onset="SEIZ",
    )
    base.update(overrides)
    return Annotation(**base)


# ---------------------------------------------------------------------------
# Defaults / tolerance
# ---------------------------------------------------------------------------


def test_missing_id_review_author_get_defaults():
    a = _ann()
    assert a.id  # auto-generated uuid
    assert a.author is None
    assert a.review.status == ReviewStatus.DRAFT
    assert a.review.reviewer is None


def test_unique_ids_per_instance():
    assert _ann().id != _ann().id


# ---------------------------------------------------------------------------
# Float precision round-trip (no rounding anywhere)
# ---------------------------------------------------------------------------


def test_json_roundtrip_preserves_subsecond_times():
    a = _ann(start_time=12.34, stop_time=15.78)
    restored = Annotation.model_validate_json(a.model_dump_json())
    assert restored.start_time == 12.34
    assert restored.stop_time == 15.78
    # explicitly non-integer
    assert restored.start_time != int(restored.start_time)


def test_document_roundtrip():
    doc = AnnotationDocument(
        edf_file="p1.edf",
        annotations=[_ann(), _ann(montage="BIPOLAR", channels=["FP1-F7"])],
    )
    restored = AnnotationDocument.model_validate_json(doc.model_dump_json())
    assert len(restored.annotations) == 2
    assert restored.edf_file == "p1.edf"


# ---------------------------------------------------------------------------
# Validation / strictness
# ---------------------------------------------------------------------------


def test_stop_must_exceed_start():
    with pytest.raises(ValidationError):
        _ann(start_time=5.0, stop_time=3.0)


def test_bad_enum_value_rejected():
    payload = (
        '{"annotations":[{"montage":"X","channels":["a"],'
        '"start_time":0,"stop_time":1,"onset":"AR",'
        '"review":{"status":"bogus"}}]}'
    )
    with pytest.raises(ValidationError):
        AnnotationDocument.model_validate_json(payload)


def test_extra_keys_ignored_for_forward_compat():
    payload = (
        '{"montage":"X","channels":["a"],"start_time":0,"stop_time":1,'
        '"onset":"AR","future_field":123}'
    )
    a = Annotation.model_validate_json(payload)
    assert not hasattr(a, "future_field")


# ---------------------------------------------------------------------------
# Document montage helpers (merge-on-save primitive)
# ---------------------------------------------------------------------------


def test_for_montage_filters():
    doc = AnnotationDocument(
        annotations=[
            _ann(montage="AVERAGE"),
            _ann(montage="BIPOLAR", channels=["FP1-F7"]),
        ]
    )
    assert len(doc.for_montage("AVERAGE")) == 1
    assert len(doc.for_montage("BIPOLAR")) == 1


def test_replace_montage_keeps_other_montages():
    avg = _ann(montage="AVERAGE")
    bip = _ann(montage="BIPOLAR", channels=["FP1-F7"])
    doc = AnnotationDocument(annotations=[avg, bip])

    new_avg = _ann(montage="AVERAGE", onset="AR")
    doc.replace_montage("AVERAGE", [new_avg])

    assert len(doc.for_montage("BIPOLAR")) == 1  # untouched
    avg_now = doc.for_montage("AVERAGE")
    assert len(avg_now) == 1 and avg_now[0].onset == "AR"

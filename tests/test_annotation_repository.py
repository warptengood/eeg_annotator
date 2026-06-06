"""Tests for the JSON file annotation repository."""

import pytest
from pydantic import ValidationError

from src.core.annotation_repository import JsonFileAnnotationRepository
from src.domain.annotation import (
    ANNOTATION_FILE_SUFFIX,
    Annotation,
    AnnotationDocument,
)


@pytest.fixture
def repo():
    return JsonFileAnnotationRepository()


@pytest.fixture
def edf_path(tmp_path):
    p = tmp_path / "patient001.edf"
    p.write_bytes(b"not a real edf")
    return p


def _ann(montage="AVERAGE", **overrides):
    base = dict(
        montage=montage,
        channels=["FP1-AV"],
        start_time=12.34,
        stop_time=15.78,
        onset="SEIZ",
    )
    base.update(overrides)
    return Annotation(**base)


def test_document_path_uses_suffix(repo, edf_path):
    path = repo.document_path(edf_path)
    assert path.name == "patient001" + ANNOTATION_FILE_SUFFIX
    assert path.parent == edf_path.parent


def test_load_missing_returns_empty_document(repo, edf_path):
    doc = repo.load(edf_path)
    assert isinstance(doc, AnnotationDocument)
    assert doc.annotations == []
    assert doc.edf_file == "patient001.edf"


def test_save_then_load_roundtrip_preserves_floats(repo, edf_path):
    doc = AnnotationDocument(edf_file=edf_path.name, annotations=[_ann()])
    repo.save(edf_path, doc)

    loaded = repo.load(edf_path)
    assert len(loaded.annotations) == 1
    assert loaded.annotations[0].start_time == 12.34
    assert loaded.annotations[0].stop_time == 15.78


def test_save_is_pretty_printed(repo, edf_path):
    repo.save(edf_path, AnnotationDocument(annotations=[_ann()]))
    text = repo.document_path(edf_path).read_text()
    assert "\n" in text and "  " in text  # indented JSON


def test_merge_save_keeps_other_montages(repo, edf_path):
    doc = AnnotationDocument(
        annotations=[_ann("AVERAGE"), _ann("BIPOLAR", channels=["FP1-F7"])]
    )
    repo.save(edf_path, doc)

    reloaded = repo.load(edf_path)
    reloaded.replace_montage("AVERAGE", [_ann("AVERAGE", onset="AR")])
    repo.save(edf_path, reloaded)

    final = repo.load(edf_path)
    assert len(final.for_montage("BIPOLAR")) == 1
    assert final.for_montage("AVERAGE")[0].onset == "AR"


def test_load_malformed_json_raises(repo, edf_path):
    repo.document_path(edf_path).write_text('{"annotations": [{"montage": 5}]}')
    with pytest.raises(ValidationError):
        repo.load(edf_path)

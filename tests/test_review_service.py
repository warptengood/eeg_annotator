"""Tests for the annotation review-lifecycle transition rules."""

import pytest

from src.domain.annotation import Annotation, ReviewStatus
from src.domain.review_service import ReviewService


@pytest.fixture
def service():
    return ReviewService()


def _ann(**overrides):
    base = dict(
        montage="AVERAGE",
        channels=["FP1-AV"],
        start_time=1.0,
        stop_time=2.0,
        onset="SEIZ",
    )
    base.update(overrides)
    return Annotation(**base)


def test_stamp_new_is_authored_draft(service):
    a = service.stamp_new(
        author="aigerim",
        montage="AVERAGE",
        channels=["FP1-AV", "F7-AV"],
        start_time=12.34,
        stop_time=15.78,
        onset="SEIZ",
    )
    assert a.author == "aigerim"
    assert a.review.status == ReviewStatus.DRAFT
    assert a.created_at and a.modified_at
    assert a.start_time == 12.34  # no rounding


def test_mark_submitted_advances_draft_and_needs_changes(service):
    draft = _ann()
    needs = _ann()
    needs.review.status = ReviewStatus.NEEDS_CHANGES
    service.mark_submitted([draft, needs], "aigerim")
    assert draft.review.status == ReviewStatus.SUBMITTED
    assert needs.review.status == ReviewStatus.SUBMITTED


def test_mark_submitted_leaves_reviewed_alone(service):
    verified = _ann()
    verified.review.status = ReviewStatus.VERIFIED
    service.mark_submitted([verified], "aigerim")
    assert verified.review.status == ReviewStatus.VERIFIED


def test_mark_submitted_fills_missing_author(service):
    a = _ann()
    assert a.author is None
    service.mark_submitted([a], "aigerim")
    assert a.author == "aigerim"


def test_apply_review_stamps_reviewer(service):
    a = _ann()
    a.review.status = ReviewStatus.SUBMITTED
    service.apply_review(a, ReviewStatus.VERIFIED, "dr_smith", "looks good")
    assert a.review.status == ReviewStatus.VERIFIED
    assert a.review.reviewer == "dr_smith"
    assert a.review.reviewed_at is not None
    assert a.review.note == "looks good"


def test_apply_review_rejects_non_verdict(service):
    with pytest.raises(ValueError):
        service.apply_review(_ann(), ReviewStatus.DRAFT, "dr_smith")


def test_editing_reviewed_annotation_resets_to_draft(service):
    a = _ann()
    service.apply_review(a, ReviewStatus.REJECTED, "dr_smith", "wrong onset")
    service.touch(a)
    assert a.review.status == ReviewStatus.DRAFT
    assert a.review.reviewer is None
    assert a.review.reviewed_at is None
    # note kept so the labeler can address the feedback
    assert a.review.note == "wrong onset"


def test_touch_only_bumps_modified_for_draft(service):
    a = _ann()
    a.modified_at = "old"
    service.touch(a)
    assert a.modified_at != "old"
    assert a.review.status == ReviewStatus.DRAFT

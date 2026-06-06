# Copyright (C) 2024-2026 Kenes Yerassyl
# This file is part of Ziyatron EEG Annotator.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""Annotation review-lifecycle rules (pure Python, no PyQt).

All status transitions live here so the Qt layer never encodes business rules.
Methods mutate the passed ``Annotation`` in place and also return it for
convenience.
"""

from datetime import datetime, timezone
from typing import Iterable, List

from src.domain.annotation import Annotation, Review, ReviewStatus

# Statuses that mean "an expert has already acted on this annotation".
_REVIEWED = {ReviewStatus.VERIFIED, ReviewStatus.REJECTED, ReviewStatus.NEEDS_CHANGES}

# Verdicts an expert may apply.
REVIEW_VERDICTS = (
    ReviewStatus.VERIFIED,
    ReviewStatus.REJECTED,
    ReviewStatus.NEEDS_CHANGES,
)


def now_iso() -> str:
    """Current UTC time as ISO 8601 with a trailing ``Z`` (second precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ReviewService:
    """Applies authorship and review-status transitions to annotations."""

    def stamp_new(
        self,
        *,
        author: str,
        montage: str,
        channels: List[str],
        start_time: float,
        stop_time: float,
        onset: str,
    ) -> Annotation:
        """Build a freshly authored annotation in the ``DRAFT`` state."""
        ts = now_iso()
        return Annotation(
            montage=montage,
            channels=list(channels),
            start_time=start_time,
            stop_time=stop_time,
            onset=onset,
            author=author,
            created_at=ts,
            modified_at=ts,
            review=Review(status=ReviewStatus.DRAFT),
        )

    def mark_submitted(self, annotations: Iterable[Annotation], author: str) -> None:
        """On save, advance the labeler's own work to ``SUBMITTED``.

        Only ``DRAFT``/``NEEDS_CHANGES`` annotations move; already-reviewed
        (``VERIFIED``/``REJECTED``) ones are left untouched. Fills in a missing
        author so legacy/imported rows gain provenance on first save.
        """
        for ann in annotations:
            if ann.author is None:
                ann.author = author
            if ann.review.status in (ReviewStatus.DRAFT, ReviewStatus.NEEDS_CHANGES):
                ann.review.status = ReviewStatus.SUBMITTED

    def apply_review(
        self,
        annotation: Annotation,
        verdict: ReviewStatus,
        reviewer: str,
        note: str = "",
    ) -> Annotation:
        """Record an expert verdict (verified / rejected / needs-changes)."""
        if verdict not in REVIEW_VERDICTS:
            raise ValueError(f"{verdict!r} is not a review verdict")
        annotation.review.status = verdict
        annotation.review.reviewer = reviewer
        annotation.review.reviewed_at = now_iso()
        annotation.review.note = note
        return annotation

    def touch(self, annotation: Annotation) -> Annotation:
        """Mark an annotation edited.

        If a labeler edits an annotation an expert had already acted on, the
        verdict no longer applies, so it drops back to ``DRAFT`` (clearing the
        reviewer stamp but keeping the note so the labeler can address it).
        """
        annotation.modified_at = now_iso()
        if annotation.review.status in _REVIEWED:
            annotation.review.status = ReviewStatus.DRAFT
            annotation.review.reviewer = None
            annotation.review.reviewed_at = None
        return annotation

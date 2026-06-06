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

"""Pydantic models for EEG annotations and their review lifecycle.

The on-disk format is one JSON document per EDF file (``<stem>.ziyatron.json``):
a flat list of annotations, each tagged with the montage it was drawn under and
carrying provenance + review metadata. Using Pydantic means a malformed or
hand-edited file is rejected with a clear ``ValidationError`` at load time --
the same validation a future backend reuses to verify incoming files.
"""

from enum import Enum
from typing import List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1

# Filename suffix for the per-EDF annotation document. Distinct from the legacy
# ``<stem>_<montage>.csv`` so the two never collide.
ANNOTATION_FILE_SUFFIX = ".ziyatron.json"


class ReviewStatus(str, Enum):
    """Lifecycle state of a single annotation."""

    DRAFT = "draft"  # created, not yet saved/submitted
    SUBMITTED = "submitted"  # labeler saved; awaiting expert review
    VERIFIED = "verified"  # expert approved
    REJECTED = "rejected"  # expert rejected
    NEEDS_CHANGES = "needs_changes"  # expert wants edits, back to the labeler


class Review(BaseModel):
    """Expert verdict on an annotation. Defaults represent 'not yet reviewed'."""

    model_config = ConfigDict(extra="ignore")

    status: ReviewStatus = ReviewStatus.DRAFT
    reviewer: Optional[str] = None
    reviewed_at: Optional[str] = None  # ISO 8601 UTC
    note: str = ""


class Annotation(BaseModel):
    """A single labeled region: a time span across one or more channels.

    ``start_time``/``stop_time`` are floats in seconds (sub-second precision).
    ``channels`` is the discrete set of montage channels the region covers.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid4()))
    montage: str
    channels: List[str]
    start_time: float
    stop_time: float
    onset: str  # diagnosis label
    author: Optional[str] = None
    created_at: Optional[str] = None  # ISO 8601 UTC
    modified_at: Optional[str] = None  # ISO 8601 UTC
    review: Review = Field(default_factory=Review)

    @field_validator("stop_time")
    @classmethod
    def _stop_after_start(cls, v: float, info) -> float:
        start = info.data.get("start_time")
        if start is not None and v <= start:
            raise ValueError("stop_time must be greater than start_time")
        return v


class AnnotationDocument(BaseModel):
    """All annotations for a single EDF file, across every montage."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = SCHEMA_VERSION
    edf_file: str = ""
    annotations: List[Annotation] = Field(default_factory=list)

    def for_montage(self, montage: str) -> List[Annotation]:
        """Return annotations belonging to ``montage`` (preserving order)."""
        return [a for a in self.annotations if a.montage == montage]

    def replace_montage(self, montage: str, annotations: List[Annotation]) -> None:
        """Swap out this montage's annotations, leaving other montages intact.

        This is the merge-on-save primitive: saving one montage must never drop
        annotations belonging to another montage already in the document.
        """
        kept = [a for a in self.annotations if a.montage != montage]
        self.annotations = kept + list(annotations)

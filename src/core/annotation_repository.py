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

"""Annotation persistence behind a narrow interface.

The UI depends only on the ``AnnotationRepository`` protocol, so the JSON-file
backend used today can later be swapped for an HTTP client talking to a backend
engine without touching any Qt code. This module imports no PyQt.
"""

import logging
from pathlib import Path
from typing import Protocol

from src.domain.annotation import ANNOTATION_FILE_SUFFIX, AnnotationDocument

logger = logging.getLogger(__name__)


class AnnotationRepository(Protocol):
    """Load/save the full annotation document for a given EDF file."""

    def load(self, edf_path: Path) -> AnnotationDocument: ...

    def save(self, edf_path: Path, doc: AnnotationDocument) -> None: ...


class JsonFileAnnotationRepository:
    """Stores one ``<stem>.ziyatron.json`` document next to each EDF file."""

    def document_path(self, edf_path: Path) -> Path:
        edf_path = Path(edf_path)
        return edf_path.with_name(edf_path.stem + ANNOTATION_FILE_SUFFIX)

    def load(self, edf_path: Path) -> AnnotationDocument:
        """Return the stored document, or an empty one if none exists.

        Raises ``pydantic.ValidationError`` if the file exists but is malformed,
        so the caller can surface a clear error instead of silently losing data.
        """
        edf_path = Path(edf_path)
        path = self.document_path(edf_path)
        if not path.exists():
            return AnnotationDocument(edf_file=edf_path.name)

        text = path.read_text(encoding="utf-8")
        doc = AnnotationDocument.model_validate_json(text)
        logger.info("Loaded %d annotations from %s", len(doc.annotations), path)
        return doc

    def save(self, edf_path: Path, doc: AnnotationDocument) -> None:
        path = self.document_path(Path(edf_path))
        path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
        logger.info("Saved %d annotations to %s", len(doc.annotations), path)

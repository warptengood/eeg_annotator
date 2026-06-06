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

"""Expert review dock: verify / reject / request-changes on a selected label."""

import logging
from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.domain.annotation import ReviewStatus

logger = logging.getLogger(__name__)


class ReviewPanel(QDockWidget):
    """Shows the selected annotation's provenance and review controls.

    Visible only to experts in review mode (main window manages docking). It
    reads/writes nothing itself: verdicts are forwarded to ``apply_review``,
    which routes through the plot widget into the domain ReviewService.
    """

    def __init__(self, state, apply_review: Callable, parent=None):
        super().__init__("Review", parent)
        self._state = state
        self._apply_review = apply_review
        self._roi = None  # currently selected AnnotationROI

        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)

        self._author_lbl = QLabel("—")
        self._created_lbl = QLabel("—")
        self._status_lbl = QLabel("—")
        self._reviewer_lbl = QLabel("—")
        self._note_edit = QTextEdit()
        self._note_edit.setPlaceholderText("Reviewer note (optional)…")

        self._verify_btn = QPushButton("Verify")
        self._verify_btn.clicked.connect(lambda: self._submit(ReviewStatus.VERIFIED))
        self._reject_btn = QPushButton("Reject")
        self._reject_btn.clicked.connect(lambda: self._submit(ReviewStatus.REJECTED))
        self._changes_btn = QPushButton("Needs changes")
        self._changes_btn.clicked.connect(
            lambda: self._submit(ReviewStatus.NEEDS_CHANGES)
        )

        form = QVBoxLayout()
        for caption, widget in (
            ("Author:", self._author_lbl),
            ("Created:", self._created_lbl),
            ("Status:", self._status_lbl),
            ("Reviewer:", self._reviewer_lbl),
        ):
            row = QHBoxLayout()
            cap = QLabel(caption)
            cap.setFixedWidth(70)
            row.addWidget(cap)
            row.addWidget(widget, 1)
            form.addLayout(row)

        form.addWidget(QLabel("Note:"))
        form.addWidget(self._note_edit, 1)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._verify_btn)
        btn_row.addWidget(self._reject_btn)
        btn_row.addWidget(self._changes_btn)
        form.addLayout(btn_row)

        container = QWidget()
        container.setLayout(form)
        self.setWidget(container)

        self._set_enabled(False)

        if self._state is not None:
            self._state.annotation_selected.connect(self.set_annotation)

    def _set_enabled(self, enabled: bool):
        self._verify_btn.setEnabled(enabled)
        self._reject_btn.setEnabled(enabled)
        self._changes_btn.setEnabled(enabled)
        self._note_edit.setEnabled(enabled)

    def set_annotation(self, roi: Optional[object]):
        """Populate the panel from the selected ROI (or clear it for None)."""
        self._roi = roi
        if roi is None:
            self._author_lbl.setText("—")
            self._created_lbl.setText("—")
            self._status_lbl.setText("—")
            self._reviewer_lbl.setText("—")
            self._note_edit.clear()
            self._set_enabled(False)
            return

        data = roi.data
        review = data.get("review") or {}
        self._author_lbl.setText(str(data.get("author") or "unknown"))
        self._created_lbl.setText(str(data.get("created_at") or "—"))
        self._status_lbl.setText(str(review.get("status") or "draft"))
        self._reviewer_lbl.setText(str(review.get("reviewer") or "—"))
        self._note_edit.setPlainText(str(review.get("note") or ""))
        self._set_enabled(True)

    def _submit(self, verdict: ReviewStatus):
        if self._roi is None:
            return
        note = self._note_edit.toPlainText().strip()
        self._apply_review(self._roi, verdict, note)
        # Reflect the freshly applied verdict back into the panel.
        self.set_annotation(self._roi)

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


import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QMainWindow, QMessageBox, QWidget

from src.core.annotation_repository import JsonFileAnnotationRepository
from src.core.user_session import UserSession
from src.domain.annotation import Annotation
from src.domain.review_service import ReviewService
from src.models.app_state import AppState
from src.views.control_toolbar import ControlToolBar
from src.views.plot_widget import EEGPlotWidget
from src.views.review_panel import ReviewPanel

logger = logging.getLogger(__name__)


class EEGAnnotator(QMainWindow):
    """Main window for Ziyatron EEG annotation application.

    Integrates:
    - PyQtGraph plot widget for efficient rendering
    - EEGDataStreamer for lazy loading
    - Control toolbar for user interactions
    - JSON-based annotation persistence with review metadata
    """

    def __init__(self, user_session: UserSession = None):
        super().__init__()
        self.setWindowTitle("Ziyatron EEG Annotator v2.0")
        self.resize(1400, 800)

        self.filename = (
            None  # Set by open_file(); guards on_settings_changed / on_scale_changed
        )

        # Domain / persistence layer (no PyQt dependency)
        self.user_session = user_session or UserSession()
        self.review_service = ReviewService()
        self.annotation_repo = JsonFileAnnotationRepository()

        # Application state
        self.state = AppState()
        self.state.montage_changed.connect(self.on_montage_changed)
        self.state.filter_changed.connect(self.on_filter_changed)
        self.state.scale_changed.connect(self.on_scale_changed)
        self.state.review_mode_changed.connect(self.on_review_mode_changed)

        # Create UI components
        self.control_toolbar = ControlToolBar(self.state, self.user_session)
        self.control_toolbar.open_file_clicked.connect(self.open_file)
        self.control_toolbar.save_clicked.connect(self.save_annotations)

        # Keyboard shortcut: Ctrl+S (Cmd+S on Mac)
        save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        save_shortcut.activated.connect(self.save_annotations)

        self.eeg_plot_widget = EEGPlotWidget(
            self.state,
            review_service=self.review_service,
            user_session=self.user_session,
        )

        # Expert review dock (hidden until an expert enables review mode)
        self.review_panel = ReviewPanel(self.state, self.eeg_plot_widget.apply_review)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.review_panel)
        self.review_panel.hide()

        # Add toolbar
        self.addToolBar(self.control_toolbar)

        # Create menu bar
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")

        open_action = QAction("Open EDF", self)
        open_action.triggered.connect(self.open_file)
        open_action.setShortcut("Ctrl+O")
        file_menu.addAction(open_action)

        save_action = QAction("Save Annotations", self)
        save_action.triggered.connect(self.save_annotations)
        save_action.setShortcut("Ctrl+S")
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        exit_action.setShortcut("Ctrl+Q")
        file_menu.addAction(exit_action)

        # Central widget layout
        layout = QHBoxLayout()
        layout.addWidget(self.eeg_plot_widget)

        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        # State variables
        self.filename: Path = None

    def open_file(self):
        """Open EDF file dialog and load file."""
        file_filters = "EDF Files (*.edf *.EDF)"

        filename, _ = QFileDialog.getOpenFileName(
            self, "Open EDF File", "", file_filters
        )

        if not filename:
            return

        self.filename = Path(filename)

        try:
            # Load EDF file with current montage and filter settings
            self.eeg_plot_widget.load_edf_file(
                filename=str(self.filename),
                montage_name=self.state.montage_name,
                filter_params=self.state.filter,
            )

            # Load existing annotations if available
            self.load_annotations()

            # Enable controls
            metadata = self.eeg_plot_widget.data_streamer.get_metadata()
            signal_duration = metadata["duration"]
            s_freq = metadata["sfreq"]

            self.control_toolbar.label_btn.setEnabled(True)
            self.control_toolbar.save_btn.setEnabled(True)
            self.control_toolbar.show_controls(signal_duration, s_freq)

            logger.info(f"Loaded file: {self.filename}")

        except Exception as e:
            logger.error(f"Failed to open file {filename}: {e}")
            QMessageBox.critical(self, "Error", f"Failed to open EDF file:\n{e}")

    def load_annotations(self):
        """Load annotations for the current montage from the JSON document."""
        if not self.filename:
            return

        try:
            doc = self.annotation_repo.load(self.filename)
        except Exception as e:
            logger.error(f"Failed to load annotations: {e}")
            QMessageBox.warning(
                self, "Warning", f"Failed to load existing annotations:\n{e}"
            )
            return

        montage = self.state.montage_name
        annotations = [a.model_dump() for a in doc.for_montage(montage)]
        self.eeg_plot_widget.load_annotations(annotations)
        logger.info(f"Loaded {len(annotations)} annotations for montage '{montage}'")

    def _save_to_disk(self, montage_name: str) -> int | None:
        """Merge the widget's annotations for ``montage_name`` into the JSON doc.

        Saving one montage never drops another montage's annotations: we load
        the full document, replace only this montage's slice, and write it back.
        The labeler's own draft/needs-changes annotations advance to SUBMITTED.

        Returns the number of annotations saved for this montage, or ``None``
        when there was nothing to persist (no annotations in memory and none
        already saved for this montage), so the save is skipped entirely.
        """
        doc = self.annotation_repo.load(self.filename)
        dicts = self.eeg_plot_widget.get_annotations()
        if not dicts and not doc.for_montage(montage_name):
            return None

        models = []
        for d in dicts:
            d["montage"] = montage_name
            models.append(Annotation(**d))

        self.review_service.mark_submitted(models, self.user_session.name)

        # Sync status/author changes back into the live ROI dicts so the
        # on-screen colors reflect the new (submitted) state.
        for d, m in zip(dicts, models):
            d.update(m.model_dump())
        self.eeg_plot_widget.refresh_annotation_styles()

        doc.edf_file = self.filename.name
        doc.replace_montage(montage_name, models)
        self.annotation_repo.save(self.filename, doc)
        self.eeg_plot_widget.mark_annotations_saved()
        return len(models)

    def save_annotations(self):
        """Save current-montage annotations to the JSON document (interactive)."""
        if not self.filename:
            QMessageBox.warning(self, "Warning", "No file is currently open")
            return

        montage = self.state.montage_name
        try:
            count = self._save_to_disk(montage)
        except Exception as e:
            logger.error(f"Failed to save annotations: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save annotations:\n{e}")
            return

        if count is None:
            QMessageBox.information(self, "Info", "No annotations to save")
            return

        logger.info(f"Saved {count} annotations for montage '{montage}'")
        path = self.annotation_repo.document_path(self.filename)
        QMessageBox.information(self, "Success", f"Annotations saved to:\n{path.name}")

    def on_montage_changed(self):
        """Handle montage switch: prompt to save if there are unsaved annotations."""
        if not self.filename:
            return

        if self.eeg_plot_widget.is_annotations_dirty:
            previous_montage = self.eeg_plot_widget.current_montage
            reply = QMessageBox.question(
                self,
                "Unsaved Annotations",
                f"You have unsaved annotations for montage '{previous_montage}'.\n\n"
                "Save them before switching montage?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )

            if reply == QMessageBox.StandardButton.Cancel:
                # Revert state and combobox — no reload
                self.state.revert_montage(previous_montage)
                self.control_toolbar.select_montage.blockSignals(True)
                self.control_toolbar.select_montage.setCurrentText(previous_montage)
                self.control_toolbar.select_montage.blockSignals(False)
                return

            if reply == QMessageBox.StandardButton.Save:
                self._save_annotations_silent()

        self._reload_with_current_settings()

    def on_filter_changed(self):
        """Handle filter change: reload without annotation guard (channels unchanged)."""
        if not self.filename:
            return
        self._reload_with_current_settings()

    def _save_annotations_silent(self):
        """Save annotations without dialogs (used when switching montage).

        Uses the widget's current_montage (the montage being switched away
        from), since self.state already holds the newly selected montage.

        Persists even when the montage is now empty: deleting every annotation
        and saving must clear that montage's slice on disk. We only skip when
        there is nothing in memory AND nothing already saved for the montage.
        """
        montage = self.eeg_plot_widget.current_montage
        try:
            count = self._save_to_disk(montage)
            if count is not None:
                logger.info(f"Auto-saved {count} annotations")
        except Exception as e:
            logger.error(f"Failed to auto-save annotations: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save annotations:\n{e}")

    def on_review_mode_changed(self, enabled: bool):
        """Show/hide the expert review dock when review mode is toggled."""
        self.review_panel.setVisible(enabled)

    def _reload_with_current_settings(self):
        """Reload EEG data and annotations for the current montage/filter."""
        try:
            saved_range = self.eeg_plot_widget.view_range

            # Clear annotations before reloading so no stale ROIs survive
            self.eeg_plot_widget.clear_annotations()

            self.eeg_plot_widget.data_streamer.clear_cache()

            self.eeg_plot_widget.load_edf_file(
                filename=str(self.filename),
                montage_name=self.state.montage_name,
                filter_params=self.state.filter,
            )

            if saved_range is not None:
                start_time, duration = saved_range
                self.eeg_plot_widget.set_view_range(start_time, duration)

            self.load_annotations()

            logger.info(
                f"Reloaded with montage={self.state.montage_name}, filter={self.state.filter}"
            )

        except Exception as e:
            logger.error(f"Failed to reload with new settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to apply new settings:\n{e}")

    def on_scale_changed(self):
        """Update scale factor when scale changes."""
        if not self.filename:
            return

        scale_uv_per_mm = self.state.scale

        # Use plot widget's method to update scale properly
        # This updates scale_factor, Y-axis labels, Y-axis range, and reloads plot
        self.eeg_plot_widget.set_scale_factor(scale_uv_per_mm)

    def closeEvent(self, event):
        """Handle window close event."""
        if self.eeg_plot_widget.data_streamer:
            self.eeg_plot_widget.data_streamer.close()

        logger.info("Application closed")
        event.accept()

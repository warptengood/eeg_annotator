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


from pathlib import Path
import logging

import pandas as pd
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QWidget,
    QMessageBox,
)

from src.views.control_toolbar import ControlToolBar
from src.views.plot_widget import EEGPlotWidget
from src.models.app_state import AppState


logger = logging.getLogger(__name__)


class EEGAnnotator(QMainWindow):
    """Main window for Ziyatron EEG annotation application.

    Integrates:
    - PyQtGraph plot widget for efficient rendering
    - EEGDataStreamer for lazy loading
    - Control toolbar for user interactions
    - CSV-based annotation persistence
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ziyatron EEG Annotator v2.0")
        self.resize(1400, 800)

        self.filename = None  # Set by open_file(); guards on_settings_changed / on_scale_changed

        # Application state
        self.state = AppState()
        self.state.montage_changed.connect(self.on_settings_changed)
        self.state.filter_changed.connect(self.on_settings_changed)
        self.state.scale_changed.connect(self.on_scale_changed)

        # Create UI components
        self.control_toolbar = ControlToolBar(self.state)
        self.control_toolbar.open_file_clicked.connect(self.open_file)
        self.control_toolbar.save_clicked.connect(self.save_annotations)

        # Keyboard shortcut: Ctrl+S (Cmd+S on Mac)
        save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        save_shortcut.activated.connect(self.save_annotations)

        self.eeg_plot_widget = EEGPlotWidget(self.state)

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
            self,
            "Open EDF File",
            "",
            file_filters
        )

        if not filename:
            return

        self.filename = Path(filename)

        try:
            # Load EDF file with current montage and filter settings
            self.eeg_plot_widget.load_edf_file(
                filename=str(self.filename),
                montage=self.state.montage,
                filter_params=self.state.filter
            )

            # Load existing annotations if available
            self.load_annotations()

            # Enable controls
            metadata = self.eeg_plot_widget.data_streamer.get_metadata()
            signal_duration = metadata['duration']
            s_freq = metadata['sfreq']

            self.control_toolbar.label_btn.setEnabled(True)
            self.control_toolbar.save_btn.setEnabled(True)
            self.control_toolbar.show_controls(signal_duration, s_freq)

            logger.info(f"Loaded file: {self.filename}")

        except Exception as e:
            logger.error(f"Failed to open file {filename}: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open EDF file:\n{e}"
            )

    def load_annotations(self):
        """Load existing annotations from CSV file if it exists."""
        if not self.filename:
            return

        work_dir = self.filename.parent
        eeg_file_name = self.filename.stem
        annotation_file_path = work_dir / f"{eeg_file_name}_{self.state.montage.replace(' ', '_')}.csv"

        if not annotation_file_path.exists():
            logger.info("No existing annotations found")
            return

        try:
            df = pd.read_csv(annotation_file_path)
            annotations = df.to_dict(orient="records")

            # Sort annotations
            annotations.sort(key=lambda a: (a['start_time'], a['stop_time'], a['onset']))

            # Merge annotations with same time/label but different channels
            merged_annotations = []
            if len(annotations) > 0:
                current_annotation = {
                    'channels': [annotations[0]['channels']],
                    'start_time': annotations[0]['start_time'],
                    'stop_time': annotations[0]['stop_time'],
                    'onset': annotations[0]['onset']
                }

                for i in range(1, len(annotations)):
                    ann = annotations[i]
                    if (current_annotation['start_time'] == ann['start_time'] and
                        current_annotation['stop_time'] == ann['stop_time'] and
                        current_annotation['onset'] == ann['onset']):
                        current_annotation['channels'].append(ann['channels'])
                    else:
                        merged_annotations.append(current_annotation)
                        current_annotation = {
                            'channels': [ann['channels']],
                            'start_time': ann['start_time'],
                            'stop_time': ann['stop_time'],
                            'onset': ann['onset']
                        }

                merged_annotations.append(current_annotation)

            self.eeg_plot_widget.load_annotations(merged_annotations)
            logger.info(f"Loaded {len(merged_annotations)} annotations from {annotation_file_path}")

        except Exception as e:
            logger.error(f"Failed to load annotations: {e}")
            QMessageBox.warning(
                self,
                "Warning",
                f"Failed to load existing annotations:\n{e}"
            )

    def save_annotations(self):
        """Save annotations to CSV file."""
        if not self.filename:
            QMessageBox.warning(self, "Warning", "No file is currently open")
            return

        annotations = self.eeg_plot_widget.get_annotations()

        if len(annotations) == 0:
            QMessageBox.information(self, "Info", "No annotations to save")
            return

        work_dir = self.filename.parent
        eeg_file_name = self.filename.stem
        annotation_file_path = work_dir / f"{eeg_file_name}_{self.state.montage.replace(' ', '_')}.csv"

        try:
            # Expand annotations (one row per channel)
            csv_rows = []
            for annotation in annotations:
                for channel in annotation['channels']:
                    csv_rows.append({
                        'channels': channel,
                        'start_time': annotation['start_time'],
                        'stop_time': annotation['stop_time'],
                        'onset': annotation['onset'],
                    })

            df = pd.DataFrame(csv_rows, columns=["channels", "start_time", "stop_time", "onset"])
            df.to_csv(annotation_file_path, index=False)

            logger.info(f"Saved {len(annotations)} annotations to {annotation_file_path}")
            QMessageBox.information(
                self,
                "Success",
                f"Annotations saved to:\n{annotation_file_path.name}"
            )

        except Exception as e:
            logger.error(f"Failed to save annotations: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save annotations:\n{e}"
            )

    def on_settings_changed(self):
        """Reload EEG data when montage or filter changes."""
        if not self.filename:
            return

        try:
            # Preserve current time position before reload resets the view
            saved_range = None
            if hasattr(self.eeg_plot_widget, '_last_view_range'):
                saved_range = self.eeg_plot_widget._last_view_range  # (start_time, duration)

            # Clear data streamer cache (settings changed)
            self.eeg_plot_widget.data_streamer.clear_cache()

            # Reload with new settings
            self.eeg_plot_widget.load_edf_file(
                filename=str(self.filename),
                montage=self.state.montage,
                filter_params=self.state.filter
            )

            # Restore time position after reload
            if saved_range is not None:
                start_time, duration = saved_range
                self.eeg_plot_widget._set_x_range_and_update(start_time, start_time + duration)

            # Reload annotations
            self.load_annotations()

            logger.info(f"Reloaded with montage={self.state.montage}, filter={self.state.filter}")

        except Exception as e:
            logger.error(f"Failed to reload with new settings: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to apply new settings:\n{e}"
            )

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

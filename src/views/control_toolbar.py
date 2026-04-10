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


from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIcon, QIntValidator, QDoubleValidator
from PyQt6.QtWidgets import (
    QToolBar,
    QPushButton,
    QSpinBox,
    QLabel,
    QLineEdit,
    QComboBox,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from src.utils.path_utils import resource_path
from src.core.montage_manager import montage_manager
from src.models.app_state import AppState


class ControlToolBar(QToolBar):
    """Toolbar for controlling EEG display and annotation operations."""

    open_file_clicked = pyqtSignal()
    save_clicked = pyqtSignal()

    def __init__(self, state: AppState):
        super().__init__()
        self.state = state

        # Montage selection
        self.select_montage = QComboBox()
        self.select_montage.addItems(sorted(montage_manager.montages.keys()))
        self.select_montage.currentTextChanged.connect(self.on_montage_changed)

        # File operations
        self.open_file = QPushButton("Open")
        self.open_file.setIcon(QIcon(resource_path("resources/icons/folder.png", to_string=True)))
        self.open_file.clicked.connect(self.on_open_clicked)

        self.save_btn = QPushButton("Save Annotation")
        self.save_btn.setIcon(QIcon(resource_path("resources/icons/diskette.png", to_string=True)))
        self.save_btn.clicked.connect(self.on_save_clicked)
        self.save_btn.setEnabled(False)

        # Undo button
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setIcon(QIcon(resource_path("resources/icons/undo.png", to_string=True)))
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.on_undo_clicked)

        # Label/annotate button
        self.label_btn = QPushButton("Label")
        self.label_btn.setIcon(QIcon(resource_path("resources/icons/add-selection.png", to_string=True)))
        self.label_btn.setEnabled(False)
        self.label_btn.setCheckable(True)
        self.label_btn.clicked.connect(self.on_label_clicked)
        self.state.draw_mode_changed.connect(self.label_btn.setChecked)

        # Validators for numeric inputs
        int_validator = QIntValidator()
        double_validator = QDoubleValidator()

        # Filter controls
        self.low_filter = QLineEdit()
        self.low_filter.setMaxLength(10)
        self.low_filter.setPlaceholderText("Low filter (Hz)")
        self.low_filter.setFixedWidth(100)
        self.low_filter.setValidator(double_validator)

        self.high_filter = QLineEdit()
        self.high_filter.setMaxLength(10)
        self.high_filter.setPlaceholderText("High filter (Hz)")
        self.high_filter.setFixedWidth(100)
        self.high_filter.setValidator(double_validator)

        self.apply_filter_btn = QPushButton("Apply Filter")
        self.apply_filter_btn.clicked.connect(self.on_filter_changed)
        self.on_filter_changed()  # Initialize filter

        # Scale selection
        self.select_scale = QComboBox()
        for scale in [1, 2, 5, 7, 10, 15, 20, 50, 70, 100, 200, 500, 1000]:
            self.select_scale.addItem(f'{scale} µV/mm')
        self.select_scale.currentTextChanged.connect(self.on_scale_changed)
        self.state.set_scale(int(self.select_scale.currentText().replace(' µV/mm', '')))

        # Display time controls
        self.spinner_label = QLabel("Display duration: ")
        self.x_lim_spinner = QSpinBox()

        # Goto time input
        self.goto_input = QLineEdit()
        self.goto_input.setMaxLength(10)
        self.goto_input.setFixedWidth(100)
        self.goto_input.setPlaceholderText("Goto (seconds)")
        self.goto_input.returnPressed.connect(self.on_goto_input_return_pressed)
        self.goto_input.setValidator(int_validator)

        # Info labels
        self.signal_duration_lbl = QLabel()
        self.sampling_freq_lbl = QLabel()

        # Connect undo button enable state
        self.state.enable_undo_button.connect(self.undo_btn.setEnabled)

        # Set initial montage
        self.state.set_montage(self.select_montage.currentText())

        # Layout
        display_widget = QWidget()
        display_layout = QHBoxLayout(display_widget)
        display_layout.addWidget(self.select_montage)
        display_layout.addWidget(self.open_file)
        display_layout.addWidget(self.save_btn)
        display_layout.addWidget(self.spinner_label)
        display_layout.addWidget(self.x_lim_spinner)
        display_layout.addWidget(self.goto_input)
        display_layout.addWidget(self.signal_duration_lbl)
        display_layout.addWidget(self.sampling_freq_lbl)
        display_layout.setContentsMargins(0, 0, 0, 0)

        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.addWidget(self.undo_btn)
        action_layout.addWidget(self.label_btn)
        action_layout.addWidget(self.low_filter)
        action_layout.addWidget(self.high_filter)
        action_layout.addWidget(self.apply_filter_btn)
        action_layout.addWidget(self.select_scale)
        action_layout.setContentsMargins(0, 0, 0, 0)

        tools_widget = QWidget()
        tools_layout = QVBoxLayout(tools_widget)
        tools_layout.addWidget(display_widget)
        tools_layout.addWidget(action_widget)
        tools_layout.setContentsMargins(0, 0, 0, 0)

        self.addWidget(tools_widget)

    def show_controls(self, signal_duration: float, s_freq: float):
        """Enable and configure controls after file is loaded.

        Args:
            signal_duration: Total duration of recording in seconds
            s_freq: Sampling frequency in Hz
        """
        self.signal_duration = signal_duration
        self.s_freq = s_freq

        self.x_lim_spinner.setMinimum(5)
        self.x_lim_spinner.setMaximum(int(signal_duration // 2))
        self.x_lim_spinner.setValue(10)
        self.x_lim_spinner.setSingleStep(5)
        self.x_lim_spinner.setSuffix(" Seconds")
        self.x_lim_spinner.valueChanged.connect(self.on_spinner_value_changed)

        self.signal_duration_lbl.setText(f"Duration: {signal_duration:.1f}s ")
        self.sampling_freq_lbl.setText(f"Sampling: {s_freq:.0f}Hz")

    def on_montage_changed(self, new_montage: str):
        """Handle montage selection change."""
        self.state.set_montage(new_montage)

    def on_open_clicked(self):
        """Emit signal to open file dialog."""
        self.open_file_clicked.emit()

    def on_save_clicked(self):
        """Emit signal to save annotations."""
        self.save_clicked.emit()

    def on_label_clicked(self):
        """Emit signal to start annotation selection."""
        self.state.label_clicked.emit()

    def on_spinner_value_changed(self, v: int):
        """Handle display duration change."""
        self.state.spinner_value_changed.emit(v)

    def on_goto_input_return_pressed(self):
        """Handle goto time input."""
        if self.goto_input.text():
            entered_number = int(self.goto_input.text())
            self.state.goto_input_return_pressed.emit(entered_number)

    def on_undo_clicked(self):
        """Emit signal to undo last annotation."""
        self.state.undo_clicked.emit()

    def on_filter_changed(self):
        """Handle filter parameter changes."""
        low = None if self.low_filter.text() == '' else float(self.low_filter.text())
        high = None if self.high_filter.text() == '' else float(self.high_filter.text())
        self.state.set_filter((low, high))

    def on_scale_changed(self, v: str):
        """Handle scale selection change."""
        self.state.set_scale(int(v.replace(' µV/mm', '')))

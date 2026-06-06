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
import math
from typing import Dict, List, Optional, Tuple

import pyqtgraph as pg
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from src.core.config import config
from src.core.data_streamer import EEGDataStreamer
from src.views.annotation_layer import AnnotationLayer, AnnotationROI  # noqa: F401

logger = logging.getLogger(__name__)


class EEGPlotWidget(QWidget):
    """Memory-efficient EEG plot widget using PyQtGraph.

    Key improvements over Matplotlib:
    - 10-100x faster rendering for time-series data
    - Automatic downsampling when zoomed out
    - Only renders visible viewport (clipToView)
    - GPU-accelerated with OpenGL (optional)
    - Smooth pan/zoom without full redraws

    Integrates with EEGDataStreamer for lazy loading of data windows.
    """

    def __init__(self, state=None, review_service=None, user_session=None):
        super().__init__()

        self.state = state
        self._review_service = review_service
        self._user_session = user_session
        self.data_streamer = EEGDataStreamer()

        # Plot configuration
        self._scale_constant = 0.00001
        self.scale_factor = self._scale_constant  # Vertical spacing between channels
        self.current_montage = "AVERAGE"
        self.current_filter = (None, None)
        self.montage_list = []  # Channel names for current montage
        self.signal_duration = 0
        self.window_duration = 10  # Initial display window in seconds

        # Flag to prevent signal cascading during programmatic range changes
        self._updating_range = False

        # Setup PyQtGraph widget
        self.setup_plot_widget()

        self._annotation_layer = AnnotationLayer(
            plot_widget=self.plot_widget,
            get_plot_bounds=self._get_plot_bounds,
            channel_y=self._channel_y,
            y_to_channel_range=self._y_to_channel_range,
            get_montage_list=lambda: self.montage_list,
            get_signal_duration=lambda: self.signal_duration,
            get_scale_factor=lambda: self.scale_factor,
            goto_time=self.goto_time,
            get_channel_index=lambda: self._channel_index,
            review_service=self._review_service,
            user_session=self._user_session,
            state=self.state,
            parent=self,
        )

        # Connect to app state signals if provided
        if self.state:
            self.state.label_clicked.connect(
                self._annotation_layer.enable_selection_mode
            )
            self.state.spinner_value_changed.connect(self.change_window_duration)
            self.state.goto_input_return_pressed.connect(self.goto_time)
            self.state.undo_clicked.connect(self._annotation_layer.undo_annotation)
            self.state.montage_changed.connect(
                self._annotation_layer.exit_draw_mode_if_active
            )
            self.state.filter_changed.connect(
                self._annotation_layer.exit_draw_mode_if_active
            )
            self.state.jump_label_changed.connect(self._annotation_layer.set_jump_label)
            self.state.jump_requested.connect(
                self._annotation_layer.jump_to_current_label
            )

        layout = QVBoxLayout()
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

    def setup_plot_widget(self):
        """Initialize PyQtGraph PlotWidget with optimized settings."""
        self.plot_widget = pg.PlotWidget()

        # Configure plot appearance
        self.plot_widget.setBackground("w")  # White background
        self.plot_widget.showGrid(x=True, y=False, alpha=0.3)
        self.plot_widget.setLabel("bottom", "Time", units="s")
        self.plot_widget.setLabel("left", "Channels")

        # Disable auto-range for manual control
        self.plot_widget.disableAutoRange()

        # Y axis is a fixed channel layout — never allow vertical zoom
        self.plot_widget.getViewBox().setMouseEnabled(x=True, y=False)

        # Disable PyQtGraph's built-in context menu (ViewBox + PlotItem)
        self.plot_widget.getPlotItem().setMenuEnabled(False)

        # Enable keyboard focus for arrow key navigation
        self.plot_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Connect view range change signal for lazy loading
        self.plot_widget.sigRangeChanged.connect(self.on_view_range_changed)

        # Install event filter for keyboard shortcuts and drawing
        self.plot_widget.installEventFilter(self)
        self.plot_widget.viewport().installEventFilter(self)

        # Plot items storage
        self.channel_curves = []
        self._channel_index: dict[str, int] = {}

    def _channel_y(self, channel_index: int) -> float:
        """Y position of a channel's center line (first channel at top)."""
        return (len(self.montage_list) - 1 - channel_index) * self.scale_factor

    def _y_to_channel_range(self, y_low: float, y_high: float) -> tuple[int, int]:
        """Return (first_ch, last_ch) covered by the Y span [y_low, y_high].

        A channel is covered iff its center line (``_channel_y``) lies within
        the span. Center line of row j (counting from the bottom) is at
        ``j * scale_factor``; channel index = n - 1 - j. This is robust at band
        borders (which sit at half-integer multiples of scale_factor) and never
        drifts when an already-banded annotation is re-measured.
        """
        n = len(self.montage_list)
        sf = self.scale_factor
        eps = sf * 1e-6  # absorb float dust so border edges land predictably
        j_min = max(0, math.ceil((y_low - eps) / sf))
        j_max = min(n - 1, math.floor((y_high + eps) / sf))
        if j_min > j_max:
            # Span too thin to contain any center line: snap to the nearest one.
            j = min(n - 1, max(0, round(((y_low + y_high) / 2) / sf)))
            j_min = j_max = j
        first_ch = n - 1 - j_max
        last_ch = n - 1 - j_min
        return first_ch, last_ch

    def load_edf_file(self, filename: str, montage_name: str, filter_params: Tuple):
        """Load EDF file and initialize display.

        Args:
            filename: Path to EDF file
            montage: Montage type (e.g., 'AVERAGE', 'BIPOLAR DOUBLE BANANA')
            filter_params: Tuple of (low_freq, high_freq)
        """
        self.data_streamer.open_edf(filename)
        self.current_montage = montage_name
        self.current_filter = filter_params

        metadata = self.data_streamer.get_metadata()
        self.signal_duration = metadata["duration"]

        # Load initial window to get channel information
        initial_window = self.data_streamer.get_window(
            start_time=0,
            duration=self.window_duration,
            montage_name=montage_name,
            filter_params=filter_params,
        )

        self.montage_list = initial_window.ch_names
        self._channel_index = {name: i for i, name in enumerate(self.montage_list)}
        n_channels = len(self.montage_list)

        # Setup plot with correct number of channels
        self.setup_channels(n_channels)

        # Display initial window
        self.update_plot(0, self.window_duration)

    def setup_channels(self, n_channels: int):
        """Create plot curves for each EEG channel.

        Args:
            n_channels: Number of channels to display
        """
        self.plot_widget.clear()
        self.channel_curves = []
        # Create one PlotDataItem per channel with optimization flags
        for i in range(n_channels):
            curve = self.plot_widget.plot(
                pen=pg.mkPen(color="k", width=1),
                autoDownsample=True,  # compute ds from view width each render
                autoDownsampleFactor=5.0,  # target ~5 samples per pixel
                clipToView=True,  # only render visible region (CRITICAL)
            )
            self.channel_curves.append(curve)

        # Set Y-axis ticks to show channel names
        y_ticks = [
            (self._channel_y(i), name) for i, name in enumerate(self.montage_list)
        ]
        y_axis = self.plot_widget.getAxis("left")
        y_axis.setTicks([y_ticks])

        # Set initial view range and enforce zoom-out limit.
        # _updating_range prevents setXRange/setYRange from firing on_view_range_changed,
        # which would trigger an extra update_plot before load_edf_file calls it.
        self._updating_range = True
        self.plot_widget.setXRange(0, self.window_duration, padding=0)
        self.plot_widget.getViewBox().setLimits(maxXRange=self.window_duration)
        self.plot_widget.setYRange(
            -self.scale_factor,
            (n_channels - 1) * self.scale_factor + self.scale_factor,
            padding=0,
        )
        self._updating_range = False

    def update_plot(self, start_time: float, duration: float):
        """Update plot with new time window from data streamer.

        This is where lazy loading happens - only loads visible window.

        Args:
            start_time: Start time in seconds
            duration: Window duration in seconds
        """
        # Load window from data streamer (lazy loading)
        window_data = self.data_streamer.get_window(
            start_time=start_time,
            duration=duration,
            montage_name=self.current_montage,
            filter_params=self.current_filter,
        )

        signal = window_data.get_data()
        time_axis = window_data.times + start_time

        # Update each channel's curve efficiently
        for i, curve in enumerate(self.channel_curves):
            curve.setData(time_axis, signal[i] + self._channel_y(i))

    def on_view_range_changed(self, _):
        """Called when user pans/zooms - triggers lazy loading of new window.

        This is the key integration point with the data streamer.
        """
        if self._updating_range:
            return

        view_range = self.plot_widget.viewRange()
        x_min, x_max = view_range[0]

        start_time = max(0, x_min)
        duration = x_max - x_min
        duration = min(duration, self.signal_duration - start_time)
        duration = min(duration, self.window_duration)
        if duration <= 0:
            return

        # Only reload if view has actually changed significantly
        # (avoid redundant loads during minor adjustments)
        if hasattr(self, "_last_view_range"):
            last_start, last_duration = self._last_view_range
            if (
                abs(start_time - last_start) < 0.5
                and abs(duration - last_duration) < 0.5
            ):
                return

        self._last_view_range = (start_time, duration)

        # Lazy load new window
        self._safe_update_plot(start_time, duration)

    def _safe_update_plot(self, start_time: float, duration: float):
        """Update the plot from a navigation slot, logging instead of crashing."""
        try:
            self.update_plot(start_time, duration)
        except Exception as e:
            logger.error(f"Failed to update plot at {start_time:.2f}s: {e}")

    def eventFilter(self, obj, event):
        """Handle keyboard and mouse events for navigation and drawing."""
        al = self._annotation_layer

        # Always track mouse position in view coordinates for copy/paste
        if obj == self.plot_widget.viewport() and event.type() == event.Type.MouseMove:
            scene_pos = self.plot_widget.mapFromGlobal(event.globalPosition().toPoint())
            view_pos = self.plot_widget.getViewBox().mapSceneToView(QPointF(scene_pos))
            al.update_mouse_pos(view_pos)

        # Deselect annotation on any background click (ROI click will re-select if needed)
        if (
            obj == self.plot_widget.viewport()
            and event.type() == event.Type.MouseButtonPress
            and not al.draw_mode_active
        ):
            al.deselect_all()

        # Mouse events are delivered to the viewport (QGraphicsView is a QAbstractScrollArea)
        if obj == self.plot_widget.viewport() and al.draw_mode_active:
            if event.type() == event.Type.MouseButtonPress:
                if al.handle_draw_mouse_press(event):
                    return True
            elif event.type() == event.Type.MouseMove:
                if al.handle_draw_mouse_move(event):
                    return True
            elif event.type() == event.Type.MouseButtonRelease:
                if al.handle_draw_mouse_release(event):
                    return True

        # Keyboard events are delivered to the plot widget
        if obj == self.plot_widget and event.type() == event.Type.KeyPress:
            key_event: QKeyEvent = event

            if key_event.key() == Qt.Key.Key_Escape and al.draw_mode_active:
                al.exit_draw_mode_if_active()
                return True
            elif key_event.key() == Qt.Key.Key_A:
                self.pan_left()
                return True
            elif key_event.key() == Qt.Key.Key_D:
                self.pan_right()
                return True
            elif key_event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                al.delete_hovered_annotation()
                return True
            elif (
                key_event.key() == Qt.Key.Key_Z
                and key_event.modifiers() & Qt.KeyboardModifier.ControlModifier
            ):
                al.undo_annotation()
                return True
            elif (
                key_event.key() == Qt.Key.Key_C
                and key_event.modifiers() & Qt.KeyboardModifier.ControlModifier
            ):
                al.copy_annotation()
                return True
            elif (
                key_event.key() == Qt.Key.Key_V
                and key_event.modifiers() & Qt.KeyboardModifier.ControlModifier
            ):
                al.paste_annotation()
                return True
            elif key_event.key() == Qt.Key.Key_L:
                al.enable_selection_mode()
                return True
            elif key_event.key() == Qt.Key.Key_Right:
                al.jump_next()
                return True
            elif key_event.key() == Qt.Key.Key_Left:
                al.jump_prev()
                return True

        return super().eventFilter(obj, event)

    @property
    def view_range(self) -> tuple | None:
        """Return current (start_time, duration) or None if no file is loaded."""
        return getattr(self, "_last_view_range", None)

    def set_view_range(self, start: float, duration: float) -> None:
        """Restore the visible window to (start, start+duration)."""
        self._set_x_range_and_update(start, start + duration)

    def _set_x_range_and_update(self, x_min: float, x_max: float):
        """Set X range without triggering on_view_range_changed, then update plot directly."""
        self._updating_range = True
        self.plot_widget.setXRange(x_min, x_max, padding=0)
        self._updating_range = False

        start_time = max(0, x_min)
        duration = x_max - x_min
        self._last_view_range = (start_time, duration)
        self._safe_update_plot(start_time, duration)

    def pan_left(self):
        """Pan view to the left by configured amount."""
        view_range = self.plot_widget.viewRange()
        x_min, x_max = view_range[0]
        pan_amount = config.pan_ammount

        new_x_min = max(0, x_min - pan_amount)
        new_x_max = max(self.window_duration, x_max - pan_amount)

        self._set_x_range_and_update(new_x_min, new_x_max)

    def pan_right(self):
        """Pan view to the right by configured amount."""
        view_range = self.plot_widget.viewRange()
        x_min, x_max = view_range[0]
        pan_amount = config.pan_ammount

        new_x_min = min(self.signal_duration - self.window_duration, x_min + pan_amount)
        new_x_max = min(self.signal_duration, x_max + pan_amount)

        self._set_x_range_and_update(new_x_min, new_x_max)

    def change_window_duration(self, duration: int):
        """Change the display window duration (zoom).

        Args:
            duration: New window duration in seconds
        """
        self.window_duration = duration
        self.plot_widget.getViewBox().setLimits(maxXRange=duration)

        view_range = self.plot_widget.viewRange()
        x_min = view_range[0][0]

        self._set_x_range_and_update(x_min, x_min + duration)

    def goto_time(self, time: int):
        """Jump to specific time in recording.

        Args:
            time: Target time in seconds
        """
        time = min(self.signal_duration - self.window_duration, time)
        time = max(0, time)

        self._set_x_range_and_update(time, time + self.window_duration)

    def enable_selection_mode(self):
        """Toggle annotation drawing mode."""
        self._annotation_layer.enable_selection_mode()

    def _get_plot_bounds(self):
        """Get the plot boundaries as a QRectF for constraining annotation movement."""
        n_channels = len(self.montage_list)
        y_min = -self.scale_factor
        y_height = (n_channels - 1) * self.scale_factor + 2 * self.scale_factor
        return QRectF(0, y_min, self.signal_duration, y_height)

    def render_annotations(self, annotations: Optional[List[Dict]] = None):
        """Render all saved annotations on the plot as editable rectangles."""
        self._annotation_layer.render_annotations(annotations)

    def get_annotations(self) -> List[Dict]:
        """Return all annotation dicts for persistence."""
        return self._annotation_layer.get_annotations()

    def load_annotations(self, annotations: List[Dict]):
        """Render annotations loaded from the persistence layer."""
        self._annotation_layer.load_annotations(annotations)

    def apply_review(self, roi, verdict, note: str):
        """Record an expert verdict on a single annotation ROI."""
        self._annotation_layer.apply_review_to_roi(roi, verdict, note)

    def refresh_annotation_styles(self):
        """Recolor all annotation borders from their current review status."""
        self._annotation_layer.refresh_styles()

    def undo_annotation(self):
        """Remove the last annotation."""
        self._annotation_layer.undo_annotation()

    def jump_to_nearest(self, label: str):
        """Jump to the annotation nearest to the current view center."""
        self._annotation_layer.jump_to_nearest(label)

    def jump_to_next(self, label: str):
        self._annotation_layer.jump_to_next(label)

    def jump_to_prev(self, label: str):
        self._annotation_layer.jump_to_prev(label)

    def clear_annotations(self):
        """Remove all annotations and reset annotation state."""
        self._annotation_layer.clear()

    def mark_annotations_saved(self):
        """Clear the dirty flag after a successful save."""
        self._annotation_layer.mark_saved()

    @property
    def is_annotations_dirty(self) -> bool:
        """True when there are unsaved annotation changes."""
        return self._annotation_layer.is_dirty

    @property
    def annotation_items(self):
        return self._annotation_layer.annotation_items

    @annotation_items.setter
    def annotation_items(self, value):
        self._annotation_layer.annotation_items = value

    def update_y_axis(self):
        """Update Y-axis ticks and range to match current scale factor.

        This should be called whenever scale_factor changes to ensure
        channel labels appear at the correct vertical positions.
        """
        if not self.montage_list:
            return

        n_channels = len(self.montage_list)

        # Update Y-axis ticks with new scale factor
        y_ticks = [
            (self._channel_y(i), name) for i, name in enumerate(self.montage_list)
        ]
        y_axis = self.plot_widget.getAxis("left")
        y_axis.setTicks([y_ticks])

        # Update Y-axis range to fit all channels with new scale
        self.plot_widget.setYRange(
            -self.scale_factor,
            (n_channels - 1) * self.scale_factor + self.scale_factor,
            padding=0,
        )

    def set_scale_factor(self, scale_uv_per_mm: int):
        """Update scale factor and refresh plot.

        This is the proper way to change the scale - it updates the scale factor,
        adjusts Y-axis labels to match, and reloads the plot.

        Args:
            scale_uv_per_mm: Scale in µV/mm (e.g., 1, 10, 100, 1000)
        """
        # Convert µV/mm to vertical spacing factor
        # The factor 0.0004 is empirical - adjust if channels are too close/far
        self.scale_factor = scale_uv_per_mm * self._scale_constant

        # Update Y-axis labels and range to match new scale
        self.update_y_axis()

        # Reload current view with new scale
        view_range = self.plot_widget.viewRange()
        x_min, x_max = view_range[0]
        self.update_plot(x_min, x_max - x_min)

        # Re-render annotations so their Y positions match the new scale
        self.render_annotations()

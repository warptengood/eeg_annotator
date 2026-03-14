"""High-performance EEG plot widget using PyQtGraph for efficient rendering."""
from typing import List, Dict, Optional, Tuple

import pyqtgraph as pg
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QDialog,
    QPushButton,
    QComboBox,
    QLabel,
    QGraphicsRectItem,
)
from PyQt6.QtGui import QKeyEvent, QCursor

from src.core.config import Config
from src.core.data_streamer import EEGDataStreamer


config = Config()

class AnnotationROI(pg.ROI):
    sigSelected = pg.QtCore.Signal(object)  # emits self when left-clicked

    def __init__(self, pos, size, data: Dict, **kwargs):
        pg.ROI.__init__(
            self,
            pos,
            size,
            pen=pg.mkPen(color='b', width=3),
            hoverPen=pg.mkPen(color='r', width=5),
            handlePen=pg.mkPen(color='r', width=3),
            handleHoverPen=pg.mkPen(color='g', width=5),
            rotatable=False,
            **kwargs
        )

        self.addScaleHandle([1, 1], [0, 0])
        self.addScaleHandle([0, 0], [1, 1])

        self.addScaleHandle([0, 1], [1, 0])
        self.addScaleHandle([1, 0], [0, 1])

        self.addScaleHandle([0.5, 1], [0.5, 0])
        self.addScaleHandle([0.5, 0], [0.5, 1])

        self.addScaleHandle([1, 0.5], [0, 0.5])
        self.addScaleHandle([0, 0.5], [1, 0.5])

        self._is_hovered = False
        self._is_selected = False
        self._normal_pen = pg.mkPen(color='b', width=3)
        self._selected_pen = pg.mkPen(color=(255, 165, 0), width=4)  # orange border when selected

        self.data = data
        self.text_item = pg.TextItem(
            text=self.data["onset"],
            color='b',
            anchor=(0, 0)  # Anchor at bottom-left so text sits ON TOP of rectangle
        )
        self.text_item.setPos(pos[0], pos[1])

        self.setAcceptedMouseButtons(
            pg.QtCore.Qt.MouseButton.RightButton | pg.QtCore.Qt.MouseButton.LeftButton
        )
        self.sigClicked.connect(self._on_clicked)

    def set_selected(self, selected: bool):
        """Toggle orange selection highlight."""
        self._is_selected = selected
        self.setPen(self._selected_pen if selected else self._normal_pen)

    def hoverEvent(self, ev):
        self._is_hovered = not ev.isExit()
        super().hoverEvent(ev)

    def _on_clicked(self, _roi, ev):
        if ev.button() == pg.QtCore.Qt.MouseButton.LeftButton:
            self.sigSelected.emit(self)
            ev.accept()
            return
        if ev.button() == pg.QtCore.Qt.MouseButton.RightButton:
            label_dialog = LabelDialog()
            try:
                current_label_idx = config.diagnosis.index(self.text_item.textItem.toPlainText())
                label_dialog.label_idx = current_label_idx
                combobox = label_dialog.findChild(QComboBox)
                if combobox:
                    combobox.setCurrentIndex(current_label_idx)
            except ValueError:
                pass

            label_dialog.exec()

            if label_dialog.delete_requested:
                self.sigRemoveRequested.emit(self)
            elif label_dialog.result():
                new_label = config.diagnosis[label_dialog.label_idx]
                self.data["onset"] = new_label
                self.text_item.setText(new_label, 'b')

            ev.accept()


class LabelDialog(QDialog):
    """Dialog for selecting annotation label from predefined diagnosis options."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Label Selection")
        self.label_idx = 0
        self.delete_requested = False

        layout = QVBoxLayout()

        # Label dropdown with diagnosis options from config
        label_combobox = QComboBox()
        label_combobox.addItems(config.diagnosis)
        label_combobox.currentIndexChanged.connect(self._on_index_changed)

        ok_btn = QPushButton("Ok")
        ok_btn.clicked.connect(self.accept)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._on_delete)

        layout.addWidget(QLabel("Select Diagnosis Label:"))
        layout.addWidget(label_combobox)
        layout.addWidget(ok_btn)
        layout.addWidget(delete_btn)

        self.setLayout(layout)

    def _on_index_changed(self, i: int):
        """Update selected label index."""
        self.label_idx = i

    def _on_delete(self):
        """Request deletion and close dialog."""
        self.delete_requested = True
        self.reject()

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

    def __init__(self, state=None):
        super().__init__()

        self.state = state
        self.data_streamer = EEGDataStreamer()

        # Plot configuration
        self._scale_constant = 0.00001
        self.scale_factor = self._scale_constant  # Vertical spacing between channels
        self.current_montage = "AVERAGE"
        self.current_filter = (None, None)
        self.montage_list = []  # Channel names for current montage
        self.signal_duration = 0
        self.window_duration = 10  # Initial display window in seconds

        # Annotation data
        self.annotation_items: List[AnnotationROI] = []
        self.selected_annotation_roi = None  # Currently selected annotation for highlighting
        self._clipboard_annotation = None    # Copied annotation data dict
        self._last_mouse_view_pos = None     # Cursor position in view coords (QPointF)

        # Drawing mode state
        self._draw_mode = False
        self._is_drawing = False
        self._draw_start_pos = None  # QPointF in view coordinates
        self._preview_rect = None  # QGraphicsRectItem for temporary preview

        # Flag to prevent signal cascading during programmatic range changes
        self._updating_range = False

        # Setup PyQtGraph widget
        self.setup_plot_widget()

        # Connect to app state signals if provided
        if self.state:
            self.state.label_clicked.connect(self.enable_selection_mode)
            self.state.spinner_value_changed.connect(self.change_window_duration)
            self.state.goto_input_return_pressed.connect(self.goto_time)
            self.state.undo_clicked.connect(self.undo_annotation)
            self.state.montage_changed.connect(lambda: self._exit_draw_mode() if self._draw_mode else None)
            self.state.filter_changed.connect(lambda: self._exit_draw_mode() if self._draw_mode else None)

        layout = QVBoxLayout()
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

    def setup_plot_widget(self):
        """Initialize PyQtGraph PlotWidget with optimized settings."""
        self.plot_widget = pg.PlotWidget()

        # Configure plot appearance
        self.plot_widget.setBackground('w')  # White background
        self.plot_widget.showGrid(x=True, y=False, alpha=0.3)
        self.plot_widget.setLabel('bottom', 'Time', units='s')
        self.plot_widget.setLabel('left', 'Channels')

        # Disable auto-range for manual control
        self.plot_widget.disableAutoRange()

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

    def load_edf_file(self, filename: str, montage: str, filter_params: Tuple):
        """Load EDF file and initialize display.

        Args:
            filename: Path to EDF file
            montage: Montage type (e.g., 'AVERAGE', 'BIPOLAR DOUBLE BANANA')
            filter_params: Tuple of (low_freq, high_freq)
        """
        self.data_streamer.open_edf(filename)
        self.current_montage = montage
        self.current_filter = filter_params

        metadata = self.data_streamer.get_metadata()
        self.signal_duration = metadata['duration']

        # Load initial window to get channel information
        initial_window = self.data_streamer.get_window(
            start_time=0,
            duration=self.window_duration,
            montage=montage,
            filter_params=filter_params
        )

        self.montage_list = initial_window.ch_names
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
                pen=pg.mkPen(color='k', width=1),
                downsample=10,  # Auto-downsample when zoomed out
                autoDownsampleFactor=5.0,  # Adjust detail by zoom level
                clipToView=True,  # Only render visible region (CRITICAL)
            )
            self.channel_curves.append(curve)

        # Set Y-axis ticks to show channel names
        y_ticks = [(i * self.scale_factor, name) for i, name in enumerate(self.montage_list)]
        y_axis = self.plot_widget.getAxis('left')
        y_axis.setTicks([y_ticks])

        # Set initial view range
        self.plot_widget.setXRange(0, self.window_duration, padding=0)
        self.plot_widget.setYRange(-self.scale_factor, (n_channels - 1) * self.scale_factor + self.scale_factor, padding=0)

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
            montage=self.current_montage,
            filter_params=self.current_filter
        )

        signal = window_data.get_data()
        time_axis = window_data.times + start_time

        # Update each channel's curve efficiently
        for i, curve in enumerate(self.channel_curves):
            y_offset = i * self.scale_factor
            curve.setData(time_axis, signal[i] + y_offset)

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
        if duration <= 0:
            return

        # Only reload if view has actually changed significantly
        # (avoid redundant loads during minor adjustments)
        if hasattr(self, '_last_view_range'):
            last_start, last_duration = self._last_view_range
            if abs(start_time - last_start) < 0.5 and abs(duration - last_duration) < 0.5:
                return

        self._last_view_range = (start_time, duration)

        # Lazy load new window
        self.update_plot(start_time, duration)

    def eventFilter(self, obj, event):
        """Handle keyboard and mouse events for navigation and drawing."""
        # Always track mouse position in view coordinates for copy/paste
        if obj == self.plot_widget.viewport() and event.type() == event.Type.MouseMove:
            scene_pos = self.plot_widget.mapFromGlobal(event.globalPosition().toPoint())
            self._last_mouse_view_pos = self.plot_widget.getViewBox().mapSceneToView(
                QPointF(scene_pos)
            )

        # Deselect annotation on any background click (ROI click will re-select if needed)
        if obj == self.plot_widget.viewport() and event.type() == event.Type.MouseButtonPress and not self._draw_mode:
            self._deselect_all()

        # Mouse events are delivered to the viewport (QGraphicsView is a QAbstractScrollArea)
        if obj == self.plot_widget.viewport() and self._draw_mode:
            if event.type() == event.Type.MouseButtonPress:
                if self._on_draw_mouse_press(event):
                    return True
            elif event.type() == event.Type.MouseMove:
                if self._on_draw_mouse_move(event):
                    return True
            elif event.type() == event.Type.MouseButtonRelease:
                if self._on_draw_mouse_release(event):
                    return True

        # Keyboard events are delivered to the plot widget
        if obj == self.plot_widget and event.type() == event.Type.KeyPress:
            key_event: QKeyEvent = event

            if key_event.key() == Qt.Key.Key_Escape and self._draw_mode:
                self._exit_draw_mode()
                return True
            elif key_event.key() == Qt.Key.Key_A:
                self.pan_left()
                return True
            elif key_event.key() == Qt.Key.Key_D:
                self.pan_right()
                return True
            elif key_event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self._delete_hovered_annotation()
                return True
            elif key_event.key() == Qt.Key.Key_Z and key_event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.undo_annotation()
                return True
            elif key_event.key() == Qt.Key.Key_C and key_event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._copy_annotation()
                return True
            elif key_event.key() == Qt.Key.Key_V and key_event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._paste_annotation()
                return True
            elif key_event.key() == Qt.Key.Key_L:
                self.enable_selection_mode()
                return True

        return super().eventFilter(obj, event)

    def _set_x_range_and_update(self, x_min: float, x_max: float):
        """Set X range without triggering on_view_range_changed, then update plot directly."""
        self._updating_range = True
        self.plot_widget.setXRange(x_min, x_max, padding=0)
        self._updating_range = False

        start_time = max(0, x_min)
        duration = x_max - x_min
        self._last_view_range = (start_time, duration)
        self.update_plot(start_time, duration)

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
        if self._draw_mode:
            self._exit_draw_mode()
        else:
            self._enter_draw_mode()

    def _enter_draw_mode(self):
        """Enter annotation drawing mode. Disables pan/zoom, changes cursor."""
        self._draw_mode = True
        self._is_drawing = False

        # Disable ViewBox mouse interaction to prevent pan/zoom from consuming events
        self.plot_widget.getViewBox().setMouseEnabled(x=False, y=False)

        # Change cursor to crosshair
        self.plot_widget.setCursor(QCursor(Qt.CursorShape.CrossCursor))

        # Create preview rectangle (hidden until drag starts)
        self._preview_rect = QGraphicsRectItem()
        self._preview_rect.setPen(pg.mkPen(color=(0, 0, 255, 200), width=2, style=Qt.PenStyle.DashLine))
        self._preview_rect.setBrush(pg.mkBrush(0, 0, 255, 40))
        self._preview_rect.setZValue(1e8)
        self._preview_rect.hide()
        self.plot_widget.getViewBox().addItem(self._preview_rect, ignoreBounds=True)

        if self.state:
            self.state.draw_mode_changed.emit(True)

    def _exit_draw_mode(self):
        """Exit annotation drawing mode. Restores pan/zoom and cursor."""
        self._draw_mode = False
        self._is_drawing = False
        self._draw_start_pos = None

        # Re-enable ViewBox mouse interaction
        self.plot_widget.getViewBox().setMouseEnabled(x=True, y=True)

        # Restore default cursor
        self.plot_widget.unsetCursor()

        # Remove preview rectangle
        if self._preview_rect is not None:
            self.plot_widget.getViewBox().removeItem(self._preview_rect)
            self._preview_rect = None

        if self.state:
            self.state.draw_mode_changed.emit(False)

    def _on_draw_mouse_press(self, event) -> bool:
        """Handle mouse press in drawing mode. Records start position."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # Map widget position to view (data) coordinates
        view_box = self.plot_widget.getViewBox()
        scene_pos = self.plot_widget.mapToScene(event.position().toPoint())
        view_pos = view_box.mapSceneToView(scene_pos)

        self._draw_start_pos = view_pos
        self._is_drawing = True

        # Show preview rectangle at zero size
        self._preview_rect.setRect(QRectF(view_pos, view_pos))
        self._preview_rect.show()

        return True

    def _on_draw_mouse_move(self, event) -> bool:
        """Handle mouse move in drawing mode. Updates preview rectangle."""
        if not self._is_drawing or self._draw_start_pos is None:
            return False

        view_box = self.plot_widget.getViewBox()
        scene_pos = self.plot_widget.mapToScene(event.position().toPoint())
        view_pos = view_box.mapSceneToView(scene_pos)

        # Update preview rectangle (normalized handles any drag direction)
        rect = QRectF(self._draw_start_pos, view_pos).normalized()
        self._preview_rect.setRect(rect)

        return True

    def _on_draw_mouse_release(self, event) -> bool:
        """Handle mouse release in drawing mode. Creates AnnotationROI from drawn rect."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if not self._is_drawing or self._draw_start_pos is None:
            return False

        view_box = self.plot_widget.getViewBox()
        scene_pos = self.plot_widget.mapToScene(event.position().toPoint())
        view_pos = view_box.mapSceneToView(scene_pos)

        # Build final rectangle
        rect = QRectF(self._draw_start_pos, view_pos).normalized()

        # Hide preview and reset drawing state
        self._preview_rect.hide()
        self._is_drawing = False
        self._draw_start_pos = None

        # Minimum size threshold to prevent accidental clicks
        min_width = 0.2  # seconds
        min_height = 0.5 * self.scale_factor
        if rect.width() < min_width or rect.height() < min_height:
            self._exit_draw_mode()
            return True

        # Clamp to plot bounds
        plot_bounds = self._get_plot_bounds()
        rect = rect.intersected(plot_bounds)
        if rect.isEmpty():
            self._exit_draw_mode()
            return True

        # Map Y coordinates to channel indices
        x_start = rect.left()
        x_end = rect.right()
        y_start = rect.top()
        y_end = rect.bottom()

        first_ch = max(0, int(min(y_start, y_end) / self.scale_factor))
        last_ch = min(len(self.montage_list) - 1, int(max(y_start, y_end) / self.scale_factor))
        selected_channels = self.montage_list[first_ch:last_ch + 1]

        if len(selected_channels) == 0:
            self._exit_draw_mode()
            return True

        annotation_data = {
            "channels": selected_channels,
            "start_time": round(x_start),
            "stop_time": round(x_end),
            "onset": "BCKG",
        }

        annotation_roi = AnnotationROI(
            pos=[rect.left(), rect.top()],
            size=[rect.width(), rect.height()],
            data=annotation_data,
        )

        self._create_editable_annotation_rect(annotation_roi)

        if self.state:
            self.state.enable_undo_button.emit(True)

        # Exit draw mode after creating annotation
        self._exit_draw_mode()

        return True

    def _get_plot_bounds(self) -> QRectF:
        """Get the plot boundaries as a QRectF for constraining annotation movement."""
        n_channels = len(self.montage_list)
        y_min = -self.scale_factor
        y_height = (n_channels - 1) * self.scale_factor + 2 * self.scale_factor
        return QRectF(0, y_min, self.signal_duration, y_height)

    def _create_editable_annotation_rect(self, annotation_roi: AnnotationROI) -> AnnotationROI:
        """Create an editable annotation rectangle with event handlers."""

        # Restrict movement to plot boundaries
        annotation_roi.maxBounds = self._get_plot_bounds()

        # Connect signals for data synchronization
        annotation_roi.sigRegionChangeFinished.connect(lambda: self._on_annotation_moved(annotation_roi))
        annotation_roi.sigRemoveRequested.connect(lambda: self._delete_annotation(annotation_roi))
        annotation_roi.sigSelected.connect(self._select_annotation)

        # Connect region changed signal to update text position during drag
        annotation_roi.sigRegionChanged.connect(lambda: self._update_annotation_text_position(annotation_roi))

        self.plot_widget.addItem(annotation_roi)
        self.plot_widget.addItem(annotation_roi.text_item)

        self.annotation_items.append(annotation_roi)

        return annotation_roi

    def _update_annotation_text_position(self, annotation_roi: AnnotationROI):
        """Update text position when annotation is moved."""

        if annotation_roi:
            pos = annotation_roi.pos()
            # Position text at top-left of rectangle
            # Anchor is (0, 1) so text sits on top of rectangle
            annotation_roi.text_item.setPos(pos[0], pos[1])

    def _on_annotation_moved(self, annotation_roi: AnnotationROI):
        """Synchronize annotation data after ROI move/resize is complete.

        Called when user finishes dragging or resizing an annotation.
        Updates the underlying data to match new position/size.

        Args:
            roi: RectROI that was moved/resized
        """
        # Get new bounds
        pos = annotation_roi.pos()
        size = annotation_roi.size()

        x_start = pos[0]
        x_end = pos[0] + size[0]
        y_start = pos[1]
        y_end = pos[1] + size[1]

        # Determine new selected channels based on Y position
        first_ch = max(0, int(min(y_start, y_end) / self.scale_factor))
        last_ch = min(len(self.montage_list) - 1, int(max(y_start, y_end) / self.scale_factor))
        selected_channels = self.montage_list[first_ch:last_ch + 1]

        # Update annotation data in-place
        annotation_data = annotation_roi.data
        annotation_data["channels"] = selected_channels
        annotation_data["start_time"] = round(x_start)
        annotation_data["stop_time"] = round(x_end)

    def _delete_annotation(self, annotation_roi: AnnotationROI):
        """Delete annotation from both visual items and data."""
        if not annotation_roi:
            return

        # Disconnect signals before removal
        annotation_roi.sigRegionChangeFinished.disconnect()
        annotation_roi.sigRemoveRequested.disconnect()
        annotation_roi.sigRegionChanged.disconnect()
        annotation_roi.sigSelected.disconnect()

        # Remove from visual items (both rect and text)
        self.plot_widget.removeItem(annotation_roi.text_item)
        self.plot_widget.removeItem(annotation_roi)

        # Remove from annotation_items list
        if annotation_roi in self.annotation_items:
            self.annotation_items.remove(annotation_roi)

        # Clear selection if deleted annotation was selected
        if self.selected_annotation_roi is annotation_roi:
            self.selected_annotation_roi = None

        # Disable undo button if no more annotations
        if len(self.annotation_items) == 0 and self.state:
            self.state.enable_undo_button.emit(False)

    def _delete_hovered_annotation(self):
        """Delete the annotation currently under the mouse cursor."""
        for roi in self.annotation_items:
            if roi._is_hovered:
                self._delete_annotation(roi)
                return

    def _select_annotation(self, roi: AnnotationROI):
        """Select an annotation, deselecting any previously selected one."""
        if self.selected_annotation_roi and self.selected_annotation_roi is not roi:
            self.selected_annotation_roi.set_selected(False)
        self.selected_annotation_roi = roi
        roi.set_selected(True)

    def _deselect_all(self):
        """Clear the current annotation selection."""
        if self.selected_annotation_roi:
            self.selected_annotation_roi.set_selected(False)
        self.selected_annotation_roi = None

    def _copy_annotation(self):
        """Copy the currently selected annotation to the internal clipboard."""
        if self.selected_annotation_roi is None:
            return
        src = self.selected_annotation_roi.data
        self._clipboard_annotation = {
            "channels": list(src["channels"]),
            "start_time": src["start_time"],
            "stop_time": src["stop_time"],
            "onset": src["onset"],
        }

    def _paste_annotation(self):
        """Paste the clipboard annotation at the current cursor X position."""
        if self._clipboard_annotation is None or self._last_mouse_view_pos is None:
            return

        data = dict(self._clipboard_annotation)
        data["channels"] = list(self._clipboard_annotation["channels"])

        # Reposition: cursor X = start of pasted annotation, keep same duration
        duration = data["stop_time"] - data["start_time"]
        cursor_x = self._last_mouse_view_pos.x()
        new_start = round(cursor_x)
        new_end = round(cursor_x + duration)

        # Clamp to file bounds
        new_start = max(0, min(new_start, int(self.signal_duration) - 1))
        new_end = max(new_start + 1, min(new_end, int(self.signal_duration)))
        data["start_time"] = new_start
        data["stop_time"] = new_end

        # Validate channels exist in current montage
        valid_channels = [c for c in data["channels"] if c in self.montage_list]
        if not valid_channels:
            return
        data["channels"] = valid_channels

        # Compute Y bounds using same formula as render_annotations
        try:
            first_idx = self.montage_list.index(valid_channels[0])
            last_idx = self.montage_list.index(valid_channels[-1])
        except ValueError:
            return

        y_min = min(first_idx, last_idx) * self.scale_factor
        y_max = max(first_idx, last_idx) * self.scale_factor

        annotation_roi = AnnotationROI(
            pos=[new_start, y_min],
            size=[new_end - new_start, y_max - y_min],
            data=data,
        )
        self._create_editable_annotation_rect(annotation_roi)

        if self.state:
            self.state.enable_undo_button.emit(True)

    def render_annotations(self, annotations: Optional[List[Dict]] = None):
        """Render all saved annotations on the plot as EDITABLE rectangles."""
        # Clear existing annotation items
        self._deselect_all()
        for annotation_roi in self.annotation_items:
            annotation_roi.sigRegionChangeFinished.disconnect()
            annotation_roi.sigRemoveRequested.disconnect()
            annotation_roi.sigRegionChanged.disconnect()
            annotation_roi.sigSelected.disconnect()
            self.plot_widget.removeItem(annotation_roi.text_item)
            self.plot_widget.removeItem(annotation_roi)

        if annotations is None:
            annotations = [annotation_roi.data for annotation_roi in self.annotation_items]
        self.annotation_items.clear()

        # Re-render all annotations as editable
        for annotation_data in annotations:
            if len(annotation_data["channels"]) == 0:
                continue

            # Get channel indices for Y positioning
            try:
                first_ch_idx = self.montage_list.index(annotation_data["channels"][0])
                last_ch_idx = self.montage_list.index(annotation_data["channels"][-1])
            except ValueError:
                # Channel not in current montage, skip
                continue

            # Ensure y_start <= y_end for positive height
            y_min = min(first_ch_idx, last_ch_idx) * self.scale_factor
            y_max = max(first_ch_idx, last_ch_idx) * self.scale_factor

            x_start = annotation_data["start_time"]
            x_end = annotation_data["stop_time"]

            annotation_roi = AnnotationROI(
                pos=[x_start, y_min],
                size=[x_end - x_start, y_max - y_min],
                data=annotation_data,
            )
            self._create_editable_annotation_rect(annotation_roi)

    def undo_annotation(self):
        """Remove the last annotation."""
        if len(self.annotation_items) == 0:
            if self.state:
                self.state.enable_undo_button.emit(False)
            return

        # Remove last annotation
        annotation_roi = self.annotation_items.pop()

        # Disconnect signals before removal
        annotation_roi.sigRegionChangeFinished.disconnect()
        annotation_roi.sigRemoveRequested.disconnect()
        annotation_roi.sigRegionChanged.disconnect()
        annotation_roi.sigSelected.disconnect()

        self.plot_widget.removeItem(annotation_roi.text_item)
        self.plot_widget.removeItem(annotation_roi)

        # Clear selection if deleted annotation was selected
        if self.selected_annotation_roi is annotation_roi:
            self.selected_annotation_roi = None

        # Disable undo button if no more annotations
        if len(self.annotation_items) == 0 and self.state:
            self.state.enable_undo_button.emit(False)

    def update_y_axis(self):
        """Update Y-axis ticks and range to match current scale factor.

        This should be called whenever scale_factor changes to ensure
        channel labels appear at the correct vertical positions.
        """
        if not self.montage_list:
            return

        n_channels = len(self.montage_list)

        # Update Y-axis ticks with new scale factor
        y_ticks = [(i * self.scale_factor, name) for i, name in enumerate(self.montage_list)]
        y_axis = self.plot_widget.getAxis('left')
        y_axis.setTicks([y_ticks])

        # Update Y-axis range to fit all channels with new scale
        self.plot_widget.setYRange(
            -self.scale_factor,
            (n_channels - 1) * self.scale_factor + self.scale_factor,
            padding=0
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

    def get_annotations(self) -> List[Dict]:
        """Get all annotations for saving to CSV.

        Returns:
            List of annotation dictionaries
        """
        return [annotation_roi.data for annotation_roi in self.annotation_items]

    def load_annotations(self, annotations: List[Dict]):
        """Load annotations from CSV file.

        Args:
            annotations: List of annotation dictionaries with channels, start_time, stop_time, onset
        """
        self.render_annotations(annotations)

        if len(self.annotation_items) > 0 and self.state:
            self.state.enable_undo_button.emit(True)

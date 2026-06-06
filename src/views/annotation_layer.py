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

import bisect
import logging
from typing import Callable, Dict, List, Optional

import pyqtgraph as pg
from PyQt6.QtCore import QObject, QPointF, QRectF, Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QGraphicsRectItem,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from src.core.config import config

logger = logging.getLogger(__name__)

# Border colors per review status (RGB). Selection overrides these temporarily.
_STATUS_COLORS = {
    "draft": (130, 130, 130),
    "submitted": (30, 90, 220),
    "verified": (0, 160, 0),
    "rejected": (210, 40, 40),
    "needs_changes": (160, 60, 200),
}
_DEFAULT_STATUS_COLOR = (130, 130, 130)
_SELECTED_COLOR = (255, 140, 0)


def _status_color(data: Dict) -> tuple:
    """Border color for an annotation, derived from its review status."""
    status = (data.get("review") or {}).get("status", "draft")
    return _STATUS_COLORS.get(status, _DEFAULT_STATUS_COLOR)


class AnnotationROI(pg.ROI):
    sigSelected = pg.QtCore.Signal(object)  # emits self when left-clicked
    sigEdited = pg.QtCore.Signal(object)  # emits self when its label is edited

    def __init__(
        self,
        pos,
        size,
        data: Dict,
        get_scale_factor: Optional[Callable[[], float]] = None,
        **kwargs,
    ):
        pg.ROI.__init__(
            self,
            pos,
            size,
            hoverPen=pg.mkPen(color="r", width=5),
            handlePen=pg.mkPen(color="r", width=3),
            handleHoverPen=pg.mkPen(color="g", width=5),
            rotatable=False,
            # Time (X) stays continuous; channel coverage (Y) snaps to channel
            # borders. Translation snaps Y via our getSnapPosition override;
            # resize snaps are re-banded by AnnotationLayer on release.
            translateSnap=True,
            snapSize=1.0,
            **kwargs,
        )
        self._get_scale_factor = get_scale_factor

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
        self._selected_pen = pg.mkPen(color=_SELECTED_COLOR, width=4)

        self.data = data
        self.text_item = pg.TextItem(
            text=self.data["onset"],
            color=_status_color(data),
            anchor=(0, 0),  # Anchor at bottom-left so text sits ON TOP of rectangle
        )
        self.text_item.setPos(pos[0], pos[1])

        self.refresh_status_style()

        self.setAcceptedMouseButtons(
            pg.QtCore.Qt.MouseButton.RightButton | pg.QtCore.Qt.MouseButton.LeftButton
        )
        self.sigClicked.connect(self._on_clicked)

    def getSnapPosition(self, pos, snap=None):
        """Snap only Y to the channel-border lattice; leave X (time) free.

        Channel bands are centered on the curve lines (at integer multiples of
        ``sf``), so the borders between them — where a box edge belongs — sit at
        half-integer multiples: ``(k + 0.5) * sf``.
        """
        sf = self._get_scale_factor() if self._get_scale_factor else None
        if not sf:
            return pg.Point(pos)
        snapped_y = (round(pos[1] / sf - 0.5) + 0.5) * sf
        return pg.Point(pos[0], snapped_y)

    def refresh_status_style(self):
        """Recolor the border/label from the current review status."""
        color = _status_color(self.data)
        self._normal_pen = pg.mkPen(color=color, width=3)
        self.text_item.setColor(color)
        self.setPen(self._selected_pen if self._is_selected else self._normal_pen)

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
                current_label_idx = config.diagnosis.index(
                    self.text_item.textItem.toPlainText()
                )
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
                if new_label != self.data["onset"]:
                    self.data["onset"] = new_label
                    self.text_item.setText(new_label)
                    # sigEdited -> _on_annotation_edited -> refresh_status_style
                    # owns the (re)coloring after the edit resets review status.
                    self.sigEdited.emit(self)

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


class AnnotationLayer(QObject):
    """Manages all annotation state and logic for EEGPlotWidget.

    Holds annotation items, draw-mode state machine, copy/paste, and
    jump navigation. All dependencies on the parent widget are injected
    as callables so this class has no back-reference to EEGPlotWidget.
    """

    def __init__(
        self,
        plot_widget: pg.PlotWidget,
        get_plot_bounds: Callable[[], QRectF],
        channel_y: Callable[[int], float],
        y_to_channel_range: Callable[[float, float], tuple],
        get_montage_list: Callable[[], list],
        get_signal_duration: Callable[[], float],
        get_scale_factor: Callable[[], float],
        goto_time: Callable[[float], None],
        get_channel_index: Callable[[], dict],
        review_service=None,
        user_session=None,
        state=None,
        parent=None,
    ):
        super().__init__(parent)

        self._plot_widget = plot_widget
        self._get_plot_bounds = get_plot_bounds
        self._channel_y = channel_y
        self._y_to_channel_range = y_to_channel_range
        self._get_montage_list = get_montage_list
        self._get_signal_duration = get_signal_duration
        self._get_scale_factor = get_scale_factor
        self._goto_time = goto_time
        self._get_channel_index = get_channel_index
        self._review_service = review_service
        self._user_session = user_session
        self._state = state

        # Annotation data
        self.annotation_items: List[AnnotationROI] = []
        self.selected_annotation_roi: Optional[AnnotationROI] = None
        self._clipboard_annotation: Optional[Dict] = None
        self._last_mouse_view_pos: Optional[QPointF] = None

        # Jump navigation state
        self._sorted_annotations: list = (
            []
        )  # list of (start_time, AnnotationROI), sorted
        self._jump_cursor: Optional[AnnotationROI] = None
        self._jump_label: str = "ALL"

        # Drawing mode state
        self._draw_mode = False
        self._is_drawing = False
        self._draw_start_pos: Optional[QPointF] = None
        self._preview_rect: Optional[QGraphicsRectItem] = None

        # Dirty flag — True when annotations have unsaved changes
        self._dirty = False

    # ------------------------------------------------------------------
    # Mouse tracking
    # ------------------------------------------------------------------

    def update_mouse_pos(self, view_pos: QPointF) -> None:
        self._last_mouse_view_pos = view_pos

    @property
    def is_dirty(self) -> bool:
        """True when there are unsaved annotation changes."""
        return self._dirty

    @property
    def draw_mode_active(self) -> bool:
        """True while the annotation drawing mode is engaged."""
        return self._draw_mode

    def exit_draw_mode_if_active(self) -> None:
        """Leave draw mode if currently active (no-op otherwise)."""
        if self._draw_mode:
            self._exit_draw_mode()

    # Public event-handling entry points used by EEGPlotWidget.eventFilter.
    def handle_draw_mouse_press(self, event) -> bool:
        return self._on_draw_mouse_press(event)

    def handle_draw_mouse_move(self, event) -> bool:
        return self._on_draw_mouse_move(event)

    def handle_draw_mouse_release(self, event) -> bool:
        return self._on_draw_mouse_release(event)

    def delete_hovered_annotation(self) -> None:
        self._delete_hovered_annotation()

    def copy_annotation(self) -> None:
        self._copy_annotation()

    def paste_annotation(self) -> None:
        self._paste_annotation()

    def set_jump_label(self, label: str) -> None:
        self._jump_label = label

    def jump_to_current_label(self) -> None:
        self.jump_to_nearest(self._jump_label)

    def jump_next(self) -> None:
        self._jump_in_direction(self._jump_label, forward=True)

    def jump_prev(self) -> None:
        self._jump_in_direction(self._jump_label, forward=False)

    def clear(self):
        """Remove all annotations from the plot and reset all state.

        Called before loading a new montage/file to ensure no stale ROIs
        remain in the scene or in the jump index.
        """
        if self._draw_mode:
            self._exit_draw_mode()
        self.deselect_all()
        for roi in self.annotation_items:
            self._disconnect_roi(roi)
            self._plot_widget.removeItem(roi.text_item)
            self._plot_widget.removeItem(roi)
        self.annotation_items.clear()
        self._sorted_annotations.clear()
        self._jump_cursor = None
        self._dirty = False
        if self._state:
            self._state.enable_undo_button.emit(False)

    # ------------------------------------------------------------------
    # Domain helpers
    # ------------------------------------------------------------------

    def _channel_band(self, first_ch: int, last_ch: int) -> tuple:
        """Return (y_bottom, height) for a box centered on channels first..last.

        Each channel band is centered on its curve line (``_channel_y``) and is
        one ``scale_factor`` tall, so the box spans from half a band below the
        bottom channel's center to half a band above the top channel's center.
        A single channel is one full band tall (always visible) and the box
        visually straddles exactly the channels it lists.
        """
        sf = self._get_scale_factor()
        y_bottom = self._channel_y(last_ch) - sf / 2.0
        height = (last_ch - first_ch + 1) * sf
        return y_bottom, height

    def _current_author(self) -> str:
        if self._user_session is not None:
            return self._user_session.name
        return ""

    def _build_annotation_data(
        self, channels: list, start_time: float, stop_time: float, onset: str
    ) -> Dict:
        """Build a fully-stamped annotation dict for a newly authored region."""
        if self._review_service is not None:
            ann = self._review_service.stamp_new(
                author=self._current_author(),
                montage=self._state.montage_name if self._state is not None else "",
                channels=channels,
                start_time=start_time,
                stop_time=stop_time,
                onset=onset,
            )
            return ann.model_dump()
        # Fallback for contexts without a service (e.g. isolated tests)
        return {
            "channels": list(channels),
            "start_time": start_time,
            "stop_time": stop_time,
            "onset": onset,
        }

    def _touch(self, data: Dict) -> None:
        """Mark an annotation edited via the review service (no-op without one)."""
        if self._review_service is None:
            return
        from src.domain.annotation import Annotation

        ann = self._review_service.touch(Annotation(**data))
        data.update(ann.model_dump())

    def apply_review_to_roi(self, roi: "AnnotationROI", verdict, note: str) -> None:
        """Record an expert verdict on a single annotation and restyle it."""
        if self._review_service is None or roi is None:
            return
        from src.domain.annotation import Annotation

        reviewer = self._current_author()
        ann = self._review_service.apply_review(
            Annotation(**roi.data), verdict, reviewer, note
        )
        roi.data.update(ann.model_dump())
        roi.refresh_status_style()
        self._dirty = True

    # ------------------------------------------------------------------
    # Draw mode state machine
    # ------------------------------------------------------------------

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
        self._plot_widget.getViewBox().setMouseEnabled(x=False, y=False)

        # Change cursor to crosshair
        self._plot_widget.setCursor(QCursor(Qt.CursorShape.CrossCursor))

        # Create preview rectangle (hidden until drag starts)
        self._preview_rect = QGraphicsRectItem()
        self._preview_rect.setPen(
            pg.mkPen(color=(0, 0, 255, 200), width=2, style=Qt.PenStyle.DashLine)
        )
        self._preview_rect.setBrush(pg.mkBrush(0, 0, 255, 40))
        self._preview_rect.setZValue(1e8)
        self._preview_rect.hide()
        self._plot_widget.getViewBox().addItem(self._preview_rect, ignoreBounds=True)

        if self._state:
            self._state.draw_mode_changed.emit(True)

    def _exit_draw_mode(self):
        """Exit annotation drawing mode. Restores pan/zoom and cursor."""
        self._draw_mode = False
        self._is_drawing = False
        self._draw_start_pos = None

        # Re-enable ViewBox mouse interaction (Y stays locked — fixed channel layout)
        self._plot_widget.getViewBox().setMouseEnabled(x=True, y=False)

        # Restore default cursor
        self._plot_widget.unsetCursor()

        # Remove preview rectangle
        if self._preview_rect is not None:
            self._plot_widget.getViewBox().removeItem(self._preview_rect)
            self._preview_rect = None

        if self._state:
            self._state.draw_mode_changed.emit(False)

    def _on_draw_mouse_press(self, event) -> bool:
        """Handle mouse press in drawing mode. Records start position."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # Map widget position to view (data) coordinates
        view_box = self._plot_widget.getViewBox()
        scene_pos = self._plot_widget.mapToScene(event.position().toPoint())
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

        view_box = self._plot_widget.getViewBox()
        scene_pos = self._plot_widget.mapToScene(event.position().toPoint())
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

        view_box = self._plot_widget.getViewBox()
        scene_pos = self._plot_widget.mapToScene(event.position().toPoint())
        view_pos = view_box.mapSceneToView(scene_pos)

        # Build final rectangle
        rect = QRectF(self._draw_start_pos, view_pos).normalized()

        # Hide preview and reset drawing state
        self._preview_rect.hide()
        self._is_drawing = False
        self._draw_start_pos = None

        # Minimum size threshold to prevent accidental clicks
        min_width = 0.2  # seconds
        min_height = 0.5 * self._get_scale_factor()
        if rect.width() < min_width or rect.height() < min_height:
            self._exit_draw_mode()
            return True

        # Clamp to plot bounds
        plot_bounds = self._get_plot_bounds()
        rect = rect.intersected(plot_bounds)
        if rect.isEmpty():
            self._exit_draw_mode()
            return True

        x_start = rect.left()
        x_end = rect.right()
        first_ch, last_ch = self._y_to_channel_range(
            min(rect.top(), rect.bottom()), max(rect.top(), rect.bottom())
        )
        montage_list = self._get_montage_list()
        selected_channels = montage_list[first_ch : last_ch + 1]

        if len(selected_channels) == 0:
            self._exit_draw_mode()
            return True

        # Sub-second time precision (no rounding); snap Y to whole channel bands.
        annotation_data = self._build_annotation_data(
            channels=selected_channels,
            start_time=x_start,
            stop_time=x_end,
            onset="BCKG",
        )

        y_bottom, height = self._channel_band(first_ch, last_ch)
        annotation_roi = AnnotationROI(
            pos=[x_start, y_bottom],
            size=[x_end - x_start, height],
            data=annotation_data,
            get_scale_factor=self._get_scale_factor,
        )

        self._create_editable_annotation_rect(annotation_roi)
        self._dirty = True

        if self._state:
            self._state.enable_undo_button.emit(True)

        # Exit draw mode after creating annotation
        self._exit_draw_mode()

        return True

    # ------------------------------------------------------------------
    # Annotation CRUD
    # ------------------------------------------------------------------

    def _create_editable_annotation_rect(
        self, annotation_roi: AnnotationROI, rebuild_index: bool = True
    ) -> AnnotationROI:
        """Create an editable annotation rectangle with event handlers.

        Pass rebuild_index=False during bulk rendering and rebuild the jump
        index once afterward, to avoid an O(N^2 log N) re-sort per insert.
        """

        # Restrict movement to plot boundaries
        annotation_roi.maxBounds = self._get_plot_bounds()

        # Connect signals for data synchronization
        annotation_roi.sigRegionChangeFinished.connect(
            lambda: self._on_annotation_moved(annotation_roi)
        )
        annotation_roi.sigRemoveRequested.connect(
            lambda: self._delete_annotation(annotation_roi)
        )
        annotation_roi.sigSelected.connect(self._select_annotation)
        annotation_roi.sigEdited.connect(self._on_annotation_edited)

        # Connect region changed signal to update text position during drag
        annotation_roi.sigRegionChanged.connect(
            lambda: self._update_annotation_text_position(annotation_roi)
        )

        self._plot_widget.addItem(annotation_roi)
        self._plot_widget.addItem(annotation_roi.text_item)

        self.annotation_items.append(annotation_roi)
        if rebuild_index:
            self._rebuild_jump_index()

        return annotation_roi

    def _disconnect_roi(self, roi: AnnotationROI) -> None:
        """Disconnect all signal handlers from an ROI before removing it."""
        roi.sigRegionChangeFinished.disconnect()
        roi.sigRemoveRequested.disconnect()
        roi.sigRegionChanged.disconnect()
        roi.sigSelected.disconnect()
        roi.sigEdited.disconnect()

    def _on_annotation_edited(self, annotation_roi: AnnotationROI):
        """Handle an in-place label edit: bump modified_at / reset review."""
        self._touch(annotation_roi.data)
        annotation_roi.refresh_status_style()
        self._dirty = True

    def _update_annotation_text_position(self, annotation_roi: AnnotationROI):
        """Update text position when annotation is moved."""
        if annotation_roi:
            pos = annotation_roi.pos()
            annotation_roi.text_item.setPos(pos[0], pos[1])

    def _on_annotation_moved(self, annotation_roi: AnnotationROI):
        """Synchronize annotation data after ROI move/resize is complete.

        Time (X) is kept at full float precision; channel coverage (Y) is
        re-snapped to whole channel bands so the rectangle visually matches the
        discrete channels it is recorded against.
        """
        pos = annotation_roi.pos()
        size = annotation_roi.size()

        x_start = pos[0]
        x_end = pos[0] + size[0]
        y_start = pos[1]
        y_end = pos[1] + size[1]

        first_ch, last_ch = self._y_to_channel_range(
            min(y_start, y_end), max(y_start, y_end)
        )
        montage_list = self._get_montage_list()
        selected_channels = montage_list[first_ch : last_ch + 1]

        # Re-band the ROI's Y geometry without re-triggering this handler.
        y_bottom, height = self._channel_band(first_ch, last_ch)
        annotation_roi.setPos((x_start, y_bottom), update=False)
        annotation_roi.setSize((size[0], height), update=False)
        annotation_roi.stateChanged(finish=False)
        self._update_annotation_text_position(annotation_roi)

        annotation_data = annotation_roi.data
        annotation_data["channels"] = selected_channels
        annotation_data["start_time"] = x_start
        annotation_data["stop_time"] = x_end
        self._touch(annotation_data)

        # Position changed — rebuild sorted index and reset cursor
        self._dirty = True
        self._jump_cursor = None
        self._rebuild_jump_index()

    def _delete_annotation(self, annotation_roi: AnnotationROI):
        """Delete annotation from both visual items and data."""
        if not annotation_roi:
            return

        # Disconnect signals before removal
        self._disconnect_roi(annotation_roi)

        # Remove from visual items (both rect and text)
        self._plot_widget.removeItem(annotation_roi.text_item)
        self._plot_widget.removeItem(annotation_roi)

        # Remove from annotation_items list
        if annotation_roi in self.annotation_items:
            self.annotation_items.remove(annotation_roi)

        # Clear selection if deleted annotation was selected
        if self.selected_annotation_roi is annotation_roi:
            self.selected_annotation_roi = None

        # Reset jump cursor if deleted annotation was the cursor
        if self._jump_cursor is annotation_roi:
            self._jump_cursor = None
        self._rebuild_jump_index()

        self._dirty = True

        # Disable undo button if no more annotations
        if len(self.annotation_items) == 0 and self._state:
            self._state.enable_undo_button.emit(False)

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
        if self._state:
            self._state.annotation_selected.emit(roi)

    def deselect_all(self):
        """Clear the current annotation selection."""
        if self.selected_annotation_roi:
            self.selected_annotation_roi.set_selected(False)
        self.selected_annotation_roi = None
        if self._state:
            self._state.annotation_selected.emit(None)

    # ------------------------------------------------------------------
    # Copy / paste
    # ------------------------------------------------------------------

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

        clip = self._clipboard_annotation
        montage_list = self._get_montage_list()

        # Validate channels exist in current montage
        valid_channels = [c for c in clip["channels"] if c in montage_list]
        if not valid_channels:
            return

        # Reposition: cursor X = start of pasted annotation, keep same duration
        # (full float precision, clamped to the recording bounds).
        duration = clip["stop_time"] - clip["start_time"]
        signal_duration = self._get_signal_duration()
        new_start = max(0.0, self._last_mouse_view_pos.x())
        new_end = new_start + duration
        if new_end > signal_duration:
            new_end = signal_duration
            new_start = max(0.0, new_end - duration)

        channel_index = self._get_channel_index()
        idx0 = channel_index.get(valid_channels[0])
        idx1 = channel_index.get(valid_channels[-1])
        if idx0 is None or idx1 is None:
            return
        first_ch, last_ch = min(idx0, idx1), max(idx0, idx1)

        # A paste is a newly authored region: fresh id + authorship, draft status.
        data = self._build_annotation_data(
            channels=valid_channels,
            start_time=new_start,
            stop_time=new_end,
            onset=clip["onset"],
        )

        y_bottom, height = self._channel_band(first_ch, last_ch)
        annotation_roi = AnnotationROI(
            pos=[new_start, y_bottom],
            size=[new_end - new_start, height],
            data=data,
            get_scale_factor=self._get_scale_factor,
        )
        self._create_editable_annotation_rect(annotation_roi)
        self._dirty = True

        if self._state:
            self._state.enable_undo_button.emit(True)

    # ------------------------------------------------------------------
    # Undo / persistence
    # ------------------------------------------------------------------

    def undo_annotation(self):
        """Remove the last annotation."""
        if len(self.annotation_items) == 0:
            if self._state:
                self._state.enable_undo_button.emit(False)
            return

        annotation_roi = self.annotation_items.pop()

        # Disconnect signals before removal
        self._disconnect_roi(annotation_roi)

        self._plot_widget.removeItem(annotation_roi.text_item)
        self._plot_widget.removeItem(annotation_roi)

        # Clear selection if deleted annotation was selected
        if self.selected_annotation_roi is annotation_roi:
            self.selected_annotation_roi = None

        # Reset jump cursor if undone annotation was the cursor
        if self._jump_cursor is annotation_roi:
            self._jump_cursor = None
        self._rebuild_jump_index()
        self._dirty = True

        # Disable undo button if no more annotations
        if len(self.annotation_items) == 0 and self._state:
            self._state.enable_undo_button.emit(False)

    def render_annotations(self, annotations: Optional[List[Dict]] = None):
        """Render all saved annotations on the plot as editable rectangles."""
        # Clear existing annotation items
        self.deselect_all()
        for annotation_roi in self.annotation_items:
            self._disconnect_roi(annotation_roi)
            self._plot_widget.removeItem(annotation_roi.text_item)
            self._plot_widget.removeItem(annotation_roi)

        if annotations is None:
            annotations = [
                annotation_roi.data for annotation_roi in self.annotation_items
            ]
        self.annotation_items.clear()

        channel_index = self._get_channel_index()

        # Re-render all annotations as editable
        for annotation_data in annotations:
            if len(annotation_data["channels"]) == 0:
                continue

            idx0 = channel_index.get(annotation_data["channels"][0])
            idx1 = channel_index.get(annotation_data["channels"][-1])
            if idx0 is None or idx1 is None:
                # Channel not in current montage, skip
                continue
            first_ch_idx, last_ch_idx = min(idx0, idx1), max(idx0, idx1)

            y_bottom, height = self._channel_band(first_ch_idx, last_ch_idx)

            x_start = annotation_data["start_time"]
            x_end = annotation_data["stop_time"]

            annotation_roi = AnnotationROI(
                pos=[x_start, y_bottom],
                size=[x_end - x_start, height],
                data=annotation_data,
                get_scale_factor=self._get_scale_factor,
            )
            self._create_editable_annotation_rect(annotation_roi, rebuild_index=False)

        self._rebuild_jump_index()
        self._jump_cursor = None
        self._dirty = False

    def refresh_styles(self):
        """Recolor every annotation border/label from its review status."""
        for roi in self.annotation_items:
            roi.refresh_status_style()

    def mark_saved(self):
        """Clear the dirty flag after a successful save."""
        self._dirty = False

    def get_annotations(self) -> List[Dict]:
        """Return all annotation dicts for persistence."""
        return [annotation_roi.data for annotation_roi in self.annotation_items]

    def load_annotations(self, annotations: List[Dict]):
        """Render annotations loaded from the persistence layer."""
        self.render_annotations(annotations)

        if len(self.annotation_items) > 0 and self._state:
            self._state.enable_undo_button.emit(True)

    # ------------------------------------------------------------------
    # Jump navigation
    # ------------------------------------------------------------------

    def _rebuild_jump_index(self):
        """Rebuild the sorted annotation index used for jump navigation."""
        self._sorted_annotations = sorted(
            ((roi.data["start_time"], roi) for roi in self.annotation_items),
            key=lambda t: t[0],
        )

    def _filtered_sorted_annotations(self, label: str) -> list:
        """Return sorted annotations filtered by label ('ALL' returns all)."""
        if label == "ALL":
            return self._sorted_annotations
        return [
            (t, roi)
            for t, roi in self._sorted_annotations
            if roi.data["onset"] == label
        ]

    def _jump_to_annotation(self, roi: AnnotationROI):
        self._jump_cursor = roi
        self._goto_time(roi.data["start_time"])

    def jump_to_nearest(self, label: str):
        """Jump to the annotation nearest to the current view center."""
        candidates = self._filtered_sorted_annotations(label)
        if not candidates:
            return
        view_range = self._plot_widget.viewRange()
        view_center = sum(view_range[0]) / 2.0
        starts = [t for t, _ in candidates]
        idx = bisect.bisect_left(starts, view_center)
        best_roi, best_dist = None, float("inf")
        for i in (idx - 1, idx):
            if 0 <= i < len(candidates):
                dist = abs(candidates[i][0] - view_center)
                if dist < best_dist:
                    best_dist, best_roi = dist, candidates[i][1]
        if best_roi:
            self._jump_to_annotation(best_roi)

    def jump_to_next(self, label: str):
        self._jump_in_direction(label, forward=True)

    def jump_to_prev(self, label: str):
        self._jump_in_direction(label, forward=False)

    def _jump_in_direction(self, label: str, forward: bool):
        candidates = self._filtered_sorted_annotations(label)
        if not candidates:
            return
        if self._jump_cursor is None:
            self.jump_to_nearest(label)
            return
        starts = [t for t, _ in candidates]
        cur_start = self._jump_cursor.data["start_time"]
        if forward:
            idx = bisect.bisect_right(starts, cur_start)
            if idx < len(candidates):
                self._jump_to_annotation(candidates[idx][1])
        else:
            idx = bisect.bisect_left(starts, cur_start) - 1
            if idx >= 0:
                self._jump_to_annotation(candidates[idx][1])

    def _on_jump_label_changed(self, label: str):
        """Update the active jump label filter."""
        self._jump_label = label

    def _on_jump_requested(self):
        """Handle Jump button press — jump to nearest matching annotation."""
        self.jump_to_nearest(self._jump_label)

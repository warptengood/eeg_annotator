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


from typing import Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

class AppState(QObject):
    scale_changed = pyqtSignal()
    montage_changed = pyqtSignal()
    montage_list_changed = pyqtSignal()
    filter_changed = pyqtSignal()
    
    label_clicked = pyqtSignal()
    draw_mode_changed = pyqtSignal(bool)
    spinner_value_changed = pyqtSignal(int)
    goto_input_return_pressed = pyqtSignal(int)
    undo_clicked = pyqtSignal()
    enable_undo_button = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._montage_name = 'AVERAGE'
        self._filter = (None, None)
        self._montage_list = []
        self._scale = 0

    def set_montage_list(self, montage_list):
        if montage_list != self._montage_list:
            self._montage_list = montage_list
            self.montage_list_changed.emit()

    @property
    def montage_list(self):
        return self._montage_list

    def set_montage(self, montage_name):
        if montage_name != self._montage_name:
            self._montage_name = montage_name
            self.montage_changed.emit()
    
    @property
    def montage_name(self) -> str:
        return self._montage_name

    def set_filter(self, filter):
        if filter != self._filter:
            self._filter = filter
            self.filter_changed.emit()
    
    @property
    def filter(self) -> Tuple[Optional[float], Optional[float]]:
        return self._filter
    
    def set_scale(self, scale):
        if scale != self._scale:
            self._scale = scale
            self.scale_changed.emit()
    
    @property
    def scale(self) -> int:
        return self._scale
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


import sys
from typing import Union
from pathlib import Path

def resource_path(relative_path: Path, to_string: bool = False) -> Union[Path, str]:
    """Get path to resource file, handling both development and PyInstaller bundle.

    Args:
        relative_path: Path relative to project root (e.g., 'resources/icons/file.png')
        to_string: If True, return string instead of Path object

    Returns:
        Absolute path to resource
    """
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller bundle - resources are in _MEIPASS
        base_path = Path(sys._MEIPASS)
    else:
        # Development - go up two levels from src/utils/ to project root
        base_path = Path(__file__).resolve().parent.parent.parent

    final_path = base_path / relative_path

    if to_string:
        return str(final_path)

    return final_path
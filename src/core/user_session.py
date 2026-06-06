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

"""Honor-system current-user identity, persisted via QSettings.

There is no enforced login. We capture a display name and a role (labeler vs
expert) once, persist it across launches, and let the user edit it later. The
role gates the expert review UI; it is not a security boundary.
"""

from PyQt6.QtCore import QSettings

ROLE_LABELER = "labeler"
ROLE_EXPERT = "expert"
ROLES = (ROLE_LABELER, ROLE_EXPERT)

_ORG = "Ziyatron"
_APP = "EEGAnnotator"


class UserSession:
    """Reads/writes the current user's name and role from persistent settings."""

    def __init__(self) -> None:
        self._settings = QSettings(_ORG, _APP)
        self._name = self._settings.value("user/name", "", type=str) or ""
        role = self._settings.value("user/role", ROLE_LABELER, type=str)
        self._role = role if role in ROLES else ROLE_LABELER

    @property
    def name(self) -> str:
        return self._name

    @property
    def role(self) -> str:
        return self._role

    @property
    def is_expert(self) -> bool:
        return self._role == ROLE_EXPERT

    @property
    def is_configured(self) -> bool:
        """True once a non-empty name has been stored (first-run check)."""
        return bool(self._name.strip())

    def set_identity(self, name: str, role: str) -> None:
        """Persist a new name/role. Falls back to labeler for unknown roles."""
        self._name = name.strip()
        self._role = role if role in ROLES else ROLE_LABELER
        self._settings.setValue("user/name", self._name)
        self._settings.setValue("user/role", self._role)
        self._settings.sync()

    def label(self) -> str:
        """Compact read-out, e.g. ``'aigerim (labeler)'``."""
        name = self._name or "unknown"
        return f"{name} ({self._role})"

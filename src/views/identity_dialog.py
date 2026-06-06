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

"""Honor-system identity prompt (name + role), shared by first-run and toolbar."""

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
)

from src.core.user_session import ROLE_EXPERT, ROLE_LABELER

# (display label, stored role) pairs for the role combo.
_ROLE_CHOICES = (("Labeler", ROLE_LABELER), ("Expert", ROLE_EXPERT))


class IdentityDialog(QDialog):
    """Collects a display name and a role (labeler / expert)."""

    def __init__(self, name: str = "", role: str = ROLE_LABELER, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Who are you?")

        self._name_edit = QLineEdit(name)
        self._name_edit.setPlaceholderText("Your name")

        self._role_combo = QComboBox()
        for label, value in _ROLE_CHOICES:
            self._role_combo.addItem(label, value)
        for i, (_, value) in enumerate(_ROLE_CHOICES):
            if value == role:
                self._role_combo.setCurrentIndex(i)
                break

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QFormLayout()
        layout.addRow("Name:", self._name_edit)
        layout.addRow("Role:", self._role_combo)
        layout.addRow(buttons)
        self.setLayout(layout)

    @property
    def name(self) -> str:
        return self._name_edit.text().strip()

    @property
    def role(self) -> str:
        return self._role_combo.currentData()


def prompt_identity(user_session, parent=None, require: bool = False) -> bool:
    """Show the identity dialog and persist the result.

    Returns True if an identity was set. When ``require`` is True (first run),
    the dialog re-prompts until a non-empty name is provided or the user cancels.
    """
    while True:
        dialog = IdentityDialog(
            name=user_session.name, role=user_session.role, parent=parent
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        if dialog.name:
            user_session.set_identity(dialog.name, dialog.role)
            return True
        if not require:
            return False
        # require=True and empty name -> loop and ask again

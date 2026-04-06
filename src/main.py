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
import logging
from PyQt6.QtWidgets import QApplication

from src.views.main_window import EEGAnnotator


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('eeg_annotator.log'),
        logging.StreamHandler()
    ]
)


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("Ziyatron EEG Annotator")
    app.setOrganizationName("Ziyatron")
    app.setApplicationVersion("2.0.0")

    window = EEGAnnotator()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

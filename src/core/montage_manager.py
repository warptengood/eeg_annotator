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


import os
import re
from dataclasses import dataclass

import yaml

from src.utils.path_utils import resource_path


@dataclass
class Montage:
    type: str
    name: str
    configuration: dict

class MontageManager:
    """Manages loading and accessing EEG montage configurations from YAML files."""

    def __init__(self):
        self.montages_path = resource_path('resources/montages')
        self.montages = {}

        for montage_type_entry in os.scandir(self.montages_path):
            if montage_type_entry.is_dir():
                for montage_name_entry in os.scandir(montage_type_entry.path):
                    if montage_name_entry.name.endswith('.yaml'):
                        montage_type = montage_type_entry.name
                        montage_name = montage_name_entry.name.replace('.yaml', '').replace('_', ' ').upper()
                        self.montages[montage_name] = self._load_montage(montage_type, montage_name)

        self.channel_patterns = {
            'REF': re.compile(r"^EEG .+-A\d{1,2}$"),
            'AV': re.compile(r"^EEG .+-AV$"),
        }

    def _load_montage(self, montage_type: str, montage_name: str) -> Montage:
        """Load montage configuration from YAML file.

        Args:
            montage_type: Type of montage (e.g., 'bipolar')
            montage_name: Name of montage (e.g., 'BIPOLAR_DOUBLE_BANANA')

        Returns:
            Montage object
        """
        montage_filename = montage_name.replace(' ', '_').lower() + '.yaml'
        montage_path = os.path.join(self.montages_path, montage_type, montage_filename)

        with open(montage_path, 'r') as file:
            configuration = yaml.safe_load(file)

        return Montage(montage_type, montage_name, configuration)

    def get_montage(self, montage_name: str) -> Montage:
        """Get montage configuration by name.

        Args:
            montage_name: Name of montage

        Returns:
            Montage

        Raises:
            KeyError: If montage type doesn't exist
        """
        if montage_name in self.montages:
            return self.montages[montage_name]
        else:
            raise KeyError(f"Non-existent montage type: {montage_name}")

    def get_monopolar_type(self, channel_list: list[str]) -> str | None:
        for pattern_type, pattern in self.channel_patterns.items():
            if all(pattern.match(name) for name in channel_list):
                return pattern_type
        return None

# Global singleton instance
montage_manager = MontageManager()

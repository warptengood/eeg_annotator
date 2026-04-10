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


from pathlib import Path
from typing import Union, Tuple, Optional, Dict
from collections import OrderedDict
import logging

import mne
import numpy as np

from src.core.montage_manager import montage_manager


logger = logging.getLogger(__name__)


class EEGDataStreamer:
    """Memory-efficient EEG data manager using lazy loading and windowed caching.

    This class loads EEG data on-demand in small time windows rather than loading
    entire files into memory. Implements LRU caching for recently accessed windows.

    Key improvements over full preload:
    - 100MB file: ~30-50MB RAM (vs 400-500MB with full preload)
    - Only loads visible time windows (6-10 seconds)
    - Caches up to 5 recent windows for smooth navigation
    - Applies montage/filter transformations on small windows only
    """

    MAX_CACHE_SIZE = 5  # Maximum number of windows to cache

    def __init__(self):
        self.raw_handle: Optional[mne.io.Raw] = None
        self.window_cache: OrderedDict = OrderedDict()
        self.metadata: Dict = {}
        self.filename: Optional[Path] = None
        self.current_montage: Optional[str] = None
        self.current_filter: Tuple[Optional[float], Optional[float]] = (None, None)
        self._monopolar_type: Optional[str] = None

    def open_edf(self, filename: Union[str, Path]) -> None:
        """Open EDF file handle without loading data into memory.

        Args:
            filename: Path to EDF file

        Raises:
            FileNotFoundError: If file doesn't exist
            RuntimeError: If file cannot be opened by MNE
        """
        self.filename = Path(filename)

        if not self.filename.exists():
            raise FileNotFoundError(f"EDF file not found: {filename}")

        try:
            # CRITICAL: preload=False keeps file on disk, only loads metadata
            self.raw_handle = mne.io.read_raw_edf(filename, preload=False, verbose=False)

            # Store metadata only (minimal memory footprint)
            self.metadata = {
                'sfreq': self.raw_handle.info['sfreq'],
                'duration': self.raw_handle.times[-1],
                'n_channels': len(self.raw_handle.ch_names),
                'ch_names': self.raw_handle.ch_names.copy(),
            }

            # Clear cache when opening new file
            self.window_cache.clear()

            # Cache monopolar type (static per file, avoids regex on every window load)
            eeg_channels = [ch for ch in self.metadata['ch_names'] if ch.startswith('EEG')]
            self._monopolar_type = montage_manager.get_monopolar_type(eeg_channels)

            logger.info(
                f"Opened EDF: {filename} "
                f"({self.metadata['n_channels']} channels, "
                f"{self.metadata['duration']:.1f}s @ {self.metadata['sfreq']}Hz)"
            )

        except Exception as e:
            raise RuntimeError(f"Failed to open EDF file {filename}: {e}")

    def get_window(
        self,
        start_time: float,
        duration: float,
        montage_name: str,
        filter_params: Tuple[Optional[float], Optional[float]],
        buffer_seconds: float = 2.0
    ) -> mne.io.Raw:
        """Load and return a small time window of EEG data.

        This is the core method for lazy loading. Only loads the requested time
        window plus a small buffer. Applies montage and filter transformations
        on this small window only.

        Args:
            start_time: Start time in seconds
            duration: Window duration in seconds (typically 6-10s)
            montage: Montage type (e.g., 'AVERAGE', 'BIPOLAR DOUBLE BANANA')
            filter_params: Tuple of (low_freq, high_freq) for filtering
            buffer_seconds: Extra seconds to load beyond window for smooth panning

        Returns:
            MNE Raw object containing only the requested time window

        Raises:
            RuntimeError: If no file is open or window cannot be loaded
        """
        if self.raw_handle is None:
            raise RuntimeError("No EDF file is open. Call open_edf() first.")

        # Create cache key for this exact window configuration
        cache_key = (start_time, duration, montage_name, tuple(filter_params))

        # Return cached window if available
        if cache_key in self.window_cache:
            # Move to end (most recently used)
            self.window_cache.move_to_end(cache_key)
            logger.debug(f"Cache hit for window at {start_time}s")
            return self.window_cache[cache_key]

        # Calculate window boundaries with buffer
        tmin = max(0, start_time)
        tmax = min(self.metadata['duration'], start_time + duration + buffer_seconds)

        logger.debug(f"Loading window: {tmin:.2f}s to {tmax:.2f}s")

        try:
            # Load ONLY this time window from disk
            window_data = self.raw_handle.copy().crop(tmin=tmin, tmax=tmax)
            window_data.load_data()  # Load only this small window into memory

            # Apply montage transformation on small window
            window_data = self._apply_montage(window_data, montage_name)

            # Apply filter on small window
            window_data = self._apply_filter(window_data, filter_params)

            # Cache with LRU eviction
            self.window_cache[cache_key] = window_data

            # Evict oldest window if cache exceeds limit
            if len(self.window_cache) > self.MAX_CACHE_SIZE:
                removed_key = next(iter(self.window_cache))
                del self.window_cache[removed_key]
                logger.debug(f"Evicted window from cache (size: {self.MAX_CACHE_SIZE})")

            return window_data

        except Exception as e:
            raise RuntimeError(f"Failed to load window at {start_time}s: {e}")

    def _apply_montage(self, raw: mne.io.Raw, montage_name: str) -> mne.io.Raw:
        """Apply montage transformation to raw data.

        Args:
            raw: MNE Raw object
            montage: Montage type

        Returns:
            Transformed Raw object with montage applied
        """
        montage = montage_manager.get_montage(montage_name)
        if montage.type == 'monopolar':
            try:
                electrodes = [channels[0] for channels in montage.configuration.values()]
                raw.pick(electrodes)
                raw.rename_channels({channels[0]: ch_name for ch_name, channels in montage.configuration.items()})
            except Exception as e:
                logger.exception(f"Montage configuration error: {e}")
                # Return unmodified if montage fails
        elif montage.type == 'bipolar':
            try:
                if self._monopolar_type:
                    ch_name, anode, cathode = [], [], []
                    for conf_ch_name, conf_monopolar_types in montage.configuration.items():
                        ch_name.append(conf_ch_name)
                        anode.append(conf_monopolar_types[self._monopolar_type][0])
                        cathode.append(conf_monopolar_types[self._monopolar_type][1])
                    raw = mne.set_bipolar_reference(
                        raw,
                        anode=anode,
                        cathode=cathode,
                        ch_name=ch_name,
                        drop_refs=True,
                        copy=False,  # Modify in-place to save memory
                        verbose=False,
                    )
                    raw.pick(ch_name)

            except Exception as e:
                logger.exception(f"Montage configuration error: {e}")
                # Return unmodified if montage fails
        return raw

    def _apply_filter(
        self,
        raw: mne.io.Raw,
        filter_params: Tuple[Optional[float], Optional[float]]
    ) -> mne.io.Raw:
        """Apply frequency filter to raw data.

        Args:
            raw: MNE Raw object
            filter_params: Tuple of (low_freq, high_freq)

        Returns:
            Filtered Raw object
        """
        l_freq, h_freq = filter_params

        # Only filter if at least one frequency is specified
        if l_freq is not None or h_freq is not None:
            try:
                raw.filter(l_freq=l_freq, h_freq=h_freq, verbose=False)
            except Exception as e:
                logger.warning(f"Filter failed ({l_freq}, {h_freq}Hz): {e}")
                # Return unfiltered if filter fails

        return raw

    def get_metadata(self) -> Dict:
        """Get file metadata without loading data.

        Returns:
            Dictionary with sfreq, duration, n_channels, ch_names
        """
        if not self.metadata:
            raise RuntimeError("No file opened")
        return self.metadata.copy()

    def get_duration(self) -> float:
        """Get total duration of recording in seconds."""
        return self.metadata.get('duration', 0.0)

    def get_sfreq(self) -> float:
        """Get sampling frequency in Hz."""
        return self.metadata.get('sfreq', 0.0)

    def get_channel_names(self) -> list:
        """Get list of channel names."""
        return self.metadata.get('ch_names', []).copy()

    def clear_cache(self) -> None:
        """Clear all cached windows (e.g., when montage/filter changes)."""
        self.window_cache.clear()
        logger.debug("Cleared window cache")

    def close(self) -> None:
        """Close file handle and free resources."""
        if self.raw_handle is not None:
            self.raw_handle.close()
            self.raw_handle = None

        self.window_cache.clear()
        self.metadata.clear()
        logger.info("Closed EDF file")

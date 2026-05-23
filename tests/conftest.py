import shutil
from pathlib import Path

import pytest

from src.models.app_state import AppState
from src.core.data_streamer import EEGDataStreamer
from src.core.montage_manager import montage_manager


@pytest.fixture
def app_state(qapp):
    return AppState()


@pytest.fixture
def data_streamer():
    return EEGDataStreamer()


@pytest.fixture(scope="session")
def edf_files():
    data_dir = Path(__file__).parent / "data"
    return sorted(data_dir.glob("*.edf"))


def _detect_scheme(path: Path) -> str | None:
    """Open EDF, extract EEG channel names, return 'AV', 'REF', or None."""
    import mne
    raw = mne.io.read_raw_edf(str(path), preload=False, verbose=False)
    eeg_ch = [ch for ch in raw.ch_names if ch.startswith("EEG")]
    raw.close()
    return montage_manager.get_monopolar_type(eeg_ch)


@pytest.fixture(scope="session")
def edf_av(edf_files):
    for p in edf_files:
        if _detect_scheme(p) == "AV":
            return p
    pytest.skip("No -AV EDF file found in tests/data/")


@pytest.fixture(scope="session")
def edf_ref(edf_files):
    for p in edf_files:
        if _detect_scheme(p) == "REF":
            return p
    pytest.skip("No -A1/-A2 EDF file found in tests/data/")


@pytest.fixture
def tmp_edf_copy(edf_av, tmp_path):
    """Copy the AV EDF to a tmp dir so CSV side-effects don't pollute tests/data/."""
    dest = tmp_path / edf_av.name
    shutil.copy2(edf_av, dest)
    return dest

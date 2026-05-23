import pytest

from src.core.data_streamer import EEGDataStreamer

pytestmark = pytest.mark.needs_edf


# ---------------------------------------------------------------------------
# open_edf
# ---------------------------------------------------------------------------


def test_open_edf_missing_path_raises():
    ds = EEGDataStreamer()
    with pytest.raises(FileNotFoundError):
        ds.open_edf("/nonexistent/path/file.edf")


def test_open_edf_populates_metadata(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    meta = ds.metadata
    assert "sfreq" in meta
    assert "duration" in meta
    assert "n_channels" in meta
    assert "ch_names" in meta
    assert meta["sfreq"] > 0
    assert meta["duration"] > 0
    assert meta["n_channels"] > 0
    assert len(meta["ch_names"]) == meta["n_channels"]
    ds.close()


def test_open_edf_detects_av_type(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    assert ds._monopolar_type == "AV"
    ds.close()


def test_open_edf_detects_ref_type(edf_ref):
    ds = EEGDataStreamer()
    ds.open_edf(edf_ref)
    assert ds._monopolar_type == "REF"
    ds.close()


# ---------------------------------------------------------------------------
# get_window without open file
# ---------------------------------------------------------------------------


def test_get_window_before_open_raises():
    ds = EEGDataStreamer()
    with pytest.raises(RuntimeError, match="No EDF file is open"):
        ds.get_window(0.0, 10.0, "AVERAGE", (None, None))


# ---------------------------------------------------------------------------
# get_window content / quantization
# ---------------------------------------------------------------------------


def test_get_window_returns_raw(edf_av):
    import mne

    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    raw = ds.get_window(0.0, 10.0, "AVERAGE", (None, None))
    assert isinstance(raw, mne.io.BaseRaw)
    ds.close()


def test_get_window_duration_approximate(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    raw = ds.get_window(0.0, 10.0, "AVERAGE", (None, None), buffer_seconds=2.0)
    # duration should be roughly 10s + 2s buffer (clamped to file end)
    file_duration = ds.metadata["duration"]
    expected = min(12.0, file_duration)
    assert abs(raw.times[-1] - expected) < 1.0
    ds.close()


def test_get_window_start_time_quantization(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    # Two calls differing by < 0.5s should share a cache entry
    ds.get_window(0.0, 10.0, "AVERAGE", (None, None))
    assert len(ds.window_cache) == 1
    ds.get_window(0.1, 10.0, "AVERAGE", (None, None))  # 0.1 quantizes to 0.0
    assert len(ds.window_cache) == 1
    ds.close()


def test_get_window_duration_quantization(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    ds.get_window(0.0, 10.0, "AVERAGE", (None, None))
    ds.get_window(0.0, 10.2, "AVERAGE", (None, None))  # 10.2 quantizes to 10.0
    assert len(ds.window_cache) == 1
    ds.close()


# ---------------------------------------------------------------------------
# LRU cache behaviour
# ---------------------------------------------------------------------------


def test_lru_cache_hit_same_object(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    raw1 = ds.get_window(0.0, 10.0, "AVERAGE", (None, None))
    raw2 = ds.get_window(0.0, 10.0, "AVERAGE", (None, None))
    assert raw1 is raw2
    ds.close()


def test_lru_cache_max_size(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    file_duration = ds.metadata["duration"]
    # Load MAX_CACHE_SIZE + 1 distinct windows; ensure cache never exceeds limit
    step = 0.5
    for i in range(EEGDataStreamer.MAX_CACHE_SIZE + 1):
        start = i * step
        if start + step > file_duration:
            pytest.skip("EDF too short to fill cache")
        ds.get_window(start, step, "AVERAGE", (None, None), buffer_seconds=0.0)
    assert len(ds.window_cache) <= EEGDataStreamer.MAX_CACHE_SIZE
    ds.close()


def test_lru_evicts_oldest(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    file_duration = ds.metadata["duration"]
    step = 0.5
    keys_loaded = []
    for i in range(EEGDataStreamer.MAX_CACHE_SIZE + 1):
        start = i * step
        if start + step > file_duration:
            pytest.skip("EDF too short to fill cache + 1")
        ds.get_window(start, step, "AVERAGE", (None, None), buffer_seconds=0.0)
        keys_loaded.append(start)
    # Oldest key should have been evicted
    oldest_key = (
        round(keys_loaded[0] / 0.5) * 0.5,
        round(step / 0.5) * 0.5,
        "AVERAGE",
        (None, None),
    )
    assert oldest_key not in ds.window_cache
    ds.close()


# ---------------------------------------------------------------------------
# clear_cache
# ---------------------------------------------------------------------------


def test_clear_cache_empties(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    ds.get_window(0.0, 10.0, "AVERAGE", (None, None))
    assert len(ds.window_cache) == 1
    ds.clear_cache()
    assert len(ds.window_cache) == 0
    ds.close()


def test_different_montage_produces_different_key(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    ds.get_window(0.0, 10.0, "AVERAGE", (None, None))
    ds.get_window(0.0, 10.0, "REFERENTIAL", (None, None))
    assert len(ds.window_cache) == 2
    ds.close()


def test_different_filter_produces_different_key(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    ds.get_window(0.0, 10.0, "AVERAGE", (None, None))
    ds.get_window(0.0, 10.0, "AVERAGE", (1.0, 40.0))
    assert len(ds.window_cache) == 2
    ds.close()


# ---------------------------------------------------------------------------
# Montage application
# ---------------------------------------------------------------------------


def test_monopolar_average_montage_on_av_file(edf_av):
    from src.core.montage_manager import montage_manager

    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    raw = ds.get_window(0.0, 10.0, "AVERAGE", (None, None))
    expected_names = set(montage_manager.get_montage("AVERAGE").configuration.keys())
    actual_names = set(raw.ch_names)
    assert expected_names == actual_names
    ds.close()


def test_bipolar_montage_on_av_file(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    from src.core.montage_manager import montage_manager

    bipolar_names = set(
        montage_manager.get_montage("BIPOLAR DOUBLE BANANA").configuration.keys()
    )
    raw = ds.get_window(0.0, 10.0, "BIPOLAR DOUBLE BANANA", (None, None))
    assert set(raw.ch_names) == bipolar_names
    ds.close()


def test_bipolar_montage_on_ref_file(edf_ref):
    ds = EEGDataStreamer()
    ds.open_edf(edf_ref)
    from src.core.montage_manager import montage_manager

    bipolar_names = set(
        montage_manager.get_montage("BIPOLAR DOUBLE BANANA").configuration.keys()
    )
    raw = ds.get_window(0.0, 10.0, "BIPOLAR DOUBLE BANANA", (None, None))
    assert set(raw.ch_names) == bipolar_names
    ds.close()


# ---------------------------------------------------------------------------
# _apply_filter
# ---------------------------------------------------------------------------


def test_apply_filter_none_is_noop(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    raw = ds.raw_handle.copy().crop(tmin=0, tmax=min(5.0, ds.metadata["duration"]))
    raw.load_data()
    original_ch_names = raw.ch_names[:]
    result = ds._apply_filter(raw, (None, None))
    assert result.ch_names == original_ch_names
    ds.close()


def test_apply_filter_bandpass_runs(edf_av):
    import mne

    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    raw = ds.raw_handle.copy().crop(tmin=0, tmax=min(5.0, ds.metadata["duration"]))
    raw.load_data()
    result = ds._apply_filter(raw, (1.0, 40.0))
    assert isinstance(result, mne.io.BaseRaw)
    ds.close()


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


def test_close_resets_state(edf_av):
    ds = EEGDataStreamer()
    ds.open_edf(edf_av)
    ds.get_window(0.0, 10.0, "AVERAGE", (None, None))
    ds.close()
    assert ds.raw_handle is None
    assert len(ds.window_cache) == 0
    assert len(ds.metadata) == 0

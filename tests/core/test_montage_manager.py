import pytest

from src.core.montage_manager import MontageManager, montage_manager


EXPECTED_MONTAGES = {
    "AVERAGE",
    "CENTRAL SAGITTAL",
    "REFERENTIAL",
    "BIPOLAR CIRCUMFERENTIAL",
    "BIPOLAR DOUBLE BANANA",
    "BIPOLAR TRANSVERSE",
}


class TestGetMonopolarType:
    def test_av_channels(self):
        channels = ["EEG FP1-AV", "EEG F7-AV", "EEG T3-AV"]
        assert montage_manager.get_monopolar_type(channels) == "AV"

    def test_ref_channels_a1(self):
        channels = ["EEG FP1-A1", "EEG F7-A1", "EEG T3-A1"]
        assert montage_manager.get_monopolar_type(channels) == "REF"

    def test_ref_channels_a2(self):
        channels = ["EEG FP1-A2", "EEG F7-A2"]
        assert montage_manager.get_monopolar_type(channels) == "REF"

    def test_mixed_returns_none(self):
        channels = ["EEG FP1-AV", "EEG F7-A1"]
        assert montage_manager.get_monopolar_type(channels) is None

    def test_empty_list_returns_none(self):
        assert montage_manager.get_monopolar_type([]) is None

    def test_non_eeg_names_return_none(self):
        channels = ["EMG CH1", "EOG Left", "EKG"]
        assert montage_manager.get_monopolar_type(channels) is None

    def test_single_av_channel(self):
        assert montage_manager.get_monopolar_type(["EEG FP1-AV"]) == "AV"

    def test_single_ref_channel(self):
        assert montage_manager.get_monopolar_type(["EEG FP1-A1"]) == "REF"


class TestGetMontage:
    def test_known_monopolar_montage(self):
        m = montage_manager.get_montage("AVERAGE")
        assert m.type == "monopolar"
        assert m.name == "AVERAGE"
        assert isinstance(m.configuration, dict)
        assert len(m.configuration) > 0

    def test_known_bipolar_montage(self):
        m = montage_manager.get_montage("BIPOLAR DOUBLE BANANA")
        assert m.type == "bipolar"
        assert m.name == "BIPOLAR DOUBLE BANANA"

    def test_referential_is_monopolar(self):
        m = montage_manager.get_montage("REFERENTIAL")
        assert m.type == "monopolar"

    def test_unknown_name_raises_key_error(self):
        with pytest.raises(KeyError):
            montage_manager.get_montage("NONEXISTENT MONTAGE")


class TestStartupScan:
    def test_all_expected_montages_loaded(self):
        loaded = set(montage_manager.montages.keys())
        assert EXPECTED_MONTAGES.issubset(loaded), (
            f"Missing montages: {EXPECTED_MONTAGES - loaded}"
        )

    def test_display_name_transform(self):
        # bipolar_double_banana.yaml → BIPOLAR DOUBLE BANANA
        assert "BIPOLAR DOUBLE BANANA" in montage_manager.montages
        assert "BIPOLAR CIRCUMFERENTIAL" in montage_manager.montages
        assert "BIPOLAR TRANSVERSE" in montage_manager.montages
        assert "CENTRAL SAGITTAL" in montage_manager.montages

    def test_montage_configurations_are_dicts(self):
        for name, montage in montage_manager.montages.items():
            assert isinstance(montage.configuration, dict), (
                f"Montage {name!r} has non-dict configuration"
            )

    def test_montage_types_are_valid(self):
        valid_types = {"monopolar", "bipolar"}
        for name, montage in montage_manager.montages.items():
            assert montage.type in valid_types, (
                f"Montage {name!r} has invalid type {montage.type!r}"
            )

    def test_fresh_instance_loads_same_montages(self):
        fresh = MontageManager()
        assert set(fresh.montages.keys()) == set(montage_manager.montages.keys())

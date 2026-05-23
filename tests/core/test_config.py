from src.core.config import config


def test_diagnosis_is_nonempty_list():
    assert isinstance(config.diagnosis, list)
    assert len(config.diagnosis) > 0


def test_diagnosis_labels_are_unique():
    assert len(config.diagnosis) == len(set(config.diagnosis))


def test_diagnosis_labels_are_strings():
    for label in config.diagnosis:
        assert isinstance(label, str), f"Non-string label: {label!r}"


def test_app_name_exists_and_is_str():
    assert hasattr(config, "app_name")
    assert isinstance(config.app_name, str)


def test_pan_ammount_exists_and_is_int():
    assert hasattr(config, "pan_ammount")
    assert isinstance(config.pan_ammount, int)

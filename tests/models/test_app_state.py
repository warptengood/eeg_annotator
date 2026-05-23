import pytest
from PyQt6.QtTest import QSignalSpy

from src.models.app_state import AppState


@pytest.fixture
def state(qapp):
    return AppState()


class TestSetMontage:
    def test_emits_on_change(self, state):
        spy = QSignalSpy(state.montage_changed)
        state.set_montage("REFERENTIAL")
        assert len(spy) == 1

    def test_no_emit_when_same_value(self, state):
        state.set_montage("AVERAGE")  # initial value
        spy = QSignalSpy(state.montage_changed)
        state.set_montage("AVERAGE")
        assert len(spy) == 0

    def test_updates_property(self, state):
        state.set_montage("BIPOLAR DOUBLE BANANA")
        assert state.montage_name == "BIPOLAR DOUBLE BANANA"


class TestSetFilter:
    def test_emits_on_change(self, state):
        spy = QSignalSpy(state.filter_changed)
        state.set_filter((1.0, 40.0))
        assert len(spy) == 1

    def test_no_emit_when_same_value(self, state):
        state.set_filter((1.0, 40.0))
        spy = QSignalSpy(state.filter_changed)
        state.set_filter((1.0, 40.0))
        assert len(spy) == 0

    def test_updates_property(self, state):
        state.set_filter((0.5, 70.0))
        assert state.filter == (0.5, 70.0)

    def test_none_filter(self, state):
        state.set_filter((None, None))
        assert state.filter == (None, None)


class TestSetScale:
    def test_emits_on_change(self, state):
        spy = QSignalSpy(state.scale_changed)
        state.set_scale(50)
        assert len(spy) == 1

    def test_no_emit_when_same_value(self, state):
        state.set_scale(0)  # initial value
        spy = QSignalSpy(state.scale_changed)
        state.set_scale(0)
        assert len(spy) == 0

    def test_updates_property(self, state):
        state.set_scale(100)
        assert state.scale == 100


class TestSetMontageList:
    def test_emits_on_change(self, state):
        spy = QSignalSpy(state.montage_list_changed)
        state.set_montage_list(["AVERAGE", "REFERENTIAL"])
        assert len(spy) == 1

    def test_no_emit_when_same_value(self, state):
        state.set_montage_list(["AVERAGE"])
        spy = QSignalSpy(state.montage_list_changed)
        state.set_montage_list(["AVERAGE"])
        assert len(spy) == 0

    def test_updates_property(self, state):
        state.set_montage_list(["AVERAGE", "REFERENTIAL"])
        assert state.montage_list == ["AVERAGE", "REFERENTIAL"]

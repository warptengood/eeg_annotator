import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication

from src.models.app_state import AppState
from src.views.control_toolbar import ControlToolBar


@pytest.fixture
def state(qapp):
    return AppState()


@pytest.fixture
def toolbar(state, qtbot):
    tb = ControlToolBar(state)
    qtbot.addWidget(tb)
    return tb


# ---------------------------------------------------------------------------
# File operation buttons
# ---------------------------------------------------------------------------

def test_open_file_button_emits_signal(toolbar, qtbot):
    spy = QSignalSpy(toolbar.open_file_clicked)
    qtbot.mouseClick(toolbar.open_file, Qt.MouseButton.LeftButton)
    assert len(spy) == 1


def test_save_button_emits_signal(toolbar, qtbot, state):
    # Enable save button first
    toolbar.save_btn.setEnabled(True)
    spy = QSignalSpy(toolbar.save_clicked)
    qtbot.mouseClick(toolbar.save_btn, Qt.MouseButton.LeftButton)
    assert len(spy) == 1


# ---------------------------------------------------------------------------
# Undo and label buttons
# ---------------------------------------------------------------------------

def test_undo_button_emits_state_signal(toolbar, qtbot, state):
    toolbar.undo_btn.setEnabled(True)
    spy = QSignalSpy(state.undo_clicked)
    qtbot.mouseClick(toolbar.undo_btn, Qt.MouseButton.LeftButton)
    assert len(spy) == 1


def test_label_button_emits_state_signal(toolbar, qtbot, state):
    toolbar.label_btn.setEnabled(True)
    spy = QSignalSpy(state.label_clicked)
    qtbot.mouseClick(toolbar.label_btn, Qt.MouseButton.LeftButton)
    assert len(spy) == 1


def test_label_button_is_checkable(toolbar):
    assert toolbar.label_btn.isCheckable()


# ---------------------------------------------------------------------------
# Filter inputs
# ---------------------------------------------------------------------------

def test_filter_apply_updates_state(toolbar, qtbot, state):
    spy = QSignalSpy(state.filter_changed)
    toolbar.low_filter.setText("1.0")
    toolbar.high_filter.setText("40.0")
    qtbot.mouseClick(toolbar.apply_filter_btn, Qt.MouseButton.LeftButton)
    assert len(spy) >= 1
    assert state.filter == (1.0, 40.0)


def test_filter_empty_fields_parse_as_none(toolbar, qtbot, state):
    toolbar.low_filter.clear()
    toolbar.high_filter.clear()
    toolbar.on_filter_changed()
    assert state.filter == (None, None)


def test_filter_partial_low_only(toolbar, qtbot, state):
    toolbar.low_filter.setText("0.5")
    toolbar.high_filter.clear()
    toolbar.on_filter_changed()
    assert state.filter == (0.5, None)


# ---------------------------------------------------------------------------
# Scale combo
# ---------------------------------------------------------------------------

def test_scale_combo_updates_state(toolbar, state):
    toolbar.select_scale.setCurrentText("50 µV/mm")
    assert state.scale == 50


# ---------------------------------------------------------------------------
# Montage combo
# ---------------------------------------------------------------------------

def test_montage_combo_updates_state(toolbar, state):
    spy = QSignalSpy(state.montage_changed)
    # Pick a different montage than the default
    items = [toolbar.select_montage.itemText(i) for i in range(toolbar.select_montage.count())]
    different = next(m for m in items if m != state.montage_name)
    toolbar.select_montage.setCurrentText(different)
    assert state.montage_name == different
    assert len(spy) >= 1


# ---------------------------------------------------------------------------
# Jump label combo
# ---------------------------------------------------------------------------

def test_jump_label_combo_emits_signal(toolbar, state, qtbot):
    spy = QSignalSpy(state.jump_label_changed)
    toolbar.jump_label_combo.setCurrentText("SEIZ")
    assert len(spy) >= 1


# ---------------------------------------------------------------------------
# Goto input
# ---------------------------------------------------------------------------

def test_goto_input_return_pressed_emits_signal(toolbar, state, qtbot):
    spy = QSignalSpy(state.goto_input_return_pressed)
    toolbar.goto_input.setText("30")
    QTest.keyPress(toolbar.goto_input, Qt.Key.Key_Return)
    assert len(spy) == 1
    assert spy[0][0] == 30


def test_goto_input_empty_does_not_emit(toolbar, state, qtbot):
    spy = QSignalSpy(state.goto_input_return_pressed)
    toolbar.goto_input.clear()
    QTest.keyPress(toolbar.goto_input, Qt.Key.Key_Return)
    assert len(spy) == 0


# ---------------------------------------------------------------------------
# Spinner (show_controls must be called first)
# ---------------------------------------------------------------------------

def test_spinner_emits_signal_after_show_controls(toolbar, state, qtbot):
    toolbar.show_controls(signal_duration=100.0, s_freq=256.0)
    spy = QSignalSpy(state.spinner_value_changed)
    toolbar.x_lim_spinner.setValue(15)
    assert len(spy) >= 1

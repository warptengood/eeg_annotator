# Contributing to Ziyatron EEG Annotator

Thank you for your interest in contributing! This document covers dev setup, architecture, and common extension patterns.

---

## Dev Setup

```bash
git clone https://github.com/warptengood/eeg_annotator.git
cd eeg_annotator

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
pip install -r requirements-dev.txt

python main.py
```

> Always run `python main.py` from the project root (not `python src/main.py`).

---

## Architecture

```
src/
├── main.py                  # App bootstrap, adds src/ to path
├── models/
│   └── app_state.py         # Centralized Qt signals / state
├── views/
│   ├── main_window.py       # Orchestration, signal wiring
│   ├── plot_widget.py       # PyQtGraph EEG visualization
│   └── control_toolbar.py   # File, montage, filter, scale controls
├── core/
│   ├── data_streamer.py     # Lazy-loading with LRU cache (key file)
│   ├── montage_manager.py   # Loads YAML montage configs at startup
│   └── config.py            # Diagnosis label list
└── utils/
    └── path_utils.py        # resource_path() for dev vs PyInstaller
```

**Data flow:** user action → `AppState` signal → `MainWindow` handler → `data_streamer.get_window()` → `plot_widget.update_plot()`

**Memory rule:** never use `preload=True` when opening EDF files. The streamer loads only the visible 6–10 s window into an LRU cache (max 5 windows).

---

## Common Extensions

### Add a diagnosis label

Edit `src/core/config.py` and append to the `diagnosis` list.

### Add a montage

Create `resources/montages/my_montage.yaml`:

```yaml
CH1-CH2: ['CH1', 'CH2']
CH2-CH3: ['CH2', 'CH3']
```

It will appear in the montage dropdown automatically.

### Add a toolbar control

1. Add widget to `ControlToolbar` (`src/views/control_toolbar.py`)
2. Add signal to `AppState` (`src/models/app_state.py`)
3. Emit the signal from the toolbar
4. Connect and handle it in `MainWindow` (`src/views/main_window.py`)

---

## Testing

```bash
# Unit tests
pytest tests/

# With coverage
pytest --cov=src tests/

# Memory profiling (expect <50 MB with a 100 MB EDF file)
python -m memory_profiler src/main.py
```

---

## Building Executables

```bash
pyinstaller main.spec
# Output: dist/eeg_annotator/

# Check bundle size (should be <200 MB)
du -sh dist/eeg_annotator/
```

---

## Releases / CI

Push a version tag to trigger the GitHub Actions build for Windows and macOS:

```bash
git tag v2.0.1
git push origin v2.0.1
```

Executables are uploaded automatically to GitHub Releases (~10–15 min build time).

---

## Code Style

```bash
black src/       # formatting
flake8 src/      # linting
```

Follow PEP 8. Add docstrings to public functions.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Ziyatron EEG Annotator v2.0** - A high-performance desktop GUI application for neurophysiologists to view, analyze, and annotate EEG (electroencephalogram) data from EDF files. Built with PyQt6 and PyQtGraph, optimized for memory efficiency (10x improvement over v1.0).

## Common Commands

### Running the Application
```bash
# Run from source (always use from project root)
python main.py

# NOT: python src/main.py (will fail with import errors)
```

### Setup
```bash
# Install runtime + dev deps (testing, linting, profiling)
uv sync --group dev

# Install runtime + build deps (pyinstaller) — needed to cut a release
uv sync --group build
```

### Testing
```bash
# Run all tests
uv run pytest tests/

# Run with coverage report
uv run pytest --cov=src tests/

# Memory profiling
uv run python -m memory_profiler main.py
# Expected: <50MB RAM usage with 100MB EDF file
```

### Building Executables
```bash
# Build locally with PyInstaller
pyinstaller main.spec

# Executable location: dist/eeg_annotator/

# Check bundle size (should be <200MB)
du -sh dist/eeg_annotator/  # macOS/Linux
```

### Code Quality
```bash
# Format code
black src/

# Lint code
flake8 src/
```

### Deployment
```bash
# Trigger automated builds via GitHub Actions
git tag v2.0.1
git push origin v2.0.1

# Builds Windows and macOS executables automatically
# Uploads to GitHub Releases with release notes
```

## Architecture Overview

### Design Philosophy
- **Lazy Loading**: Only loads 6-10 second windows of EEG data, not entire files
- **Memory Efficiency**: 30-50MB RAM for 100MB EDF files (vs 400-500MB in v1.0)
- **Performance**: PyQtGraph provides 10x faster rendering than Matplotlib
- **MVC-inspired**: Clear separation between Models (state), Views (UI), and Core (business logic)

### Module Organization

```
src/
├── main.py                      # Application bootstrap
├── models/
│   └── app_state.py            # Centralized state management with Qt signals
├── views/
│   ├── main_window.py          # Main window orchestration
│   ├── plot_widget.py          # PyQtGraph-based EEG visualization
│   └── control_toolbar.py      # User controls (file, montage, filter, scale)
├── core/
│   ├── data_streamer.py        # Lazy-loading EEG data with LRU cache
│   ├── montage_manager.py      # YAML-based montage configuration
│   └── config.py               # App configuration (diagnosis labels)
└── utils/
    └── path_utils.py           # Resource path resolution (dev vs PyInstaller)
```

### Key Data Flow Patterns

**File Loading:**
```
User clicks "Open" → open_file()
  → EEGPlotWidget.load_edf_file()
    → EEGDataStreamer.open_edf()     [opens handle with preload=False]
    → get_window(start=0, duration=10) [loads only first 10s]
    → update_plot()
```

**Lazy Loading (Pan/Zoom):**
```
User pans plot → sigRangeChanged signal
  → on_view_range_changed()
    → data_streamer.get_window(new_range) [loads new window from LRU cache or disk]
    → update_plot()
```

**State Changes:**
```
User changes montage/filter → ControlToolbar emits signal
  → AppState updates and emits montage_changed/filter_changed
    → MainWindow.on_settings_changed()
      → data_streamer.clear_cache()  [cache invalidation]
      → reload current window with new settings
```

### Signal/Slot Architecture (Qt)

**AppState signals:**
- `montage_changed` → triggers data reload
- `filter_changed` → triggers data reload
- `scale_changed` → updates plot Y-axis scaling
- `label_clicked` → enables annotation selection mode
- `undo_clicked` → removes last annotation
- `goto_input_return_pressed` → jumps to specific time
- `spinner_value_changed` → changes display window duration

### Critical Implementation Details

**Lazy Loading (data_streamer.py):**
- Uses `mne.io.read_raw_edf(preload=False)` to avoid loading entire file
- LRU cache with max 5 windows (configurable via `MAX_CACHE_SIZE`)
- Cache key: `(start_time, duration, montage_name, filter_tuple)` — `start_time` and
  `duration` are quantized to 0.5s before keying, so drag-pan frames that differ by
  a few ms share a cache entry.
- Loads windows with 2-second buffer for smooth panning
- Cache cleared when settings change (montage/filter)
- `current_montage`/`current_filter` attributes on `EEGDataStreamer` are dead state
  — montage/filter are passed per `get_window` call; don't rely on them.
- The `_monopolar_type` is detected once per file in `open_edf()` from EEG channel
  naming (`-A1`/`-A2` → REF, `-AV` → AV). Bipolar montages need it; see Montage System.

**PyQtGraph Optimization (plot_widget.py):**
- `downsample=10` reduces point density when zoomed out
- `clipToView=True` only renders visible region
- No full redraws on pan/zoom (unlike Matplotlib)
- `_scale_constant = 0.00001` controls vertical channel spacing
- Curves use `autoDownsample=True, autoDownsampleFactor=5.0` — pyqtgraph computes the
  downsample factor per render to target ~5 samples/pixel based on the current zoom.

**Montage System:**
- YAML files live under `resources/montages/<type>/<name>.yaml`, where `<type>` is
  the subdirectory name (`monopolar` or `bipolar`) and becomes the `Montage.type`.
- Display name = filename with `_`→space, uppercased (e.g. `average.yaml` → `AVERAGE`).
- MONOPOLAR format: `{display_ch}: ["EEG <SRC>-<REF>"]` (single-element list). The
  source channel is `pick`ed and renamed. Example: `FP1-AV: ["EEG FP1-AV"]`.
- BIPOLAR format is NESTED by reference type — each channel maps `REF`/`AV` to an
  `[anode, cathode]` pair, so one bipolar file works for both referential and
  average source files:
  ```yaml
  FP1-F7:
    REF: ["EEG FP1-A1", "EEG F7-A1"]
    AV:  ["EEG FP1-AV", "EEG F7-AV"]
  ```
- "AVERAGE" is a MONOPOLAR montage (maps to `-AV` channels), NOT a runtime average
  reference. Despite the v1.0 docs, no average-reference is computed.
- NOTE: bipolar montages require ALL EEG channels in the EDF to match one naming
  scheme — referential (`-A1`/`-A2`) or average (`-AV`). If `_monopolar_type` can't
  be detected, `_apply_montage` falls back to the raw channels unchanged (intended
  behavior — the plot shows the original channels under the selected montage label).
- MontageManager dynamically loads all YAMLs at startup (filesystem scan at import).

**Annotation Persistence:**
- Saves as CSV: `{edf_stem}_{montage_name_with_spaces→underscores}.csv` next to the EDF.
- Format: `channels,start_time,stop_time,onset` (`onset` = the diagnosis label string).
- Multi-channel annotations expanded to one row per channel on save; merged back on
  load by grouping rows with identical `(start_time, stop_time, onset)`.
- GOTCHA: `start_time`/`stop_time` are `round()`ed to INTEGER seconds when an
  annotation is created or moved — sub-second precision is lost and rectangles snap
  to whole seconds on reload.
- On reload, annotations whose channels aren't in the current montage are silently
  skipped (`render_annotations`), so switching montage can hide annotations.
- No unsaved-changes prompt: `closeEvent` discards in-memory annotations without
  warning if the user hasn't saved.

### PyInstaller Bundle Optimization

**Key exclusions in main.spec:**
- Matplotlib and dependencies (replaced with PyQtGraph) - saves ~80MB
- Unused PyQt6 modules (WebEngine, Multimedia, 3D) - saves ~180MB
- MNE tests/examples/datasets - saves ~400MB
- Strip and UPX compression enabled
- Result: 150MB bundle vs 500MB in v1.0

**Resource path handling:**
- `path_utils.py` uses `sys._MEIPASS` for PyInstaller bundles
- Always use `resource_path()` for accessing `resources/` folder

## Development Guidelines

### Adding New Features

**New Diagnosis Label:**
Edit `src/core/config.py` and add to the `diagnosis` list.

**New Montage:**
Create YAML file in `resources/montages/my_montage.yaml`:
```yaml
CH1-CH2: ['CH1', 'CH2']
CH2-CH3: ['CH2', 'CH3']
```
Will automatically appear in montage dropdown.

**New Control Widget:**
1. Add widget to `ControlToolbar` class
2. Create signal in `AppState`
3. Emit signal from toolbar
4. Connect signal in `MainWindow` to handler

**Modify Memory Behavior:**
In `src/core/data_streamer.py`:
- Adjust `MAX_CACHE_SIZE` (default: 5 windows)
- Modify `buffer_seconds` in `get_window()` (default: 2.0)

### Important Constraints

**Entry Point:**
- Always run `python main.py` from project root
- Never run `python src/main.py` (import paths will break)
- `main.py` wrapper adds `src/` to Python path

**Memory Management:**
- Never use `preload=True` when opening EDF files
- Always invalidate cache (`clear_cache()`) when settings change
- Keep window duration small (6-10 seconds recommended)

**UI Threading:**
- EEG data loading happens on the main thread. `get_window` runs crop + `load_data`
  + bipolar referencing + `raw.filter()` synchronously inside the pan/zoom/goto
  slots, so heavy filters block the UI. Move this to a `QThread` worker if you need
  smooth navigation (the cache + `raw_handle.copy()` would then need serialization).
- Qt signals/slots handle most cross-component communication. Use the public
  `view_range` property and `set_view_range(start, duration)` on `EEGPlotWidget`
  to read/restore the visible window — do not access `_last_view_range` directly.

**Filtering accuracy:**
- Filters are applied per small cropped window, which introduces edge/boundary
  transients near window edges. The 2s buffer mitigates but does not remove them;
  the filtered view is approximate near the visible edges.

**Logging:**
- Application logs to `eeg_annotator.log` and console
- Use `logging.getLogger(__name__)` in new modules

### Testing Notes

**Manual Testing Checklist:**
- Load 100MB+ EDF file and verify <50MB RAM usage
- Pan/zoom should be smooth (<50ms response)
- Test all montages load correctly
- Verify filter changes update display
- Annotation save/load with correct CSV format

**Memory Leak Detection:**
Run with memory profiler and check:
- Opening files doesn't accumulate memory
- Changing settings clears cache properly
- Annotations don't leak when creating/removing

### GitHub Actions CI/CD

**Workflow (`.github/workflows/build.yml`):**
- Triggers on version tags (`v*`) or manual dispatch
- Builds on Windows and macOS with Python 3.10
- Runs PyInstaller with `main.spec`
- Creates ZIP archives
- Uploads to GitHub Releases with auto-generated notes
- Build time: ~10-15 minutes per platform

**To deploy a new version:**
```bash
git tag v2.0.1
git push origin v2.0.1
# Wait for GitHub Actions to complete
# Download from Releases page
```

## Key File References

- Entry point: `main.py:10` (imports from `src/main.py`)
- Application bootstrap: `src/main.py:36-48` (`main()`)
- Main window orchestration: `src/views/main_window.py`
- Lazy loading implementation: `src/core/data_streamer.py:99-168` (`get_window`)
- Montage application: `src/core/data_streamer.py:170-211` (`_apply_montage`)
- Plot rendering: `src/views/plot_widget.py` (EEGPlotWidget class, ~159+)
- Annotation drawing/jump logic: `src/views/plot_widget.py:506-969`
- State management: `src/models/app_state.py` (Qt signals)
- Configuration: `src/core/config.py:25-77` (diagnosis labels, `pan_ammount`)
- Montage loading/type detection: `src/core/montage_manager.py`
- PyInstaller spec: `main.spec:16-50` (optimization settings)

## Common Pitfalls

1. **Import errors**: Always run from project root, not from `src/`
2. **Memory issues**: Don't use `preload=True`, keep cache size reasonable
3. **Bundle bloat**: Don't import matplotlib or unused PyQt6 modules
4. **Cache invalidation**: Clear cache when montage/filter changes
5. **Resource paths**: Use `path_utils.resource_path()` for resources, not hardcoded paths
6. **Main-thread blocking**: `get_window` filters/montages synchronously in the
   pan/zoom slots; heavy filters freeze the UI. Thread it for large/filtered files.
7. **Unsaved annotations**: closing the window discards unsaved annotations with no
   prompt; remind users to Ctrl+S (or add a dirty-state guard).
8. **Annotation precision**: annotation start/stop times are rounded to whole
   seconds; don't expect sub-second annotation boundaries.
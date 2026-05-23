# Test EDF Data

Place small, non-sensitive EDF files here for integration tests.

Required:
- At least one file with **average-reference** channels (`EEG <CH>-AV` naming)
- At least one file with **referential** channels (`EEG <CH>-A1` or `EEG <CH>-A2` naming)

Tests marked `needs_edf` will be **skipped** if no compatible file is found.
Tests marked `needs_edf` will **run** (not skipped) once both file types are present.

These files are excluded from the PyInstaller bundle (`main.spec` only collects
`resources/icons` and `resources/montages`).

# Ziyatron EEG Annotator

**Clinical-grade EEG annotation for neurophysiologists — fast, free, and runs on any laptop.**

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41cd52?logo=qt&logoColor=white)
![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-red)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-lightgrey)
![Downloads](https://img.shields.io/github/downloads/warptengood/eeg_annotator/total?color=brightgreen)

![Multiple annotations on EEG recording](docs/screenshots/08_multiple_annotations.png)

Load any EDF file, navigate the trace, and mark regions with 49 clinical labels — all without a hospital workstation. Streams data on demand so 100 MB+ files open in seconds and use under 50 MB of RAM. Built for teams: **labelers** mark regions and **experts** verify them, with full provenance on every annotation.

---

## Download

> **No installation required — just unzip and run.**

**[Download the latest release](https://github.com/warptengood/eeg_annotator/releases/latest)** — pre-built executables for Windows and macOS.

---

## Features

**Viewing**
- Load EDF / EDF+ files of any size (tested up to 1 GB+)
- Bipolar Double Banana, Bipolar Transverse, and Average montages
- Adjustable scale (1–1000 µV/mm), high-pass / low-pass filtering
- Smooth pan with A/D keys or mouse drag; zoom with scroll wheel
- Jump to any time with the Goto field

**Annotation**
- Draw rectangles across any time range and channel selection
- 49 pre-defined clinical labels (SEIZ, ARTF, AR, MUSC, EYBL, …)
- Sub-second time precision; vertical edges snap to whole channels
- Move, resize, copy/paste, and delete annotations
- Ctrl+Z undo

![Drawing an annotation](docs/screenshots/03_drawing_mode.gif)

**Review & verification**
- Labeler / expert roles (honor-system identity, no login)
- Experts verify, reject, or request changes on each label
- Border colors show review status at a glance (draft, submitted, verified, rejected, needs-changes)
- Every annotation records its author, reviewer, and timestamps

![Expert review panel](docs/screenshots/12_review_panel.png)

**File I/O**
- Annotations save to one JSON file next to the EDF (`{edf}.ziyatron.json`)
- Auto-loads existing annotations on open
- All montages in one file; saving one montage never touches another

---

## User Manual

Full usage instructions, keyboard shortcuts, and label reference: **[MANUAL.md](MANUAL.md)**

---

## Quick Start (from source)

```bash
git clone https://github.com/warptengood/eeg_annotator.git
cd eeg_annotator
uv sync
python main.py
```

> Always run `python main.py` from the project root — not `python src/main.py`.

---

## Built With

- [MNE-Python](https://mne.tools/) — EEG data I/O
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) — GUI framework
- [PyQtGraph](https://www.pyqtgraph.org/) — high-performance time-series rendering

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, architecture, and how to add montages or labels.

---

## Support

- Bug reports & feature requests: [GitHub Issues](https://github.com/warptengood/eeg_annotator/issues)
- Email: kenesyerassyl@gmail.com

---

## Author & License

**Ziyatron EEG Annotator** is created and maintained by **Kenes Yerassyl**.

- Original repository: [github.com/warptengood/eeg_annotator](https://github.com/warptengood/eeg_annotator)
- Contact: kenesyerassyl@gmail.com

This project is licensed under the **GNU General Public License v3.0** — see [LICENSE](LICENSE) for details.

Copyright © 2024–2026 Kenes Yerassyl. All source files carry the full GPL-3.0 copyright header.

If you encounter a copy of this software without proper attribution, it is in violation of the license terms.

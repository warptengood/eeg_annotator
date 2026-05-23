"""Wrapper entry point for Ziyatron EEG Annotator (for backward compatibility and PyInstaller)."""

import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path.parent))

# Import and run main application
from src.main import main

if __name__ == "__main__":
    main()

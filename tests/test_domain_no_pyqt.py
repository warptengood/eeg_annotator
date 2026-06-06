"""Guards the domain/persistence -> backend seam: it must not depend on PyQt.

A future FastAPI/engine backend reuses src.domain and the repository, so
importing them in a fresh interpreter must not pull in PyQt6.
"""

import subprocess
import sys


def test_domain_and_repository_import_without_pyqt():
    code = (
        "import sys;"
        "import src.domain.annotation, src.domain.review_service,"
        " src.core.annotation_repository;"
        "assert 'PyQt6' not in sys.modules, 'PyQt6 leaked into the domain layer';"
        "print('ok')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout

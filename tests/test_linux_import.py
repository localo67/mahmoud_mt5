import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_mt5_client_imports_without_metatrader5_package() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import mt5_client"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

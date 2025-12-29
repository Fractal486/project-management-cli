from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

_ORIG_MKDTEMP = tempfile.mkdtemp


def _temp_root() -> Path:
    base = os.environ.get("TEMP") or tempfile.gettempdir()
    root = Path(base) / "pm_test_tmp"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _make_tempdir(prefix: str = "tmp", suffix: str = "", dir: str | None = None) -> str:
    root = Path(dir) if dir else _temp_root()
    name = f"{prefix}{uuid.uuid4().hex}{suffix}"
    path = root / name
    path.mkdir(parents=True, exist_ok=False)
    return str(path)


class SafeTemporaryDirectory:
    def __init__(self, suffix: str | None = None, prefix: str | None = None, dir: str | None = None) -> None:
        self.name = _make_tempdir(prefix or "tmp", suffix or "", dir)

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.cleanup()
        return False

    def cleanup(self) -> None:
        shutil.rmtree(self.name, ignore_errors=True)


def pytest_configure(config) -> None:
    temp_path = str(_temp_root())
    os.environ["TMPDIR"] = temp_path
    os.environ["TEMP"] = temp_path
    os.environ["TMP"] = temp_path
    tempfile.tempdir = temp_path
    tempfile.TemporaryDirectory = SafeTemporaryDirectory
    tempfile.mkdtemp = _make_tempdir

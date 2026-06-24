from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


APP_NAME = "Automatic"
DATA_DIR_ENV = "AUTOMATIC_DATA_DIR"
LEGACY_APP_NAME = "InterAutomy"
LEGACY_DATA_DIR_ENV = "INTERAUTOMY_DATA_DIR"


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _local_app_data() -> Path:
    configured = os.environ.get("LOCALAPPDATA")
    if configured:
        return Path(configured)
    return Path.home() / "AppData" / "Local"


@dataclass(frozen=True)
class AppPaths:
    """Centralized filesystem locations used by the application.

    Installed applications may live in protected directories, so all mutable
    state is kept below the current user's local application-data directory.
    Project resources remain read-only and are resolved separately.
    """

    project_root: Path
    data_root: Path

    @property
    def logs_dir(self) -> Path:
        return self.data_root / "logs"

    def ensure_runtime_dirs(self) -> None:
        for directory in (self.data_root, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def resource(self, name: str) -> Path:
        """Resolve a bundled resource in development and PyInstaller builds."""

        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            bundled = Path(bundle_root) / name
            if bundled.exists():
                return bundled
        return self.project_root / name

@lru_cache(maxsize=1)
def get_app_paths() -> AppPaths:
    configured_data_root = os.environ.get(DATA_DIR_ENV)
    default_data_root = _local_app_data() / APP_NAME
    if configured_data_root:
        data_root = Path(configured_data_root)
    else:
        legacy_data_root = Path(
            os.environ.get(LEGACY_DATA_DIR_ENV, _local_app_data() / LEGACY_APP_NAME)
        )
        data_root = _migrate_legacy_data(legacy_data_root, default_data_root)
    paths = AppPaths(
        project_root=_project_root(),
        data_root=data_root,
    )
    paths.ensure_runtime_dirs()
    return paths


def _migrate_legacy_data(source: Path, destination: Path) -> Path:
    """Copy legacy user data once, preserving the source as a rollback backup."""
    if destination.exists() or not source.exists() or source.resolve() == destination.resolve():
        return destination
    try:
        shutil.copytree(source, destination)
    except OSError:
        return source
    return destination

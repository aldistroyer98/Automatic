from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


APP_NAME = "InterAutomy"


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
    def profiles_dir(self) -> Path:
        return self.data_root / "profiles"

    @property
    def logs_dir(self) -> Path:
        return self.data_root / "logs"

    @property
    def temp_dir(self) -> Path:
        return self.data_root / "temp"

    @property
    def chrome_profile_dir(self) -> Path:
        return self.data_root / "chrome-profile"

    @property
    def product_import_file(self) -> Path:
        return self.temp_dir / "Pedido_Asesor_Importar.xlsx"

    @property
    def ui_settings_file(self) -> Path:
        return self.data_root / "ui.ini"

    def ensure_runtime_dirs(self) -> None:
        for directory in (
            self.data_root,
            self.profiles_dir,
            self.logs_dir,
            self.temp_dir,
            self.chrome_profile_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def resource(self, name: str) -> Path:
        """Resolve a bundled resource in development and PyInstaller builds."""

        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            bundled = Path(bundle_root) / name
            if bundled.exists():
                return bundled
        return self.project_root / name

    def resolve_input_file(self, path_or_name: str) -> Path:
        """Resolve user input while preserving support for legacy relative paths."""

        raw_path = str(path_or_name or "").strip()
        if not raw_path:
            return Path()
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path

        project_candidate = self.project_root / path
        if project_candidate.exists():
            return project_candidate
        return self.data_root / path


@lru_cache(maxsize=1)
def get_app_paths() -> AppPaths:
    configured_data_root = os.environ.get("INTERAUTOMY_DATA_DIR")
    paths = AppPaths(
        project_root=_project_root(),
        data_root=Path(configured_data_root) if configured_data_root else _local_app_data() / APP_NAME,
    )
    paths.ensure_runtime_dirs()
    return paths

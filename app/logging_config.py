from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.paths import get_app_paths


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure process-wide logging once and return the application logger."""

    root = logging.getLogger()
    if getattr(root, "_interautomy_configured", False):
        return logging.getLogger("interautomy")

    paths = get_app_paths()
    handler = RotatingFileHandler(
        paths.logs_dir / "interautomy.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))

    root.setLevel(level)
    root.addHandler(handler)
    root._interautomy_configured = True  # type: ignore[attr-defined]
    return logging.getLogger("interautomy")

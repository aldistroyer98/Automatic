from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize


BASE_WIDTH = 1440
BASE_HEIGHT = 810
AVAILABLE_SCALES = (1.0, 0.9, 0.8, 0.7, 0.6)
DEFAULT_SCALE = 1.0


def _round_half_up(value: float) -> int:
    return int(value + 0.5)


@dataclass(frozen=True)
class UiScale:
    factor: float = DEFAULT_SCALE

    def __post_init__(self) -> None:
        normalized = self.normalize(self.factor)
        object.__setattr__(self, "factor", normalized)

    @staticmethod
    def normalize(value: object) -> float:
        try:
            candidate = float(value)
        except (TypeError, ValueError):
            return DEFAULT_SCALE
        for available in AVAILABLE_SCALES:
            if abs(candidate - available) < 0.001:
                return available
        return DEFAULT_SCALE

    @classmethod
    def from_percent(cls, percent: object) -> "UiScale":
        try:
            value = float(str(percent).replace("%", "").strip()) / 100
        except (TypeError, ValueError):
            value = DEFAULT_SCALE
        return cls(value)

    @property
    def percent(self) -> int:
        return _round_half_up(self.factor * 100)

    @property
    def label(self) -> str:
        return f"{self.percent}%"

    def px(self, value: int | float, minimum: int = 1) -> int:
        return max(minimum, _round_half_up(float(value) * self.factor))

    def font(self, value: int | float, minimum: int = 1) -> float:
        return max(float(minimum), round(float(value) * self.factor, 2))

    def size(self, width: int | float, height: int | float) -> QSize:
        return QSize(self.px(width), self.px(height))

    def window_size(self) -> QSize:
        return self.size(BASE_WIDTH, BASE_HEIGHT)


def scale_for(widget=None, scale: UiScale | None = None) -> UiScale:
    if scale is not None:
        return scale
    current = widget
    while current is not None:
        candidate = getattr(current, "ui_scale", None)
        if isinstance(candidate, UiScale):
            return candidate
        current = current.parentWidget() if hasattr(current, "parentWidget") else None
    return UiScale()

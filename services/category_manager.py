from __future__ import annotations

from collections.abc import Callable, Iterable, MutableSequence
from typing import TypeVar


T = TypeVar("T")


class CategoryManager:
    """Shared, UI-independent ordering rules for category dialogs."""

    _VISIBLE_NAMES = {
        "Reactivo Principal": "Producto Principal",
    }
    _INTERNAL_NAMES = {visible: internal for internal, visible in _VISIBLE_NAMES.items()}

    @classmethod
    def visible_name(cls, name: str) -> str:
        return cls._VISIBLE_NAMES.get(name, name)

    @classmethod
    def internal_name(cls, name: str) -> str:
        return cls._INTERNAL_NAMES.get(name, name)

    @staticmethod
    def target_index(index: int, length: int, action: str) -> int:
        if length <= 0:
            return 0
        if action == "first":
            return 0
        if action == "up":
            return max(0, index - 1)
        if action == "down":
            return min(length - 1, index + 1)
        if action == "last":
            return length - 1
        return max(0, min(length - 1, index))

    @classmethod
    def move(
        cls,
        items: MutableSequence[T],
        index: int,
        action: str,
    ) -> tuple[int, T | None]:
        if not items or index < 0 or index >= len(items):
            return index, None
        target = cls.target_index(index, len(items), action)
        item = items[index]
        if target != index:
            items.pop(index)
            items.insert(target, item)
        return target, item

    @staticmethod
    def normalize_order(
        items: Iterable[T],
        setter: Callable[[T, int], None],
    ) -> None:
        for order, item in enumerate(items):
            setter(item, order)

    @staticmethod
    def contains_name(names: Iterable[str], candidate: str) -> bool:
        key = candidate.strip().casefold()
        return any(str(name).strip().casefold() == key for name in names)

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from models.shipment import ShipmentRecord
from models.shipment_config import (
    DEFAULT_CATEGORY_COLORS,
    LEGACY_CATEGORY_MAP,
    ProductCategoryAssignment,
    ShipmentCategoryConfig,
    ShipmentCategoryState,
    product_key,
)


class ShipmentConfigService:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def default_state(self) -> ShipmentCategoryState:
        categories = [
            ShipmentCategoryConfig(name, color, index)
            for index, (name, color) in enumerate(DEFAULT_CATEGORY_COLORS.items())
        ]
        return ShipmentCategoryState(categories=categories)

    def load(self) -> ShipmentCategoryState:
        if not self.path.exists():
            return self.default_state()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            categories = [
                ShipmentCategoryConfig(
                    str(item.get("name", "")).strip(),
                    str(item.get("color_hex", "E7E6E6")).strip(),
                    int(item.get("order", index)),
                )
                for index, item in enumerate(data.get("categories", []))
                if str(item.get("name", "")).strip()
            ]
            assignments = {}
            for index, item in enumerate(data.get("assignments", [])):
                key = str(item.get("product_key", "")).strip()
                if not key:
                    key = product_key(item.get("cod_prod", ""), item.get("cod_eqv", ""), item.get("producto", ""))
                assignments[key] = ProductCategoryAssignment(
                    product_key=key,
                    cod_prod=str(item.get("cod_prod", "")).strip(),
                    cod_eqv=str(item.get("cod_eqv", "")).strip(),
                    producto=str(item.get("producto", "")).strip(),
                    category_name=str(item.get("category_name", "")).strip(),
                    product_order=int(item.get("product_order", index)),
                )
            state = ShipmentCategoryState(categories=categories, assignments=assignments)
            self._ensure_defaults(state)
            return state
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self.default_state()

    def save(self, state: ShipmentCategoryState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "categories": [
                {
                    "name": category.name,
                    "color_hex": category.normalized_color(),
                    "order": index,
                }
                for index, category in enumerate(state.sorted_categories())
            ],
            "assignments": [
                {
                    "product_key": assignment.product_key,
                    "cod_prod": assignment.cod_prod,
                    "cod_eqv": assignment.cod_eqv,
                    "producto": assignment.producto,
                    "category_name": assignment.category_name,
                    "product_order": assignment.product_order,
                }
                for assignment in sorted(
                    state.assignments.values(),
                    key=lambda item: (item.category_name.casefold(), item.product_order, item.producto.casefold()),
                )
            ],
        }
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def merge_products(self, state: ShipmentCategoryState, records: Iterable[ShipmentRecord]) -> bool:
        self._ensure_defaults(state)
        changed = False
        next_order_by_category = self._next_order_by_category(state)
        for record in records:
            key = product_key(record.cod_prod, record.cod_eqv, record.producto)
            if key in state.assignments:
                continue
            category = LEGACY_CATEGORY_MAP.get(record.categoria, record.categoria)
            if state.category_by_name(category) is None:
                category = next(iter(DEFAULT_CATEGORY_COLORS))
            order = next_order_by_category.get(category, 0)
            next_order_by_category[category] = order + 1
            state.assignments[key] = ProductCategoryAssignment(
                product_key=key,
                cod_prod=record.cod_prod,
                cod_eqv=record.cod_eqv,
                producto=record.producto,
                category_name=category,
                product_order=order,
            )
            changed = True
        return changed

    def _ensure_defaults(self, state: ShipmentCategoryState) -> None:
        existing = {category.name.casefold() for category in state.categories}
        next_order = max((category.order for category in state.categories), default=-1) + 1
        for name, color in DEFAULT_CATEGORY_COLORS.items():
            if name.casefold() not in existing:
                state.categories.append(ShipmentCategoryConfig(name, color, next_order))
                next_order += 1
        for index, category in enumerate(state.sorted_categories()):
            category.order = index

    @staticmethod
    def _next_order_by_category(state: ShipmentCategoryState) -> dict[str, int]:
        result = {category.name: 0 for category in state.categories}
        for assignment in state.assignments.values():
            result[assignment.category_name] = max(
                result.get(assignment.category_name, 0),
                assignment.product_order + 1,
            )
        return result

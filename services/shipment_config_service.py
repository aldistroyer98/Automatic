from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable

from models.shipment import ShipmentRecord
from models.shipment_config import (
    CATEGORY_WITHOUT_CATEGORY,
    DEFAULT_CATEGORY_COLORS,
    DEFAULT_FORECAST_COLORS,
    LEGACY_CATEGORY_MAP,
    ProductCategoryAssignment,
    ShipmentCategoryConfig,
    ShipmentCategoryState,
    ShipmentForecastConfig,
    ShipmentForecastProductConfig,
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

    @staticmethod
    def product_key_for_record(record: ShipmentRecord) -> str:
        return product_key(record.cod_prod, record.cod_eqv, record.producto)

    def load(self) -> ShipmentCategoryState:
        if not self.path.exists():
            return self.default_state()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            categories = [
                ShipmentCategoryConfig(
                    LEGACY_CATEGORY_MAP.get(str(item.get("name", "")).strip(), str(item.get("name", "")).strip()),
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
                    category_name=LEGACY_CATEGORY_MAP.get(
                        str(item.get("category_name", "")).strip(),
                        str(item.get("category_name", "")).strip(),
                    ),
                    product_order=int(item.get("product_order", index)),
                    linea=str(item.get("linea", "")).strip(),
                )
            state = ShipmentCategoryState(
                categories=categories,
                assignments=assignments,
                forecast=self._forecast_from_payload(data.get("forecast")),
            )
            self._ensure_defaults(state)
            self._normalize_assignments(state)
            return state
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return self.default_state()

    def save(self, state: ShipmentCategoryState) -> None:
        self._ensure_defaults(state)
        self._normalize_assignments(state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = self._state_payload(state)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def export_profile(
        self,
        state: ShipmentCategoryState,
        destination: str | Path,
        ui_preferences: dict | None = None,
    ) -> Path:
        self._ensure_defaults(state)
        self._normalize_assignments(state)
        payload = self._state_payload(state)
        assignments = payload["assignments"]
        profile = {
            "version": 1,
            "categories": payload["categories"],
            "assignments": assignments,
            "product_category_map": {
                item["product_key"]: item["category_name"]
                for item in assignments
            },
            "product_order_map": {
                item["product_key"]: item["product_order"]
                for item in assignments
            },
            "forecast": payload["forecast"],
            "ui_preferences": ui_preferences or {},
        }
        output = Path(destination)
        if output.suffix.lower() != ".json":
            output = output.with_suffix(".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        return output

    def import_profile(self, source: str | Path) -> tuple[ShipmentCategoryState, dict]:
        path = Path(source)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("El perfil no es un JSON válido.") from exc
        if not isinstance(data, dict):
            raise ValueError("El perfil no tiene una estructura válida.")
        if int(data.get("version", 1)) > 1:
            raise ValueError("La versión del perfil no es compatible.")

        categories = self._profile_categories(data)
        assignments = self._profile_assignments(data)
        state = ShipmentCategoryState(
            categories=categories,
            assignments=assignments,
            forecast=self._forecast_from_payload(data.get("forecast")),
        )
        self._ensure_defaults(state)
        self._normalize_assignments(state)
        ui_preferences = data.get("ui_preferences", {})
        return state, ui_preferences if isinstance(ui_preferences, dict) else {}

    def merge_products(
        self,
        state: ShipmentCategoryState,
        records: Iterable[ShipmentRecord],
        product_sort_key: Callable[[ShipmentRecord, int], object] | None = None,
    ) -> bool:
        self._ensure_defaults(state)
        changed = False
        next_order_by_category = self._next_order_by_category(state)
        unique_records: dict[str, tuple[ShipmentRecord, int]] = {}
        for index, record in enumerate(records):
            key = product_key(record.cod_prod, record.cod_eqv, record.producto)
            unique_records.setdefault(key, (record, index))
        items = sorted(
            unique_records.values(),
            key=lambda item: product_sort_key(item[0], item[1]) if product_sort_key else item[1],
        )
        for record, _index in items:
            key = product_key(record.cod_prod, record.cod_eqv, record.producto)
            if key in state.assignments:
                if not state.assignments[key].linea and record.linea:
                    state.assignments[key].linea = record.linea
                    changed = True
                continue
            category = LEGACY_CATEGORY_MAP.get(record.categoria, record.categoria)
            if state.category_by_name(category) is None:
                category = CATEGORY_WITHOUT_CATEGORY
            order = next_order_by_category.get(category, 0)
            next_order_by_category[category] = order + 1
            state.assignments[key] = ProductCategoryAssignment(
                product_key=key,
                cod_prod=record.cod_prod,
                cod_eqv=record.cod_eqv,
                producto=record.producto,
                category_name=category,
                product_order=order,
                linea=record.linea,
            )
            changed = True
        return changed

    def _state_payload(self, state: ShipmentCategoryState) -> dict:
        return {
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
                    "linea": assignment.linea,
                }
                for assignment in sorted(
                    state.assignments.values(),
                    key=lambda item: (item.category_name.casefold(), item.product_order, item.producto.casefold()),
                )
            ],
            "forecast": {
                "enabled": state.forecast.enabled,
                "logistics_days": max(0, int(state.forecast.logistics_days)),
                "colors": {
                    name: state.forecast.color(name)
                    for name in DEFAULT_FORECAST_COLORS
                },
                "products": [
                    {
                        "product_key": item.product_key,
                        "enabled": item.enabled,
                        "performance_days": max(0.0, float(item.performance_days)),
                        "logistics_days": item.logistics_days,
                        "performance_color": str(item.performance_color).strip().lstrip("#").upper(),
                        "observation": item.observation,
                    }
                    for item in state.forecast.products.values()
                ],
            },
        }

    @staticmethod
    def _forecast_from_payload(raw: object) -> ShipmentForecastConfig:
        if not isinstance(raw, dict):
            return ShipmentForecastConfig()
        config = ShipmentForecastConfig(
            enabled=bool(raw.get("enabled", False)),
            logistics_days=max(0, int(raw.get("logistics_days", 2))),
        )
        colors = raw.get("colors")
        if isinstance(colors, dict):
            config.colors.update({str(key): str(value) for key, value in colors.items()})
        products = raw.get("products", [])
        if isinstance(products, dict):
            products = list(products.values())
        if isinstance(products, list):
            for item in products:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("product_key", "")).strip()
                if not key:
                    continue
                logistics = item.get("logistics_days")
                config.products[key] = ShipmentForecastProductConfig(
                    product_key=key,
                    enabled=bool(item.get("enabled", True)),
                    performance_days=max(0.0, float(item.get("performance_days", 1.0))),
                    logistics_days=None if logistics in (None, "") else max(0, int(logistics)),
                    performance_color=str(item.get("performance_color", "")).strip().lstrip("#").upper(),
                    observation=str(item.get("observation", "")),
                )
        return config

    def _profile_categories(self, data: dict) -> list[ShipmentCategoryConfig]:
        raw_categories = data.get("categories")
        if not isinstance(raw_categories, list):
            raise ValueError("El perfil no contiene categorías válidas.")
        categories = [
            ShipmentCategoryConfig(
                LEGACY_CATEGORY_MAP.get(str(item.get("name", "")).strip(), str(item.get("name", "")).strip()),
                str(item.get("color_hex", "E7E6E6")).strip(),
                int(item.get("order", index)),
            )
            for index, item in enumerate(raw_categories)
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        if not categories:
            raise ValueError("El perfil no contiene categorías válidas.")
        return categories

    def _profile_assignments(self, data: dict) -> dict[str, ProductCategoryAssignment]:
        raw_assignments = data.get("assignments", [])
        category_map = data.get("product_category_map", {})
        order_map = data.get("product_order_map", {})
        if not isinstance(raw_assignments, list):
            raw_assignments = []
        if not isinstance(category_map, dict):
            category_map = {}
        if not isinstance(order_map, dict):
            order_map = {}

        assignments: dict[str, ProductCategoryAssignment] = {}
        for index, item in enumerate(raw_assignments):
            if not isinstance(item, dict):
                continue
            key = str(item.get("product_key", "")).strip()
            if not key:
                key = product_key(item.get("cod_prod", ""), item.get("cod_eqv", ""), item.get("producto", ""))
            category = str(category_map.get(key, item.get("category_name", CATEGORY_WITHOUT_CATEGORY))).strip()
            order_value = order_map.get(key, item.get("product_order", index))
            assignments[key] = ProductCategoryAssignment(
                product_key=key,
                cod_prod=str(item.get("cod_prod", "")).strip(),
                cod_eqv=str(item.get("cod_eqv", "")).strip(),
                producto=str(item.get("producto", "")).strip(),
                category_name=LEGACY_CATEGORY_MAP.get(category, category),
                product_order=int(order_value),
                linea=str(item.get("linea", "")).strip(),
            )
        return assignments

    def _ensure_defaults(self, state: ShipmentCategoryState) -> None:
        existing = {category.name.casefold() for category in state.categories}
        next_order = max((category.order for category in state.categories), default=-1) + 1
        for name, color in DEFAULT_CATEGORY_COLORS.items():
            if name.casefold() not in existing:
                state.categories.append(ShipmentCategoryConfig(name, color, next_order))
                next_order += 1
        for index, category in enumerate(state.sorted_categories()):
            category.order = index
        unique: dict[str, ShipmentCategoryConfig] = {}
        for category in state.sorted_categories():
            unique.setdefault(category.name.casefold(), category)
        state.categories = list(unique.values())

    def _normalize_assignments(self, state: ShipmentCategoryState) -> None:
        valid = {category.name.casefold(): category.name for category in state.categories}
        for assignment in state.assignments.values():
            category = valid.get(str(assignment.category_name or "").casefold())
            assignment.category_name = category or CATEGORY_WITHOUT_CATEGORY
        for category in state.category_names():
            assignments = sorted(
                (
                    assignment
                    for assignment in state.assignments.values()
                    if assignment.category_name == category
                ),
                key=lambda item: (
                    item.product_order,
                    item.producto.casefold(),
                    item.cod_prod.casefold(),
                    item.cod_eqv.casefold(),
                ),
            )
            for order, assignment in enumerate(assignments):
                assignment.product_order = order

    @staticmethod
    def _next_order_by_category(state: ShipmentCategoryState) -> dict[str, int]:
        result = {category.name: 0 for category in state.categories}
        for assignment in state.assignments.values():
            result[assignment.category_name] = max(
                result.get(assignment.category_name, 0),
                assignment.product_order + 1,
            )
        return result

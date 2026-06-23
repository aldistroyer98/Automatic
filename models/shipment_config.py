from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from models.shipment import (
    CATEGORY_CONSUMABLES,
    CATEGORY_CONTROLS,
    CATEGORY_REAGENTS,
    CATEGORY_UNCLASSIFIED,
)


CATEGORY_CONTROL_QUALITY = "Control de Calidad"
CATEGORY_MAIN_REAGENT = "Reactivo Principal"
CATEGORY_CONSUMABLE = "Consumible"
CATEGORY_NOT_CLASSIFIED = "No clasificado"
CATEGORY_WITHOUT_CATEGORY = "Sin Categoría"

DEFAULT_CATEGORY_COLORS = {
    CATEGORY_CONTROL_QUALITY: "DDEBF7",
    CATEGORY_MAIN_REAGENT: "FCE4D6",
    CATEGORY_CONSUMABLE: "E2F0D9",
    CATEGORY_NOT_CLASSIFIED: "E7E6E6",
    CATEGORY_WITHOUT_CATEGORY: "E7E6E6",
}

LEGACY_CATEGORY_MAP = {
    CATEGORY_CONTROLS: CATEGORY_CONTROL_QUALITY,
    CATEGORY_REAGENTS: CATEGORY_MAIN_REAGENT,
    CATEGORY_CONSUMABLES: CATEGORY_CONSUMABLE,
    CATEGORY_UNCLASSIFIED: CATEGORY_NOT_CLASSIFIED,
}


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(text.encode("ascii", "ignore").decode().casefold().split())


def product_key(cod_prod: object, cod_eqv: object, producto: object) -> str:
    return "|".join((normalize_text(cod_prod), normalize_text(cod_eqv), normalize_text(producto)))


@dataclass
class ShipmentCategoryConfig:
    name: str
    color_hex: str
    order: int

    def normalized_color(self) -> str:
        color = str(self.color_hex or "").strip().lstrip("#").upper()
        return color if len(color) == 6 else "E7E6E6"


@dataclass
class ProductCategoryAssignment:
    product_key: str
    cod_prod: str
    cod_eqv: str
    producto: str
    category_name: str
    product_order: int


@dataclass
class ShipmentCategoryState:
    categories: list[ShipmentCategoryConfig] = field(default_factory=list)
    assignments: dict[str, ProductCategoryAssignment] = field(default_factory=dict)

    def sorted_categories(self) -> list[ShipmentCategoryConfig]:
        return sorted(self.categories, key=lambda item: (item.order, item.name.casefold()))

    def category_names(self) -> list[str]:
        return [category.name for category in self.sorted_categories()]

    def category_by_name(self, name: str) -> ShipmentCategoryConfig | None:
        key = name.casefold()
        return next((category for category in self.categories if category.name.casefold() == key), None)

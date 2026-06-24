from __future__ import annotations

from models.equivalence import EquivalenceState
from models.shipment_config import (
    CATEGORY_WITHOUT_CATEGORY,
    DEFAULT_CATEGORY_COLORS,
    ProductCategoryAssignment,
    ShipmentCategoryConfig,
    ShipmentCategoryState,
    product_key,
)
from services.equivalence_service import EquivalenceService


class EquivalenceCategoryService:
    """Adapt EquivalenceState to the shared shipment category dialog."""

    def __init__(
        self,
        state: EquivalenceState,
        persistence: EquivalenceService,
    ) -> None:
        self.state = state
        self.persistence = persistence

    def dialog_state(self) -> ShipmentCategoryState:
        configured = self.state.settings.get("product_categories", [])
        categories = [
            ShipmentCategoryConfig(
                name=str(item.get("name", "")).strip(),
                color_hex=str(item.get("color", "E7E6E6")).strip(),
                order=index,
            )
            for index, item in enumerate(configured)
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        existing = {category.name.casefold() for category in categories}
        for name, color in DEFAULT_CATEGORY_COLORS.items():
            if name.casefold() not in existing:
                categories.append(ShipmentCategoryConfig(name, color, len(categories)))

        assignments = {}
        for product in self.state.products:
            key = product_key(product.cod_prod, product.cod_eqv, product.product)
            assignments[key] = ProductCategoryAssignment(
                product_key=key,
                cod_prod=product.cod_prod,
                cod_eqv=product.cod_eqv,
                producto=product.product,
                category_name=product.category or CATEGORY_WITHOUT_CATEGORY,
                product_order=product.order,
            )
        return ShipmentCategoryState(categories=categories, assignments=assignments)

    def save(self, dialog_state: ShipmentCategoryState) -> None:
        self.state.settings["product_categories"] = [
            {
                "name": category.name,
                "color": category.normalized_color(),
            }
            for category in dialog_state.sorted_categories()
        ]
        products_by_key = {
            product_key(product.cod_prod, product.cod_eqv, product.product): product
            for product in self.state.products
        }
        for key, assignment in dialog_state.assignments.items():
            product = products_by_key.get(key)
            if product is None:
                continue
            product.category = assignment.category_name
            product.order = assignment.product_order
        self.persistence.save(self.state)

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TenderTest:
    sap_code: str = ""
    description: str = ""
    quantity: float = 0.0


@dataclass
class ImportPreviewRow:
    sap_code: str = ""
    description: str = ""
    quantity: float = 0.0
    status: str = "Fila incompleta"
    observation: str = ""
    source_line: str = ""


@dataclass
class ReagentProduct:
    cod_prod: str = ""
    cod_eqv: str = ""
    product: str = ""
    det_rvo: float | None = None
    category: str = ""
    order: int = 0

    @property
    def key(self) -> str:
        return self.cod_prod.strip() or self.cod_eqv.strip() or self.product.strip()


@dataclass
class EquivalenceResult:
    sap_code: str
    test_description: str
    cod_prod: str
    cod_eqv: str
    product: str
    det_rvo: float | None
    det_oc: float
    det_env: float
    quantity: int
    category: str = ""
    warning: str = ""


@dataclass
class EquivalenceState:
    products: list[ReagentProduct] = field(default_factory=list)
    equivalences: dict[str, list[str]] = field(default_factory=dict)
    settings: dict = field(default_factory=dict)

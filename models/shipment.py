from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


CATEGORY_CONTROLS = "Controles y calibradores"
CATEGORY_REAGENTS = "Reactivos principales"
CATEGORY_CONSUMABLES = "Consumibles"
CATEGORY_UNCLASSIFIED = "No clasificados"

CATEGORY_ORDER = {
    CATEGORY_CONTROLS: 0,
    CATEGORY_REAGENTS: 1,
    CATEGORY_CONSUMABLES: 2,
    CATEGORY_UNCLASSIFIED: 3,
}


@dataclass(frozen=True)
class ShipmentRecord:
    fecha: date | datetime | None
    cliente: str
    cliente_corto: str
    cod_prod: str
    cod_eqv: str
    producto: str
    cantidad: float
    anio: int
    mes: int
    linea: str
    categoria: str
    responsable: str = ""
    comodato: str = ""
    licitacion: str = ""
    guia: str = ""
    pedido: str = ""
    lote: str = ""
    expira: str = ""
    registro_sanitario: str = ""


@dataclass(frozen=True)
class PowerBIExportResult:
    output_dir: Path
    fact_rows: int
    clients: int
    products: int
    years: tuple[int, ...]
    files: tuple[Path, ...]


@dataclass
class ShipmentOptions:
    create_client_sheets: bool = True
    create_summary: bool = True
    hide_normalized_data: bool = True
    use_category_colors: bool = True
    exclude_current_month: bool = True
    average_from_first_shipment: bool = True
    clients: set[str] = field(default_factory=set)
    years: set[int] = field(default_factory=set)
    lines: set[str] = field(default_factory=set)
    products: set[str] = field(default_factory=set)
    categories: set[str] = field(default_factory=set)
    responsibles: set[str] = field(default_factory=set)
    comodatos: set[str] = field(default_factory=set)
    licitaciones: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class ShipmentAnalysis:
    source: Path
    records: tuple[ShipmentRecord, ...]
    rows_read: int
    ignored_rows: int
    errors: tuple[str, ...] = ()

    @property
    def clients(self) -> tuple[str, ...]:
        return tuple(sorted({record.cliente for record in self.records}))

    @property
    def years(self) -> tuple[int, ...]:
        return tuple(sorted({record.anio for record in self.records}))

    @property
    def lines(self) -> tuple[str, ...]:
        return tuple(sorted({record.linea for record in self.records}))

    @property
    def products(self) -> tuple[str, ...]:
        return tuple(sorted({record.producto for record in self.records}))

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({record.categoria for record in self.records}))


@dataclass(frozen=True)
class ShipmentPreviewRow:
    cliente: str
    anio: int
    linea: str
    cod_prod: str
    cod_eqv: str
    producto: str
    categoria: str
    total: float
    meses: int
    prod: float

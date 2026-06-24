from __future__ import annotations

import csv
import json
import shutil
from calendar import month_abbr
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from models.shipment import (
    CATEGORY_CONSUMABLES,
    CATEGORY_CONTROLS,
    CATEGORY_ORDER,
    CATEGORY_REAGENTS,
    CATEGORY_UNCLASSIFIED,
    PowerBIExportResult,
    ShipmentAnalysis,
    ShipmentOptions,
    ShipmentRecord,
)
from models.shipment_config import CATEGORY_WITHOUT_CATEGORY, LEGACY_CATEGORY_MAP
from services.shipment_service import ShipmentService, ShipmentValidationError


TYPE_LABELS = {
    CATEGORY_CONTROLS: "Control/Calibrador",
    CATEGORY_REAGENTS: "Reactivo principal",
    CATEGORY_CONSUMABLES: "Consumible",
    CATEGORY_UNCLASSIFIED: CATEGORY_WITHOUT_CATEGORY,
    CATEGORY_WITHOUT_CATEGORY: CATEGORY_WITHOUT_CATEGORY,
}
MONTH_NAMES = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre",
)


class ShipmentPowerBIService:
    def __init__(
        self,
        shipment_service: ShipmentService,
        template_dir: str | Path | None = None,
    ) -> None:
        self.shipment_service = shipment_service
        self.today = shipment_service.today
        self.template_dir = Path(template_dir) if template_dir else Path("templates")

    def export(
        self,
        analysis: ShipmentAnalysis,
        destination: str | Path,
        options: ShipmentOptions | None = None,
    ) -> PowerBIExportResult:
        options = options or ShipmentOptions()
        records = self.shipment_service.filter_records(analysis.records, options)
        self._validate_records(records)

        output_dir = Path(destination)
        output_dir.mkdir(parents=True, exist_ok=True)
        tables = self._build_tables(records)
        files: list[Path] = []
        for name, (headers, rows) in tables.items():
            path = output_dir / f"{name}.csv"
            self._write_csv(path, headers, rows)
            files.append(path)

        artifacts = {
            "Medidas_DAX.txt": self._dax_measures(),
            "PowerQuery_M.txt": self._power_query(output_dir),
            "README_PowerBI.md": self._readme(),
            "Registros_Ignorados.txt": self._ignored_rows(analysis),
        }
        for filename, content in artifacts.items():
            path = output_dir / filename
            path.write_text(content, encoding="utf-8-sig")
            files.append(path)

        theme_path = output_dir / "theme_powerbi.json"
        theme_path.write_text(
            json.dumps(self._theme(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        files.append(theme_path)
        files.extend(self._copy_templates(output_dir))

        return PowerBIExportResult(
            output_dir=output_dir,
            fact_rows=len(tables["FactEnvios"][1]),
            clients=len(tables["DimCliente"][1]),
            products=len(tables["DimProducto"][1]),
            years=tuple(sorted({record.anio for record in records})),
            files=tuple(files),
        )

    @staticmethod
    def _ignored_rows(analysis: ShipmentAnalysis) -> str:
        lines = [
            f"Filas leídas: {analysis.rows_read}",
            f"Filas ignoradas: {analysis.ignored_rows}",
        ]
        if analysis.errors:
            lines.extend(("", "Detalle:", *analysis.errors))
        else:
            lines.extend(("", "No se registraron errores de normalización."))
        return "\n".join(lines) + "\n"

    def _build_tables(
        self, records: Sequence[ShipmentRecord]
    ) -> dict[str, tuple[tuple[str, ...], list[tuple[object, ...]]]]:
        clients = sorted({(record.cliente, record.cliente_corto) for record in records})
        client_ids = {client: f"C{index:04d}" for index, (client, _) in enumerate(clients, 1)}

        product_data: dict[str, ShipmentRecord] = {}
        for record in records:
            product_data.setdefault(record.cod_prod, record)
        products = sorted(
            product_data.values(),
            key=lambda record: self.shipment_service._product_sort(
                record.cod_prod, record.producto
            ),
        )
        product_ids = {
            record.cod_prod: f"P{index:04d}" for index, record in enumerate(products, 1)
        }

        lines = sorted({record.linea for record in records})
        line_ids = {line: f"L{index:04d}" for index, line in enumerate(lines, 1)}
        categories = sorted(
            {self._category_name(record.categoria) for record in records},
            key=self._category_order,
        )
        type_ids = {
            category: f"T{index + 1:02d}" for index, category in enumerate(categories)
        }

        fact_rows = []
        for index, record in enumerate(records, 1):
            shipment_date = self._record_date(record)
            category = self._category_name(record.categoria)
            category_label = TYPE_LABELS.get(category, category)
            fact_rows.append(
                (
                    f"E{index:07d}",
                    shipment_date.isoformat(),
                    record.anio,
                    record.mes,
                    MONTH_NAMES[record.mes - 1],
                    f"{record.anio:04d}-{record.mes:02d}",
                    client_ids[record.cliente],
                    product_ids[record.cod_prod],
                    line_ids[record.linea],
                    type_ids[category],
                    record.cod_prod,
                    record.cod_eqv,
                    record.cliente,
                    record.cliente_corto,
                    record.producto,
                    record.producto,
                    record.linea,
                    category_label,
                    record.cantidad,
                    record.comodato,
                    record.licitacion,
                    record.guia,
                    record.pedido,
                    record.lote,
                    record.expira,
                    record.registro_sanitario,
                    record.responsable,
                )
            )

        client_rows = [
            (client_ids[client], client, short, "", "", True)
            for client, short in clients
        ]
        product_rows = []
        for order, record in enumerate(products, 1):
            category = self._category_name(record.categoria)
            product_rows.append(
                (
                    product_ids[record.cod_prod],
                    record.cod_prod,
                    record.cod_eqv,
                    record.producto,
                    record.producto,
                    TYPE_LABELS.get(category, category),
                    self._category_order(category) + 1,
                    order,
                    category == CATEGORY_CONTROLS,
                    category == CATEGORY_REAGENTS,
                    category == CATEGORY_CONSUMABLES,
                    category == CATEGORY_WITHOUT_CATEGORY,
                )
            )
        line_rows = [(line_ids[line], line) for line in lines]
        type_rows = [
            (type_ids[category], TYPE_LABELS.get(category, category), self._category_order(category) + 1)
            for category in categories
        ]
        date_rows = self._date_rows(records)

        return {
            "FactEnvios": (
                (
                    "EnvioID", "Fecha", "Año", "MesNumero", "MesNombre", "Periodo",
                    "ClienteID", "ProductoID", "LineaID", "TipoProductoID", "CodProd",
                    "CodEqv", "Cliente", "ClienteCorto", "Producto", "ProductoLimpio",
                    "Linea", "TipoProductoInterno", "Cantidad", "Comodato", "Licitacion",
                    "Guia", "Pedido", "Lote", "Expira", "RegistroSanitario",
                    "ResponsableDepa",
                ),
                fact_rows,
            ),
            "DimCliente": (
                (
                    "ClienteID", "Cliente", "ClienteCorto", "Region",
                    "EstadoCliente", "IncluirEnPromedio",
                ),
                client_rows,
            ),
            "DimProducto": (
                (
                    "ProductoID", "CodProd", "CodEqv", "Producto", "ProductoLimpio",
                    "TipoProductoInterno", "OrdenTipoProducto", "OrdenProducto",
                    "EsControlCalibrador", "EsReactivoPrincipal", "EsConsumible",
                    "EsNoClasificado",
                ),
                product_rows,
            ),
            "DimFecha": (
                (
                    "Fecha", "Año", "MesNumero", "MesNombre", "Periodo", "MesAño",
                    "EsMesCerrado", "EsAñoActual", "EsMesActual", "EsMesFuturo",
                ),
                date_rows,
            ),
            "DimLinea": (("LineaID", "Linea"), line_rows),
            "DimTipoProducto": (
                ("TipoProductoID", "TipoProductoInterno", "OrdenTipoProducto"),
                type_rows,
            ),
        }

    def _date_rows(self, records: Sequence[ShipmentRecord]) -> list[tuple[object, ...]]:
        first = min(self._record_date(record) for record in records)
        last_record = max(self._record_date(record) for record in records)
        current_year_end = date(self.today.year, 12, 31)
        last = max(last_record, current_year_end)
        current = first
        rows = []
        while current <= last:
            is_current = current.year == self.today.year and current.month == self.today.month
            is_future = current > date(self.today.year, self.today.month, 1)
            rows.append(
                (
                    current.isoformat(),
                    current.year,
                    current.month,
                    MONTH_NAMES[current.month - 1],
                    f"{current.year:04d}-{current.month:02d}",
                    f"{month_abbr[current.month]}-{current.year}",
                    current < date(self.today.year, self.today.month, 1),
                    current.year == self.today.year,
                    is_current,
                    is_future,
                )
            )
            current += timedelta(days=1)
        return rows

    @staticmethod
    def _record_date(record: ShipmentRecord) -> date:
        value = record.fecha
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date(record.anio, record.mes, 1)

    @staticmethod
    def _write_csv(
        path: Path,
        headers: Sequence[str],
        rows: Iterable[Sequence[object]],
    ) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(headers)
            writer.writerows(rows)

    @staticmethod
    def _validate_records(records: Sequence[ShipmentRecord]) -> None:
        if not records:
            raise ShipmentValidationError("No hay registros para exportar a Power BI")
        for index, record in enumerate(records, 1):
            if not record.cliente or not record.producto:
                raise ShipmentValidationError(
                    f"Registro {index}: Cliente y Producto son obligatorios"
                )
            if not isinstance(record.cantidad, (int, float)):
                raise ShipmentValidationError(f"Registro {index}: Cantidad no numérica")
            if not 1 <= record.mes <= 12 or not 1900 <= record.anio <= 9999:
                raise ShipmentValidationError(f"Registro {index}: período inválido")

    @staticmethod
    def _category_name(category: str) -> str:
        return LEGACY_CATEGORY_MAP.get(category, category)

    @staticmethod
    def _category_order(category: str) -> int:
        category = LEGACY_CATEGORY_MAP.get(category, category)
        visual_order = {
            LEGACY_CATEGORY_MAP.get(key, key): value
            for key, value in CATEGORY_ORDER.items()
        }
        return visual_order.get(category, 1_000_000)

    def _copy_templates(self, output_dir: Path) -> list[Path]:
        copied = []
        for filename in ("EnvioDashboard.pbit", "EnvioDashboard.pbix"):
            source = self.template_dir / filename
            if source.exists():
                destination = output_dir / filename
                shutil.copy2(source, destination)
                copied.append(destination)
                break
        return copied

    @staticmethod
    def _dax_measures() -> str:
        return """// Medidas base
Total Enviado = SUM(FactEnvios[Cantidad])

Total Enviado Clientes Seleccionados =
CALCULATE([Total Enviado], ALLSELECTED(DimCliente[Cliente]))

Total Incluido en Promedio =
CALCULATE(
    [Total Enviado],
    KEEPFILTERS(DimCliente[IncluirEnPromedio] = TRUE())
)

Primer Mes con Envío =
MINX(
    FILTER(
        VALUES(DimFecha[Fecha]),
        DimFecha[EsMesCerrado] = TRUE()
            && CALCULATE([Total Incluido en Promedio]) <> 0
    ),
    DimFecha[Fecha]
)

Último Mes con Envío =
MAXX(
    FILTER(
        VALUES(DimFecha[Fecha]),
        DimFecha[EsMesCerrado] = TRUE()
            && CALCULATE([Total Incluido en Promedio]) <> 0
    ),
    DimFecha[Fecha]
)

Meses Contemplados =
VAR Inicio = [Primer Mes con Envío]
VAR Fin = [Último Mes con Envío]
RETURN IF(ISBLANK(Inicio) || ISBLANK(Fin), 0, DATEDIFF(Inicio, Fin, MONTH) + 1)

Promedio Mensual = DIVIDE([Total Incluido en Promedio], [Meses Contemplados], 0)

Total Controles =
CALCULATE([Total Enviado], DimTipoProducto[TipoProductoInterno] = "Control/Calibrador")

Total Reactivos Principales =
CALCULATE([Total Enviado], DimTipoProducto[TipoProductoInterno] = "Reactivo principal")

Total Consumibles =
CALCULATE([Total Enviado], DimTipoProducto[TipoProductoInterno] = "Consumible")

Total Sin Categoría =
CALCULATE([Total Enviado], DimTipoProducto[TipoProductoInterno] = "Sin Categoría")

Promedio Mensual Controles =
CALCULATE([Promedio Mensual], DimTipoProducto[TipoProductoInterno] = "Control/Calibrador")

Promedio Mensual Reactivos =
CALCULATE([Promedio Mensual], DimTipoProducto[TipoProductoInterno] = "Reactivo principal")

Promedio Mensual Consumibles =
CALCULATE([Promedio Mensual], DimTipoProducto[TipoProductoInterno] = "Consumible")

Clientes Activos = DISTINCTCOUNT(FactEnvios[ClienteID])

Productos Activos = DISTINCTCOUNT(FactEnvios[ProductoID])

Meses Cerrados =
CALCULATE(DISTINCTCOUNT(DimFecha[Periodo]), DimFecha[EsMesCerrado] = TRUE())

Último Mes Cerrado =
MAXX(FILTER(ALL(DimFecha), DimFecha[EsMesCerrado] = TRUE()), DimFecha[Fecha])

Total Enviado Año Actual =
CALCULATE([Total Enviado], DimFecha[Año] = YEAR(TODAY()))

Total Enviado Año Anterior =
CALCULATE([Total Enviado], DimFecha[Año] = YEAR(TODAY()) - 1)

Variación Año contra Año =
DIVIDE(
    [Total Enviado Año Actual] - [Total Enviado Año Anterior],
    [Total Enviado Año Anterior],
    0
)
"""

    @staticmethod
    def _power_query(output_dir: Path) -> str:
        base = str(output_dir.resolve()).replace("\\", "\\\\")
        sections = []
        types = {
            "FactEnvios": (
                '{"Fecha", type date}, {"Año", Int64.Type}, {"MesNumero", Int64.Type}, '
                '{"CodProd", type text}, {"CodEqv", type text}, {"Cantidad", type number}'
            ),
            "DimCliente": '{"IncluirEnPromedio", type logical}',
            "DimProducto": (
                '{"CodProd", type text}, {"CodEqv", type text}, '
                '{"OrdenTipoProducto", Int64.Type}, {"OrdenProducto", Int64.Type}, '
                '{"EsControlCalibrador", type logical}, {"EsReactivoPrincipal", type logical}, '
                '{"EsConsumible", type logical}, {"EsNoClasificado", type logical}'
            ),
            "DimFecha": (
                '{"Fecha", type date}, {"Año", Int64.Type}, {"MesNumero", Int64.Type}, '
                '{"EsMesCerrado", type logical}, {"EsAñoActual", type logical}, '
                '{"EsMesActual", type logical}, {"EsMesFuturo", type logical}'
            ),
            "DimLinea": "",
            "DimTipoProducto": '{"OrdenTipoProducto", Int64.Type}',
        }
        for table, transformations in types.items():
            typed = (
                f",\n    Typed = Table.TransformColumnTypes(Promoted, {{{transformations}}})"
                if transformations else ""
            )
            result = "Typed" if transformations else "Promoted"
            sections.append(
                f"""// Consulta: {table}
let
    Source = Csv.Document(
        File.Contents("{base}\\\\{table}.csv"),
        [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]){typed}
in
    {result}
"""
            )
        return "\n".join(sections)

    @staticmethod
    def _readme() -> str:
        return """# Dataset de Envíos para Power BI

## Importación

1. Abra Power BI Desktop.
2. Importe los seis CSV con **Obtener datos > Texto/CSV**.
3. Use `PowerQuery_M.txt` si prefiere crear las consultas desde el editor avanzado.
4. Cree relaciones de uno a varios desde cada dimensión hacia `FactEnvios`.
5. Marque `DimFecha` como tabla de fechas y ordene `MesNombre` por `MesNumero`.
6. Copie las medidas de `Medidas_DAX.txt` a una tabla de medidas.

## Relaciones

- `DimCliente[ClienteID]` -> `FactEnvios[ClienteID]`
- `DimProducto[ProductoID]` -> `FactEnvios[ProductoID]`
- `DimFecha[Fecha]` -> `FactEnvios[Fecha]`
- `DimLinea[LineaID]` -> `FactEnvios[LineaID]`
- `DimTipoProducto[TipoProductoID]` -> `FactEnvios[TipoProductoID]`

`Registros_Ignorados.txt` documenta las filas descartadas durante la normalización.

## IncluirEnPromedio

`DimCliente[IncluirEnPromedio]` inicia en `TRUE`. Cambie a `FALSE` los clientes
que no deben afectar el promedio consolidado. Las medidas de promedio conservan
los filtros activos y además aplican esta bandera.

## Páginas sugeridas

1. **Resumen General**: tarjetas de total, meses, promedio, clientes y productos;
   tendencia mensual; top 10 productos y clientes; segmentadores.
2. **Cliente**: selector, matriz producto/mes, totales y tendencia.
3. **Producto**: selector, clientes consumidores y evolución mensual.
4. **Consumo por Tipo**: participación y tendencia por clasificación.
5. **Validación Comercial**: caídas, inactividad, productos sin movimiento y alertas.

## Dashboard final

Para entregar un `.pbix` visualmente terminado se recomienda aportar una plantilla
`.pbit`, logo corporativo, paleta definitiva, capturas del diseño y cualquier
clasificación manual pendiente. La aplicación copia automáticamente una plantilla
llamada `templates/EnvioDashboard.pbit` o `templates/EnvioDashboard.pbix`.
"""

    @staticmethod
    def _theme() -> dict[str, object]:
        return {
            "name": "Automatic Env\u00edos",
            "dataColors": [
                "#1F4E78",
                "#5B9BD5",
                "#F4B183",
                "#70AD47",
                "#C0504D",
                "#A5A5A5",
            ],
            "background": "#F5F7FA",
            "foreground": "#1F2937",
            "tableAccent": "#1F4E78",
        }

from __future__ import annotations

from openpyxl import load_workbook

from app.paths import _migrate_legacy_data
from services.category_manager import CategoryManager
from services.equivalence_service import EquivalenceService
from services.excel_reader import sanitize_tabular_rows


def test_sanitize_tabular_rows_removes_exported_index_and_empty_data() -> None:
    rows = [
        ("Unnamed: 0", "CodProd", "Producto", None),
        (0, "P-1", "Producto A", None),
        (None, None, None, None),
    ]

    assert sanitize_tabular_rows(rows) == [
        ("CodProd", "Producto"),
        ("P-1", "Producto A"),
    ]


def test_category_display_mapping_preserves_internal_value() -> None:
    assert CategoryManager.visible_name("Reactivo Principal") == "Producto Principal"
    assert CategoryManager.internal_name("Producto Principal") == "Reactivo Principal"


def test_legacy_data_migration_copies_without_deleting_source(tmp_path) -> None:
    source = tmp_path / "legacy"
    destination = tmp_path / "Automatic"
    source.mkdir()
    (source / "equivalence_config.json").write_text('{"version": 1}', encoding="utf-8")

    selected = _migrate_legacy_data(source, destination)

    assert selected == destination
    assert (destination / "equivalence_config.json").exists()
    assert (source / "equivalence_config.json").exists()


def test_product_import_ignores_unnamed_index_column(tmp_path) -> None:
    source = tmp_path / "products.xlsx"
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(("Unnamed: 0", "CodProd", "CodEqv", "Producto", "DET RVO", "Categoría"))
    sheet.append((0, "P-1", "E-1", "Producto A", 5, "Sin Categoría"))
    workbook.save(source)

    products = EquivalenceService(tmp_path / "state.json").load_products_file(source)

    assert len(products) == 1
    assert products[0].cod_prod == "P-1"
    assert products[0].det_rvo == 5


def test_product_import_rejects_missing_required_headers(tmp_path) -> None:
    source = tmp_path / "invalid.xlsx"
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(("CodProd", "Producto"))
    sheet.append(("P-1", "Producto A"))
    workbook.save(source)

    service = EquivalenceService(tmp_path / "state.json")
    try:
        service.load_products_file(source)
    except ValueError as exc:
        assert "Faltan encabezados obligatorios" in str(exc)
    else:
        raise AssertionError("Expected missing-header validation")


def test_product_import_rejects_non_numeric_det_rvo(tmp_path) -> None:
    from openpyxl import Workbook

    source = tmp_path / "invalid_det.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(("CodProd", "CodEqv", "Producto", "DET RVO"))
    sheet.append(("P-1", "E-1", "Producto A", "no-numérico"))
    workbook.save(source)

    service = EquivalenceService(tmp_path / "state.json")
    try:
        service.load_products_file(source)
    except ValueError as exc:
        assert "DET RVO debe ser numérico" in str(exc)
    else:
        raise AssertionError("Expected DET RVO validation")


def test_product_export_has_no_index_or_unnamed_columns(tmp_path) -> None:
    from models.equivalence import ReagentProduct

    service = EquivalenceService(tmp_path / "state.json")
    output = service.export_products_excel(
        tmp_path / "products.xlsx",
        [ReagentProduct("P-1", "E-1", "Producto A", 5, "Sin Categoría", 0)],
    )

    workbook = load_workbook(output, read_only=True, data_only=True)
    try:
        headers = next(workbook.active.iter_rows(values_only=True))
    finally:
        workbook.close()

    assert headers == ("CodProd", "CodEqv", "Producto", "DET RVO", "Categoría", "Orden")
    assert not any(str(value or "").startswith("Unnamed:") for value in headers)

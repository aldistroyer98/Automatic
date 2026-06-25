from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from models.equivalence import (
    EquivalenceState,
    ImportPreviewRow,
    ReagentProduct,
    TenderTest,
)
from services.equivalence_category_service import EquivalenceCategoryService
from services.equivalence_service import EquivalenceService
from ui.dialogs.homologation_dialog import HomologationDialog
from ui.dialogs.import_preview_dialog import ImportPreviewDialog
from ui.dialogs.internal_consumption_dialog import InternalConsumptionDialog
from ui.internal_consumption_widget import InternalConsumptionWidget
from ui.tabs import equivalence_tab


def application() -> QApplication:
    return QApplication.instance() or QApplication([])


class FakeEquivalenceTab(QWidget):
    def __init__(
        self,
        service: EquivalenceService,
        tests: list[TenderTest],
        products: list[ReagentProduct],
    ) -> None:
        super().__init__()
        self.service = service
        self.tests = tests
        self._results = []
        self.state = EquivalenceState(
            products=products,
            settings={
                "product_categories": [
                    {"name": "Control de Calidad", "color": "DDEBF7"},
                    {"name": "Reactivo Principal", "color": "FCE4D6"},
                    {"name": "Consumible", "color": "E2F0D9"},
                    {"name": "Sin Categoría", "color": "E7E6E6"},
                ]
            },
        )

    def _tests_from_table(self) -> list[TenderTest]:
        return list(self.tests)

    def _replace_tender_tests(self, tests: list[TenderTest]) -> None:
        self.tests = list(tests)

    def _replace_products(self, products: list[ReagentProduct]) -> None:
        self.state.products = products

    def save_state(self, show_message: bool = False) -> None:
        del show_message

    def recalculate(self) -> None:
        pass

    def _format_number(self, value: float | None) -> str:
        if value is None:
            return ""
        return str(int(value)) if float(value).is_integer() else str(value)

    @staticmethod
    def _number(value: object) -> float:
        return float(value or 0)

    def load_products_file(self) -> None:
        pass

    def open_category_dialog(self) -> None:
        pass


def test_import_preview_has_four_columns_and_centered_description(tmp_path) -> None:
    app = application()
    tab = FakeEquivalenceTab(EquivalenceService(tmp_path / "state.json"), [], [])
    dialog = ImportPreviewDialog(
        tab,
        tmp_path / "input.csv",
        [
            ImportPreviewRow(
                "30123456",
                "Prueba de coagulación completa",
                2,
                "OK",
                "oculta",
            )
        ],
    )
    app.processEvents()

    assert dialog.table.columnCount() == 4
    assert [
        dialog.table.horizontalHeaderItem(column).text()
        for column in range(dialog.table.columnCount())
    ] == ["Código SAP", "Descripción", "Cantidad", "Estado"]
    assert dialog.table.item(0, 1).textAlignment() == Qt.AlignCenter
    assert dialog.table.item(0, 3).text() == "OK"
    dialog.close()


def test_products_sort_by_category_then_internal_order(tmp_path) -> None:
    service = EquivalenceService(tmp_path / "state.json")
    products = [
        ReagentProduct("C-2", "", "Consumible 2", 1, "Consumible", 1),
        ReagentProduct("Q-2", "", "Control 2", 1, "Control de Calidad", 1),
        ReagentProduct("Q-1", "", "Control 1", 1, "Control de Calidad", 0),
        ReagentProduct("C-1", "", "Consumible 1", 1, "Consumible", 0),
    ]

    ordered = service.sorted_products(products)

    assert [product.cod_prod for product in ordered] == ["Q-1", "Q-2", "C-1", "C-2"]


def test_category_adapter_uses_relative_order_per_category(tmp_path) -> None:
    state = EquivalenceState(
        products=[
            ReagentProduct("Q-6", "", "Control 6", 1, "Control de Calidad", 5),
            ReagentProduct("Q-7", "", "Control 7", 1, "Control de Calidad", 6),
            ReagentProduct("C-1", "", "Consumible 1", 1, "Consumible", 0),
        ]
    )
    adapter = EquivalenceCategoryService(
        state,
        EquivalenceService(tmp_path / "state.json"),
    )

    dialog_state = adapter.dialog_state()
    control_orders = [
        assignment.product_order
        for assignment in dialog_state.assignments.values()
        if assignment.category_name == "Control de Calidad"
    ]
    consumable_orders = [
        assignment.product_order
        for assignment in dialog_state.assignments.values()
        if assignment.category_name == "Consumible"
    ]

    assert control_orders == [0, 1]
    assert consumable_orders == [0]


def test_homologation_hides_and_restores_used_rows_and_sorts_relations(tmp_path) -> None:
    app = application()
    tab = FakeEquivalenceTab(
        EquivalenceService(tmp_path / "state.json"),
        [
            TenderTest("30000001", "Prueba 1", 1),
            TenderTest("30000002", "Prueba 2", 1),
        ],
        [
            ReagentProduct("P-10", "", "Producto 10", 10, "Consumible", 9),
            ReagentProduct("P-2", "", "Producto 2", 10, "Consumible", 1),
        ],
    )
    dialog = HomologationDialog(tab)
    app.processEvents()

    assert dialog.relation_table.horizontalHeaderItem(0).text() == "Orden"
    assert [
        dialog.test_table.horizontalHeaderItem(column).text()
        for column in range(dialog.test_table.columnCount())
    ] == ["Orden", "Código SAP", "Descripción", "Cantidad"]
    assert [
        dialog.product_table.horizontalHeaderItem(column).text()
        for column in range(dialog.product_table.columnCount())
    ] == ["Orden", "CodProd", "CodEqv", "Producto", "DET RVO"]

    dialog.test_table.selectRow(0)
    dialog.product_table.selectRow(1)
    dialog.add_relation()
    assert dialog.test_table.rowCount() == 1
    assert dialog.product_table.rowCount() == 1

    dialog.test_table.selectRow(0)
    dialog.product_table.selectRow(0)
    dialog.add_relation()
    assert dialog.test_table.rowCount() == 0
    assert dialog.product_table.rowCount() == 0
    assert dialog.relation_table.rowCount() == 2
    assert [
        dialog.relation_table.item(row, 0).text()
        for row in range(2)
    ] == ["2", "10"]

    dialog.relation_table.selectRow(0)
    dialog.remove_relation()
    assert dialog.test_table.rowCount() == 1
    assert dialog.product_table.rowCount() == 1
    assert dialog.relation_table.rowCount() == 1
    dialog.close()


def test_calculated_results_follow_product_order_and_enforce_unique_products(tmp_path) -> None:
    service = EquivalenceService(tmp_path / "state.json")
    first = TenderTest("30000001", "Prueba 1", 1)
    second = TenderTest("30000002", "Prueba 2", 1)
    product_ten = ReagentProduct("P-10", "", "Producto 10", 10, "Consumible", 9)
    product_two = ReagentProduct("P-2", "", "Producto 2", 10, "Consumible", 1)
    state = EquivalenceState(
        products=[product_ten, product_two],
        equivalences={
            service.test_key(first): [product_ten.key],
            service.test_key(second): [product_two.key, product_ten.key],
        },
    )

    results, _warnings = service.calculate([first, second], state, 1, "total")

    assert [result.cod_prod for result in results] == ["P-2", "P-10"]
    assert [result.product_order for result in results] == [1, 9]


def test_equivalence_tab_uses_dialog_for_internal_consumption(tmp_path, monkeypatch) -> None:
    application()
    monkeypatch.setattr(
        equivalence_tab,
        "get_app_paths",
        lambda: SimpleNamespace(data_root=tmp_path),
    )
    tab = equivalence_tab.EquivalenceTab()

    tab.show_homologation()
    assert tab.view_stack.currentWidget() is tab.homologation_widget
    tab.show_equivalence()
    assert tab.view_stack.currentWidget() is tab.result_page

    calls = []

    class FakeDialog:
        def __init__(self, parent):
            calls.append(("init", parent))

        def exec(self):
            calls.append(("exec", None))
            return 0

    monkeypatch.setattr(equivalence_tab, "InternalConsumptionDialog", FakeDialog)
    tab.show_internal_consumption()

    assert calls == [("init", tab), ("exec", None)]
    assert tab.view_stack.count() == 2
    tab.close()


def test_internal_consumption_dialog_is_fixed_1200_by_675(tmp_path) -> None:
    application()
    tab = FakeEquivalenceTab(EquivalenceService(tmp_path / "state.json"), [], [])
    tab.period_months = SimpleNamespace(value=lambda: 12)
    tab.period_type = SimpleNamespace(currentText=lambda: "Total del periodo")
    tab._optional_number = lambda value: float(value) if value else None
    tab._load_state_to_products = lambda: None
    dialog = InternalConsumptionDialog(tab)

    assert (dialog.width(), dialog.height()) == (1200, 675)
    assert dialog.minimumSize() == dialog.maximumSize()
    assert dialog.widget.tabs.count() == 3
    dialog.close()


def test_internal_consumption_dialog_discards_unsaved_changes(
    tmp_path,
    monkeypatch,
) -> None:
    application()
    tab = FakeEquivalenceTab(EquivalenceService(tmp_path / "state.json"), [], [])
    tab.period_months = SimpleNamespace(value=lambda: 12)
    tab.period_type = SimpleNamespace(currentText=lambda: "Total del periodo")
    tab._optional_number = lambda value: float(value) if value else None
    tab._load_state_to_products = lambda: None
    tab.state.settings = {"internal_consumption": {"controls": [], "consumables": []}}
    dialog = InternalConsumptionDialog(tab)
    tab.state.settings["internal_consumption"]["controls"].append({"changed": True})
    dialog.widget.set_dirty(True)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *_args, **_kwargs: QMessageBox.Discard,
    )

    assert dialog._confirm_pending_changes()
    assert tab.state.settings["internal_consumption"]["controls"] == []
    dialog._closing = True
    dialog.close()


def test_internal_consumption_accepts_text_product_name(tmp_path, monkeypatch) -> None:
    application()
    monkeypatch.setattr(
        equivalence_tab,
        "get_app_paths",
        lambda: SimpleNamespace(data_root=tmp_path),
    )
    tab = equivalence_tab.EquivalenceTab()
    product = ReagentProduct(
        "R-1",
        "E-1",
        "HemosIL RecombiPlasTin 2G (8mL)",
        360,
        "Reactivo Principal",
        0,
    )
    tab.state = EquivalenceState(products=[product])
    tab._load_state_to_products()
    tab._results = [
        equivalence_tab.EquivalenceResult(
            "",
            "Consumo interno",
            product.cod_prod,
            product.cod_eqv,
            product.product,
            product.det_rvo,
            0,
            360,
            1,
            product.category,
            "",
            product.order,
            360,
        )
    ]
    tab.recalculate = lambda: None

    widget = InternalConsumptionWidget(tab)
    widget.refresh()
    widget.apply_calculation()

    assert tab._format_number(product.product) == product.product
    assert widget.summary_table.item(0, 0).text() == product.product
    widget.close()
    tab.close()


def test_internal_control_consumption_and_boxes(tmp_path) -> None:
    service = EquivalenceService(tmp_path / "state.json")
    reagent = ReagentProduct("R-1", "", "Reactivo", 360, "Reactivo Principal", 0)
    normal = ReagentProduct("Q-1", "", "Control normal", 10, "Control de Calidad", 0)
    abnormal = ReagentProduct("Q-2", "", "Control patológico", 10, "Control de Calidad", 1)
    state = EquivalenceState(
        products=[reagent, normal, abnormal],
        settings={
            "internal_consumption": {
                "controls": [
                    {
                        "control_product_key": normal.key,
                        "linked_reagent_keys": [reagent.key],
                        "frequency_per_day": 1,
                        "enabled": True,
                    },
                    {
                        "control_product_key": abnormal.key,
                        "linked_reagent_keys": [reagent.key],
                        "frequency_per_day": 1,
                        "enabled": True,
                    },
                ],
                "consumables": [],
            }
        },
    )

    results, _warnings = service.calculate_with_internal_consumption(
        [],
        state,
        12,
        "total",
    )
    by_code = {result.cod_prod: result for result in results}

    assert service.control_boxes(365, 10, 1) == 37
    assert by_code["R-1"].det_internal == 730
    assert by_code["R-1"].quantity == 3
    assert by_code["Q-1"].quantity == 37
    assert by_code["Q-2"].quantity == 37


def test_consumable_uses_total_reagent_det_env_and_rules_persist(tmp_path) -> None:
    service = EquivalenceService(tmp_path / "state.json")
    first_test = TenderTest("30000001", "TP", 500)
    second_test = TenderTest("30000002", "TTPA", 900)
    first = ReagentProduct("R-1", "", "TP", 360, "Reactivo Principal", 0)
    second = ReagentProduct("R-2", "", "TTPA", 870, "Reactivo Principal", 1)
    cuvettes = ReagentProduct("C-1", "", "Cuvettes", 1000, "Consumible", 0)
    state = EquivalenceState(
        products=[first, second, cuvettes],
        equivalences={
            service.test_key(first_test): [first.key],
            service.test_key(second_test): [second.key],
        },
        settings={
            "internal_consumption": {
                "controls": [],
                "consumables": [
                    {
                        "consumable_product_key": cuvettes.key,
                        "basis": "total_reagent_det_env",
                        "linked_reagent_keys": [],
                        "enabled": True,
                    }
                ],
            }
        },
    )

    results, _warnings = service.calculate_with_internal_consumption(
        [first_test, second_test],
        state,
        12,
        "total",
    )
    by_code = {result.cod_prod: result for result in results}
    reagent_total = by_code["R-1"].det_env + by_code["R-2"].det_env

    assert by_code["C-1"].det_internal == reagent_total
    assert by_code["C-1"].quantity == 3

    service.save(state)
    loaded = service.load()
    assert loaded.settings["internal_consumption"] == state.settings["internal_consumption"]

from __future__ import annotations

import logging
import os
from typing import Dict, Iterable, List

from PySide6.QtCore import QEvent, QEasingCurve, QModelIndex, QPropertyAnimation, QSettings, Qt, QTimer, Slot
from PySide6.QtGui import QCloseEvent, QIcon, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QHeaderView,
    QSizePolicy,
    QTableView,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.paths import get_app_paths
from automation.runtime_config import AutomyCredentials, AutomationRuntimeConfig
from models.order_params import OrderParams
from models.product import Product
from market.ui import MarketTab
from services.automy_runner import AutomyRunner
from services.catalog_service import CatalogService
from services.credential_service import CredentialService
from services.excel_service import ExcelService
from services.profile_service import ProfileService
from services.shipment_service import ShipmentService
from services.validation_service import ValidationService
from ui.components import (
    PRODUCT_COLUMN_UNITS,
    AutoValidationSwitch,
    ProductFilterProxyModel,
    ProductItemDelegate,
    ProductTableModel,
    ProductTableView,
    ToastManager,
)
from ui.dialogs import (
    ClientLinkDialog,
    CredentialsDialog,
    DualListFilterDialog,
    ManualValidationDialog,
    ProductFilterDialog,
    ValidationDialog,
)
from ui.icons import app_icon
from ui.scaling import AVAILABLE_SCALES, UiScale
from ui.tabs import ShipmentTab
from ui.theme import ThemeMode, palette, stylesheet

try:
    from qfluentwidgets import Theme as FluentTheme
    from qfluentwidgets import setTheme as set_fluent_theme
except ImportError:  # pragma: no cover - optional visual enhancement
    FluentTheme = None
    set_fluent_theme = None


logger = logging.getLogger("interautomy.ui")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("InterAutomy - Sistemas Analíticos")
        self.paths = get_app_paths()
        window_icon = QIcon(str(self.paths.resource("resources/icons/Automy1.png")))
        if not window_icon.isNull():
            self.setWindowIcon(window_icon)
        self.ui_settings = QSettings(str(self.paths.ui_settings_file), QSettings.IniFormat)
        self.ui_scale = UiScale(self.ui_settings.value("appearance/scale", 1.0))
        self._client_boxes: Dict[str, QWidget] = {}
        self._field_box_layouts: List[QVBoxLayout] = []

        self.theme_mode = ThemeMode.LIGHT
        self.validation_service = ValidationService()
        self.excel_service = ExcelService(self.validation_service)
        self.catalog_service = CatalogService()
        self.profile_service = ProfileService(str(self.paths.profiles_dir))
        self.credential_service = CredentialService()
        self.client_filter: List[str] = []
        self.line_filter: List[str] = []
        self.product_filter_by_line: Dict[str, List[str]] = {}
        self.client_links: Dict[str, str] = {}
        self.catalogos = self._load_catalogs()
        self.catalog_options = self._catalog_options_from_catalogs()
        self.catalog_option_sets = self._catalog_option_sets()
        self.runner = AutomyRunner()
        self.toast = ToastManager(self, self.ui_scale)

        self.params = self._blank_params()
        self.product_import_path = ""
        self.active_profile_path = ""
        self.active_profile_name = ""
        self.loading = False
        self.dirty_client = False
        self.dirty_products = False
        self._client_invalid_state: bool | None = None
        self._validation_attempted = False
        self._validation_messages: Dict[str, str] = {}
        self.comment_manual_mode = False
        self.automy_credentials = AutomyCredentials()
        self._last_run_status = "idle"
        self._applied_theme_key: tuple[str, float] | None = None
        self._applied_fluent_theme: ThemeMode | None = None

        self.field_inputs: Dict[str, QLineEdit | QComboBox] = {}
        self.critical_buttons: List[QPushButton] = []

        self.product_model = ProductTableModel([])
        self._apply_product_catalogs()
        self.product_model.dataChanged.connect(lambda *_args: self._mark_products_dirty())
        self.product_proxy = ProductFilterProxyModel()
        self.product_proxy.setSourceModel(self.product_model)
        self.product_delegate: ProductItemDelegate | None = None

        self._build_ui()
        self._connect_runner()
        self._apply_ui_scale(center=True)
        self._load_initial_data()
        self._settle_layout()

        self.state_update_timer = QTimer(self)
        self.state_update_timer.setSingleShot(True)
        self.state_update_timer.setInterval(90)
        self.state_update_timer.timeout.connect(self._update_all_state)

        self.comment_update_timer = QTimer(self)
        self.comment_update_timer.setSingleShot(True)
        self.comment_update_timer.setInterval(260)
        self.comment_update_timer.timeout.connect(self._regenerate_comment_silently)

    @staticmethod
    def _blank_params() -> OrderParams:
        return OrderParams(
            nro_oc="",
            adjuntar_pdf="",
            unidad="",
            servicio="",
            cliente="",
            direccion_entrega="",
            contacto_nombre="",
            contacto_telefono="",
            departamento="",
            provincia="",
            distrito="",
            cliente_institucional="",
            comentarios="",
            direccion_nueva="NO",
            contacto_nuevo="NO",
            hora_inicio="",
            hora_fin="",
            igv="",
            moneda="",
            regularizar_adelanto="",
            motivo="SIN OC",
        )

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        self.root_layout = QVBoxLayout(root)

        self.root_layout.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_client_tab(), self._std_icon("SP_ComputerIcon"), "Cliente")
        self.tabs.addTab(self._build_products_tab(), self._std_icon("SP_FileDialogDetailedView"), "Producto")
        self.tabs.addTab(self._build_run_tab(), self._std_icon("SP_DialogApplyButton"), "Ejecución")
        shipment_service = ShipmentService(
            self.paths.resource("samples/envio/Cuadro de Envios - Formato.xlsx")
        )
        self.shipment_tab = ShipmentTab(shipment_service, self)
        self.tabs.addTab(self.shipment_tab, self._std_icon("SP_DriveFDIcon"), "Envío")
        self.market_tab = MarketTab(self.ui_scale, self)
        self.tabs.addTab(self.market_tab, self._std_icon("SP_FileDialogContentsView"), "Mercado")
        self.tabs.currentChanged.connect(self._animate_tab)
        self.root_layout.addWidget(self.tabs, 1)

        footer = QLabel("Desarrollado por Alonso Espiritu")
        footer.setObjectName("FooterLabel")
        footer.setAlignment(Qt.AlignRight)
        self.root_layout.addWidget(footer)

    def _load_catalogs(self):
        try:
            return self.catalog_service.load()
        except (OSError, ValueError, TypeError):
            logger.exception("No se pudieron cargar los catálogos embebidos")
            return None

    def _catalog_options_from_catalogs(self) -> Dict[str, List[str]]:
        if self.catalogos is None:
            return {
                "cliente": self._client_options(),
                "direccion_nueva": ["NO", "SI"],
                "contacto_nuevo": ["NO", "SI"],
                "motivo": ["SIN OC", "CON OC"],
            }
        otros = self.catalogos.otros
        return {
            "cliente": self._client_options(),
            "cliente_institucional": self._filtered_clients(),
            "unidad": otros.get("unidad", []),
            "direccion_nueva": otros.get("direccion_nueva", []),
            "contacto_nuevo": otros.get("contacto_nuevo", []),
            "hora_inicio": otros.get("hora_inicio", []),
            "hora_fin": otros.get("hora_fin", []),
            "igv": otros.get("igv", []),
            "moneda": otros.get("moneda", []),
            "regularizar_adelanto": otros.get("regularizar_adelanto", []),
            "motivo": ["SIN OC", "CON OC"],
        }

    def _catalog_option_sets(self) -> Dict[str, set[str]]:
        return {
            key: set(values)
            for key, values in self.catalog_options.items()
        }

    def _apply_product_catalogs(self) -> None:
        otros = self.catalogos.otros if self.catalogos is not None else {}
        self.product_model.set_catalogs(
            self._filtered_lineas(),
            self._filtered_productos_por_linea(),
            otros.get("unidad_producto", []),
            otros.get("categoria_producto", []),
        )

    def _filtered_clients(self) -> List[str]:
        if self.catalogos is None:
            return self._unique_values([*self.client_filter, *self.client_links.values()])
        if not self.client_filter:
            return self._unique_values([*self.catalogos.clientes, *self.client_links.values()])
        base = [client for client in self.catalogos.clientes if client in set(self.client_filter)]
        custom = [client for client in self.client_filter if client not in base]
        return self._unique_values([*base, *custom])

    def _client_options(self) -> List[str]:
        linked = list(self.client_links.keys())
        current = getattr(self, "params", OrderParams()).cliente
        return self._unique_values([*linked, current])

    def _filtered_lineas(self) -> List[str]:
        if self.catalogos is None:
            return self._unique_values(self.line_filter)
        if not self.line_filter:
            return self.catalogos.lineas
        selected = set(self.line_filter)
        base = [linea for linea in self.catalogos.lineas if linea in selected]
        custom = [linea for linea in self.line_filter if linea not in base]
        return self._unique_values([*base, *custom])

    def _filtered_productos_por_linea(self) -> Dict[str, List[str]]:
        lineas = self._filtered_lineas()
        filtered: Dict[str, List[str]] = {}
        for linea in lineas:
            productos = self.catalogos.productos_por_linea.get(linea, []) if self.catalogos is not None else []
            selected = self.product_filter_by_line.get(linea, [])
            if selected:
                productos = selected
            filtered[linea] = productos
        return filtered

    def _profile_filters(self) -> Dict[str, object]:
        return {
            "clientes": self.client_filter,
            "lineas": self.line_filter,
            "productos_por_linea": self.product_filter_by_line,
            "enlaces_clientes": self.client_links,
        }

    def _apply_profile_filters(self, filters: dict[str, object] | None) -> None:
        filters = filters or {}
        clientes = filters.get("clientes", [])
        lineas = filters.get("lineas", [])
        productos = filters.get("productos_por_linea", {})
        enlaces = filters.get("enlaces_clientes", {})
        self.client_filter = [str(item) for item in clientes] if isinstance(clientes, list) else []
        self.line_filter = [str(item) for item in lineas] if isinstance(lineas, list) else []
        self.product_filter_by_line = {
            str(linea): [str(producto) for producto in values]
            for linea, values in productos.items()
            if isinstance(values, list)
        } if isinstance(productos, dict) else {}
        self.client_links = {
            str(cliente): str(institucion)
            for cliente, institucion in enlaces.items()
            if str(cliente).strip() and str(institucion).strip()
        } if isinstance(enlaces, dict) else {}
        self._clean_filters()

    def _clean_filters(self) -> None:
        self.client_filter = self._unique_values(self.client_filter)
        self.line_filter = self._unique_values(self.line_filter)
        self.product_filter_by_line = {
            linea: self._unique_values(productos)
            for linea, productos in self.product_filter_by_line.items()
            if linea
        }

    @staticmethod
    def _unique_values(values: Iterable[str]) -> List[str]:
        seen: set[str] = set()
        result: List[str] = []
        for value in values:
            item = str(value or "").strip()
            key = " ".join(item.upper().split())
            if item and key not in seen:
                seen.add(key)
                result.append(item)
        return result

    def _client_field_widget(self, key: str) -> QLineEdit | QComboBox:
        opciones = self.catalog_options.get(key, [])
        if opciones or key in {"cliente", "cliente_institucional"}:
            field = QComboBox()
            editable = key in {"cliente", "cliente_institucional"}
            field.setEditable(editable)
            field.setMinimumWidth(0)
            field.setMinimumContentsLength(0)
            field.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            field.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            field.setInsertPolicy(QComboBox.NoInsert)
            field.addItems(self._combo_options(opciones))
            field.setCurrentIndex(-1)
            if field.lineEdit():
                field.lineEdit().setClearButtonEnabled(True)
            if editable:
                completer = QCompleter(opciones, field)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                field.setCompleter(completer)
            if key in {"cliente_institucional", "direccion_nueva", "contacto_nuevo", "motivo"}:
                field.setEnabled(False)
                field.setProperty("locked", True)
            field.currentTextChanged.connect(lambda _text, field_key=key: self._handle_client_field_changed(field_key))
            return field

        field = QLineEdit()
        field.setMinimumWidth(0)
        field.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        field.setClearButtonEnabled(True)
        if key == "motivo":
            field.setEnabled(False)
            field.setProperty("locked", True)
        field.textChanged.connect(lambda _text, field_key=key: self._handle_client_field_changed(field_key))
        return field

    @staticmethod
    def _field_text(field: QLineEdit | QComboBox) -> str:
        if isinstance(field, QComboBox):
            return field.currentText().strip()
        return field.text().strip()

    @staticmethod
    def _set_field_text(field: QLineEdit | QComboBox, value: str) -> None:
        if isinstance(field, QComboBox):
            MainWindow._set_combo_text(field, value)
        else:
            field.setText(value or "")

    @staticmethod
    def _combo_options(options: Iterable[str]) -> List[str]:
        return [str(option) for option in options if str(option).strip()]

    @staticmethod
    def _set_combo_text(field: QComboBox, value: str) -> None:
        text = str(value or "").strip()
        if not text:
            field.setCurrentIndex(-1)
            if field.isEditable():
                field.setCurrentText("")
            return
        if field.isEditable():
            field.setCurrentText(text)
            return
        index = field.findText(text, Qt.MatchFixedString)
        field.setCurrentIndex(index if index >= 0 else -1)

    def _refresh_combo_options(self) -> None:
        for key, field in self.field_inputs.items():
            if not isinstance(field, QComboBox):
                continue
            actual = field.currentText()
            opciones = self.catalog_options.get(key, [])
            if actual and actual not in opciones and key not in {"cliente", "cliente_institucional"}:
                opciones = [actual, *opciones]
            field.blockSignals(True)
            field.clear()
            field.addItems(self._combo_options(opciones))
            self._set_combo_text(field, actual if actual in opciones else "")
            if field.isEditable():
                completer = QCompleter(opciones, field)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                completer.setFilterMode(Qt.MatchContains)
                field.setCompleter(completer)
            field.blockSignals(False)

    def _add_client_field(self, layout: QGridLayout, key: str, label: str, row: int, column_group: int) -> None:
        label_widget = QLabel(label)
        label_widget.setObjectName("FieldLabel")
        field = self._client_field_widget(key)
        self.field_inputs[key] = field
        base_col = column_group * 2
        layout.addWidget(label_widget, row, base_col)
        layout.addWidget(field, row, base_col + 1)
        layout.setColumnStretch(base_col + 1, 1)

    def _client_field_box(self, key: str, label: str) -> QWidget:
        box = QWidget()
        box.setObjectName("FieldBox")
        box.setMinimumWidth(0)
        box.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        self._field_box_layouts.append(layout)
        label_widget = QLabel(label)
        label_widget.setObjectName("FieldLabel")
        field = self._client_field_widget(key)
        field.setMinimumWidth(0)
        field.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.field_inputs[key] = field
        self._client_boxes[key] = box
        layout.addWidget(label_widget)
        layout.addWidget(field)
        return box

    def _add_client_box(self, layout: QGridLayout, key: str, label: str, row: int, column: int, row_span: int = 1, col_span: int = 1) -> None:
        layout.addWidget(self._client_field_box(key, label), row, column, row_span, col_span)

    def _build_header(self) -> QWidget:
        self.app_header = QFrame()
        self.app_header.setObjectName("AppHeader")

        self.header_layout = QGridLayout(self.app_header)
        self.header_layout.setVerticalSpacing(0)

        self.header_balance = QWidget()
        self.header_balance.setObjectName("HeaderBalance")
        self.header_balance.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self.header_logo_layout = QHBoxLayout(self.header_balance)
        self.header_logo_layout.setContentsMargins(0, 0, 0, 0)
        self.header_logo_layout.setSpacing(0)
        self.header_logo_label = QLabel()
        self.header_logo_label.setObjectName("HeaderLogo")
        self.header_logo_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.header_logo_label.setScaledContents(False)
        self.header_logo_label.setToolTip("Sistemas Analíticos")
        self.header_logo_layout.addWidget(self.header_logo_label, 1)
        self.header_layout.addWidget(self.header_balance, 0, 0)

        self.header_title_layout = QVBoxLayout()
        title = QLabel("InterAutomy")
        title.setObjectName("HeaderTitle")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("Gestión Moderna de Perfiles, Clientes, Líneas y Productos en Automy")
        subtitle.setObjectName("HeaderSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        subtitle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.path_label = QLabel("")
        self.path_label.setObjectName("HeaderPath")
        self.path_label.hide()
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.header_title_layout.addStretch(1)
        self.header_title_layout.addWidget(title)
        self.header_title_layout.addWidget(subtitle)
        self.header_title_layout.addStretch(1)
        self.header_layout.addLayout(self.header_title_layout, 0, 1)

        self.header_actions_box = QFrame()
        self.header_actions_box.setObjectName("HeaderActionsBox")
        self.header_actions_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.header_actions_layout = QVBoxLayout()
        self.header_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.header_status_layout = QHBoxLayout()
        self.status_badge = QLabel("Listo")
        self.status_badge.setObjectName("StatusBadge")
        self.status_badge.setAlignment(Qt.AlignCenter)
        self.header_status_layout.addWidget(self.status_badge, 1)
        self.scale_selector = QComboBox()
        self.scale_selector.setObjectName("ScaleSelector")
        self.scale_selector.setToolTip("Escala visual de la interfaz.")
        self.scale_selector.addItems(
            [f"{round(scale * 100)}%" for scale in AVAILABLE_SCALES]
        )
        self.scale_selector.setCurrentText(self.ui_scale.label)
        self.scale_selector.currentTextChanged.connect(self._change_ui_scale)
        self.header_status_layout.addWidget(self.scale_selector)
        self.theme_toggle = QPushButton("☾")
        self.theme_toggle.setObjectName("ThemeToggle")
        self.theme_toggle.setCheckable(True)
        self.theme_toggle.clicked.connect(self._toggle_theme)
        self.header_status_layout.addWidget(self.theme_toggle)
        self.header_actions_layout.addLayout(self.header_status_layout)

        self.header_quick_layout = QHBoxLayout()
        self.header_quick_layout.addWidget(
            self._button(
                "Cargar Perfil",
                "SP_DialogOpenButton",
                self.load_profile,
                variant="primary",
                tooltip="Carga un perfil guardado con cliente y productos.",
            )
        )
        self.header_quick_layout.addWidget(
            self._button(
                "Guardar Perfil",
                "SP_DialogSaveButton",
                self.save_profile,
                tooltip="Guarda como JSON todos los datos, productos y filtros del perfil.",
            )
        )
        self.header_actions_layout.addLayout(self.header_quick_layout)
        self.header_actions_box.setLayout(self.header_actions_layout)
        self.header_layout.addWidget(self.header_actions_box, 0, 2)
        self.header_layout.setColumnStretch(1, 1)
        return self.app_header

    def _build_client_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        tab = QWidget()
        tab.setMinimumWidth(0)
        scroll.setWidget(tab)
        self.client_tab_layout = QVBoxLayout(tab)

        section = self._section("Información De Cliente")
        self.client_section_layout = QVBoxLayout(section)

        self.client_action_layout = QHBoxLayout()
        self.client_action_layout.addWidget(
            self._button(
                "Subir OC",
                "SP_DialogOpenButton",
                self.select_pdf,
                tooltip="Selecciona la orden de compra.",
            )
        )
        self.client_action_layout.addWidget(
            self._button(
                "Cliente",
                "SP_ComputerIcon",
                self.configure_client_links,
                tooltip="Crea clientes cortos y enlázalos a instituciones.",
            )
        )
        self.client_action_layout.addWidget(
            self._button(
                "Institución",
                "SP_DirIcon",
                self.configure_client_filter,
                tooltip="Filtra la lista de instituciones disponibles.",
            )
        )
        self.client_action_layout.addStretch(1)
        self.client_section_layout.addLayout(self.client_action_layout)

        form_panel = self._soft_panel()
        self.client_form_layout = QGridLayout(form_panel)

        self._add_client_box(self.client_form_layout, "nro_oc", "NRO OC", 0, 0)
        self._add_client_box(self.client_form_layout, "adjuntar_pdf", "Archivo OC", 0, 1)
        self._add_client_box(self.client_form_layout, "unidad", "Unidad", 1, 0)
        self._add_client_box(self.client_form_layout, "servicio", "Servicio", 1, 1)
        self._add_client_box(self.client_form_layout, "cliente", "Cliente", 2, 0)
        self._add_client_box(self.client_form_layout, "cliente_institucional", "Institución", 2, 1)
        self._add_client_box(self.client_form_layout, "departamento", "Departamento", 3, 0)
        self._add_client_box(self.client_form_layout, "provincia", "Provincia", 3, 1)
        self._add_client_box(self.client_form_layout, "distrito", "Distrito", 4, 0)
        self._add_client_box(self.client_form_layout, "direccion_entrega", "Dirección", 4, 1)
        self._add_client_box(self.client_form_layout, "contacto_nombre", "Contacto", 5, 0)
        self._add_client_box(self.client_form_layout, "contacto_telefono", "Teléfono", 5, 1)

        self._add_client_box(self.client_form_layout, "direccion_nueva", "Dirección Nueva", 2, 2)
        self._add_client_box(self.client_form_layout, "contacto_nuevo", "Contacto Nuevo", 2, 3)
        self._add_client_box(self.client_form_layout, "hora_inicio", "Hora Inicio", 3, 2)
        self._add_client_box(self.client_form_layout, "hora_fin", "Hora Fin", 3, 3)
        self._add_client_box(self.client_form_layout, "igv", "IGV", 4, 2)
        self._add_client_box(self.client_form_layout, "moneda", "Moneda", 4, 3)
        self._add_client_box(self.client_form_layout, "regularizar_adelanto", "Adelanto", 5, 2)
        self._add_client_box(self.client_form_layout, "motivo", "Motivo", 5, 3)

        self.comment_panel = QWidget()
        self.comment_panel.setObjectName("CommentPanel")
        self.comment_panel.setMinimumWidth(0)
        self.comment_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.comment_layout = QVBoxLayout(self.comment_panel)
        self.comment_layout.setContentsMargins(0, 0, 0, 0)
        self.comment_header_layout = QHBoxLayout()
        self.comment_header_layout.setContentsMargins(0, 0, 0, 0)
        comment_title = QLabel("Comentario Final")
        comment_title.setObjectName("SectionTitle")
        self.edit_comment_checkbox = QCheckBox("Editar Comentario")
        self.edit_comment_checkbox.setToolTip("Permite escribir el comentario final manualmente.")
        self.edit_comment_checkbox.toggled.connect(self._set_comment_manual_mode)
        self.comment_text = QTextEdit()
        self.comment_text.setReadOnly(True)
        self.comment_text.setFocusPolicy(Qt.NoFocus)
        self.comment_text.textChanged.connect(self._mark_client_dirty)
        self.comment_header_layout.addWidget(comment_title)
        self.comment_header_layout.addStretch(1)
        self.comment_header_layout.addWidget(self.edit_comment_checkbox)
        self.comment_layout.addLayout(self.comment_header_layout)
        self.comment_layout.addWidget(self.comment_text, 1)
        self.client_form_layout.addWidget(self.comment_panel, 0, 2, 2, 2)

        for column in range(4):
            self.client_form_layout.setColumnStretch(column, 1)
            self.client_form_layout.setColumnMinimumWidth(column, 0)

        self.client_section_layout.addWidget(form_panel)
        self.client_tab_layout.addWidget(section)
        return scroll

    def _build_products_tab(self) -> QWidget:
        tab = QWidget()
        self.products_tab_layout = QVBoxLayout(tab)

        section = self._section("Línea De Productos")
        self.products_section_layout = QVBoxLayout(section)

        self.product_toolbar = QWidget()
        self.product_toolbar_layout = QHBoxLayout(self.product_toolbar)
        self.product_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.line_filter_button = self._button(
            "Línea",
            "SP_DirIcon",
            self.configure_line_filter,
            tooltip="Filtra las líneas de producto disponibles.",
        )
        self.product_filter_button = self._button(
            "Producto",
            "SP_FileDialogDetailedView",
            self.configure_product_filter,
            tooltip="Filtra los productos disponibles por línea.",
        )
        self.add_line_combo = QComboBox()
        self.add_line_combo.setEditable(True)
        self.add_line_combo.setMinimumWidth(0)
        self.add_line_combo.setMinimumContentsLength(0)
        self.add_line_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.add_line_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.add_line_combo.setToolTip("Línea para el nuevo producto.")
        self._refresh_add_line_combo()
        self.add_product_button = self._button(
            "Agregar",
            "SP_FileIcon",
            self.add_product,
            variant="success",
            tooltip="Agrega una fila editable a la tabla.",
        )
        self.duplicate_product_button = self._button(
            "Duplicar", "SP_FileDialogNewFolder", self.duplicate_product
        )
        self.delete_product_button = self._button(
            "Eliminar", "SP_TrashIcon", self.delete_product, variant="danger"
        )
        self.export_excel_button = self._button(
            "Excel",
            "SP_DialogSaveButton",
            self.export_advisor_excel,
            tooltip="Exporta los productos actuales en formato Pedido Asesor.",
        )
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Buscar O Filtrar Productos...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.product_proxy.set_query)
        self.search_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.product_count_label = QLabel("0 Items")
        self.product_count_label.setObjectName("Caption")
        self.product_count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.product_toolbar_widgets = [
            self.line_filter_button,
            self.product_filter_button,
            self.add_line_combo,
            self.add_product_button,
            self.duplicate_product_button,
            self.delete_product_button,
            self.export_excel_button,
            self.search_input,
            self.product_count_label,
        ]
        self.product_toolbar_layout.addWidget(self.line_filter_button)
        self.product_toolbar_layout.addWidget(self.product_filter_button)
        self.product_toolbar_layout.addWidget(self.add_line_combo)
        self.product_toolbar_layout.addWidget(self.add_product_button)
        self.product_toolbar_layout.addWidget(self.duplicate_product_button)
        self.product_toolbar_layout.addWidget(self.delete_product_button)
        self.product_toolbar_layout.addWidget(self.export_excel_button)
        self.product_toolbar_layout.addWidget(self.search_input, 1)
        self.product_toolbar_layout.addWidget(self.product_count_label)
        self.products_section_layout.addWidget(self.product_toolbar)

        self.product_table = ProductTableView()
        self.product_table.setModel(self.product_proxy)
        self._install_product_delegate()
        self.product_table.setAlternatingRowColors(True)
        self.product_table.setSortingEnabled(False)
        self.product_table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.product_table.setSelectionMode(QTableView.ExtendedSelection)
        self.product_table.setWordWrap(True)
        self.product_table.setTextElideMode(Qt.ElideRight)
        self.product_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.product_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.product_table.setVerticalScrollMode(QAbstractItemView.ScrollPerItem)
        self.product_table.deletePressed.connect(self.delete_product)
        self.product_table.verticalHeader().setVisible(False)
        self.product_table.horizontalHeader().setStretchLastSection(False)
        self.product_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.product_table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
        )
        self.product_table.viewport().installEventFilter(self)
        self.product_model.modelReset.connect(self._update_product_table_layout)
        self.product_proxy.modelReset.connect(self._update_product_table_layout)
        self.product_proxy.rowsInserted.connect(self._update_product_table_layout)
        self.product_proxy.rowsRemoved.connect(self._update_product_table_layout)
        self.search_input.textChanged.connect(lambda _text: QTimer.singleShot(0, self._update_product_table_layout))
        QTimer.singleShot(0, self._update_product_table_layout)
        QTimer.singleShot(220, self._update_product_table_layout)
        self.products_section_layout.addWidget(self.product_table, 1)

        self.products_tab_layout.addWidget(section, 1)
        return tab

    def _install_product_delegate(self) -> None:
        otros = self.catalogos.otros if self.catalogos is not None else {}
        self.product_delegate = ProductItemDelegate(
            self._filtered_lineas(),
            self._filtered_productos_por_linea(),
            otros.get("unidad_producto", []),
            otros.get("categoria_producto", []),
            self.ui_scale,
            self.product_table,
        )
        self.product_table.setItemDelegate(self.product_delegate)

    def _refresh_add_line_combo(self) -> None:
        if not hasattr(self, "add_line_combo"):
            return
        current = self.add_line_combo.currentText().strip()
        lineas = self._filtered_lineas()
        self.add_line_combo.blockSignals(True)
        self.add_line_combo.clear()
        self.add_line_combo.addItems(self._combo_options(lineas))
        self._set_combo_text(self.add_line_combo, current if current in lineas else "")
        completer = QCompleter(lineas, self.add_line_combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.add_line_combo.setCompleter(completer)
        if self.add_line_combo.lineEdit():
            self.add_line_combo.lineEdit().setClearButtonEnabled(True)
        self.add_line_combo.blockSignals(False)

    def _update_product_table_layout(self, *_args) -> None:
        if not hasattr(self, "product_table"):
            return
        self._resize_product_columns()
        self._update_product_group_spans()

    def _resize_product_columns(self) -> None:
        if not hasattr(self, "product_table"):
            return
        viewport_width = max(1, self.product_table.viewport().width())
        table_width = self.product_table.width()
        if table_width > viewport_width + self.ui_scale.px(80):
            viewport_width = max(
                1,
                table_width
                - self.product_table.verticalScrollBar().sizeHint().width()
                - self.ui_scale.px(8),
            )
        total_units = sum(PRODUCT_COLUMN_UNITS)
        assigned = 0
        last_column = len(PRODUCT_COLUMN_UNITS) - 1
        for column, units in enumerate(PRODUCT_COLUMN_UNITS):
            if column == last_column:
                width = max(self.ui_scale.px(42), viewport_width - assigned)
            else:
                width = max(
                    self.ui_scale.px(42),
                    int(viewport_width * units / total_units),
                )
                assigned += width
            self.product_table.setColumnWidth(column, width)

    def _update_product_group_spans(self) -> None:
        if not hasattr(self, "product_table"):
            return
        self.product_table.clearSpans()
        for proxy_row in range(self.product_proxy.rowCount()):
            source_index = self.product_proxy.mapToSource(self.product_proxy.index(proxy_row, 0))
            if self.product_model.is_group_row(source_index.row()):
                self.product_table.setSpan(proxy_row, 0, 1, self.product_proxy.columnCount())
                self.product_table.setRowHeight(proxy_row, self.ui_scale.px(34))
            else:
                self.product_table.setRowHeight(proxy_row, self.ui_scale.px(58))

    def _build_run_tab(self) -> QWidget:
        tab = QWidget()
        self.run_tab_layout = QVBoxLayout(tab)

        section = self._section("Ejecución Y Bitácora")
        self.run_section_layout = QVBoxLayout(section)

        title_label = QLabel("Ejecución Y Bitácora")
        title_label.setObjectName("SectionTitle")
        self.run_section_layout.addWidget(title_label)

        self.run_toolbar = QWidget()
        self.run_toolbar_layout = QHBoxLayout(self.run_toolbar)
        self.run_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.validate_button = self._button(
            "Validar Información",
            "SP_MessageBoxInformation",
            self.validate_information,
            tooltip="Revisa datos mínimos antes de ejecutar InterAutomy.",
        )
        self.run_button = self._button(
            "Ejecutar InterAutomy",
            "SP_ArrowRight",
            self.run_automy,
            variant="success",
            tooltip="Importa los productos y ejecuta Selenium con los datos actuales de la interfaz.",
        )
        self.credentials_button = self._button(
            "Credenciales",
            "SP_FileDialogInfoView",
            self.open_credentials_dialog,
            tooltip="Configura usuario y contraseña de Automy para esta sesión.",
        )
        self.autovalidation_check = AutoValidationSwitch(self, self.ui_scale)
        self.autovalidation_check.setToolTip("Activa la validación automática final en segundo plano.")
        self.autovalidation_check.toggled.connect(self._toggle_autovalidation)
        self.clear_logs_button = self._button(
            "Limpiar Bitácora", "SP_DialogResetButton", self.clear_logs
        )
        self.run_toolbar_widgets = [
            self.validate_button,
            self.run_button,
            self.credentials_button,
            self.autovalidation_check,
            self.clear_logs_button,
        ]
        self.run_toolbar_layout.addWidget(self.validate_button)
        self.run_toolbar_layout.addWidget(self.run_button)
        self.run_toolbar_layout.addWidget(self.credentials_button)
        self.run_toolbar_layout.addWidget(self.autovalidation_check)
        self.run_toolbar_layout.addStretch(1)
        self.run_toolbar_layout.addWidget(self.clear_logs_button)
        self.run_section_layout.addWidget(self.run_toolbar)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.run_section_layout.addWidget(self.progress)

        self.log_console = QPlainTextEdit()
        self.log_console.setObjectName("LogConsole")
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumBlockCount(1200)
        self.log_console.setPlaceholderText("La Bitácora De InterAutomy Aparecerá Aquí En Tiempo Real.")
        self.run_section_layout.addWidget(self.log_console, 1)

        self.run_tab_layout.addWidget(section, 1)
        return tab

    def _section(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Section")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        frame.setAccessibleName(title)
        return frame

    def _soft_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("SoftPanel")
        return panel

    def _button(
        self,
        text: str,
        icon_name: str,
        handler,
        variant: str | None = None,
        tooltip: str = "",
    ) -> QPushButton:
        button = QPushButton(text)
        button.setIcon(self._std_icon(icon_name))
        button.setProperty("icon_name", icon_name)
        button.setIconSize(self.ui_scale.size(17, 17))
        button.setCursor(Qt.PointingHandCursor)
        button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        if variant:
            button.setProperty("variant", variant)
        if tooltip:
            button.setToolTip(tooltip)
        button.clicked.connect(handler)
        if text in {
            "Cargar Perfil",
            "Guardar Perfil",
            "Subir OC",
            "Institución",
            "Cliente",
            "Línea",
            "Producto",
            "Agregar",
            "Duplicar",
            "Eliminar",
            "Excel",
            "Ejecutar InterAutomy",
            "Validar Información",
            "Credenciales",
            "Limpiar Bitácora",
        }:
            self.critical_buttons.append(button)
        return button

    def _std_icon(self, name: str) -> QIcon:
        return app_icon(name, self, color=self._icon_color())

    def _icon_color(self) -> str:
        colors = palette(self.theme_mode)
        return "#f8fbff" if self.theme_mode == ThemeMode.DARK else colors["text"]

    def _refresh_action_icons(self) -> None:
        for button in self.findChildren(QPushButton):
            icon_name = button.property("icon_name")
            if isinstance(icon_name, str):
                button.setIcon(self._std_icon(icon_name))
        if hasattr(self, "tabs"):
            for index, icon_name in enumerate(
                ("SP_ComputerIcon", "SP_FileDialogDetailedView", "SP_DialogApplyButton")
            ):
                if index < self.tabs.count():
                    self.tabs.setTabIcon(index, self._std_icon(icon_name))

    def _install_clear_button(self, line_edit: QLineEdit, host: QWidget | None = None) -> QToolButton:
        host = host or line_edit
        line_edit.setClearButtonEnabled(False)
        for action in list(line_edit.actions()):
            if action.property("interautomy_clear_action"):
                line_edit.removeAction(action)
                action.deleteLater()
        for button in line_edit.findChildren(QToolButton):
            if button.property("interautomy_clear_button"):
                if button.parentWidget() is host:
                    return button
            button.hide()
        for button in host.findChildren(QToolButton):
            if button.property("interautomy_clear_button"):
                return button

        button = QToolButton(host)
        button.setProperty("interautomy_clear_button", True)
        button.setText("×")
        button.clicked.connect(line_edit.clear)
        button.hide()

        def update_visibility(text: str = "") -> None:
            button.setVisible(
                bool(text or line_edit.text())
                and host.isEnabled()
                and line_edit.isEnabled()
                and not line_edit.isReadOnly()
            )

        line_edit.textChanged.connect(update_visibility)
        update_visibility()
        return button

    def _scale_field_accessory_buttons(self) -> None:
        button_size = self.ui_scale.px(17, minimum=14)
        font_size = self.ui_scale.px(14, minimum=10)
        gap = self.ui_scale.px(5, minimum=3)
        radius = max(3, button_size // 2)
        colors = palette(self.theme_mode)
        hover = colors["primary_hover"]
        text_color = colors["muted"]
        def style_button(button: QToolButton) -> None:
            button.setFixedSize(button_size, button_size)
            button.setText("×")
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setCursor(Qt.PointingHandCursor)
            button.setFocusPolicy(Qt.NoFocus)
            button.setAutoRaise(True)
            button.setStyleSheet(
                f"""
                QToolButton {{
                    background: transparent;
                    border: none;
                    border-radius: {radius}px;
                    color: {text_color};
                    font-family: "Segoe UI", "Arial";
                    font-size: {font_size}px;
                    font-weight: 700;
                    margin: 0px;
                    padding: 0px;
                }}
                QToolButton:hover {{
                    background: {hover};
                }}
                """
            )

        handled_line_edits: set[QLineEdit] = set()
        for combo in self.findChildren(QComboBox):
            line_edit = combo.lineEdit()
            if line_edit is None:
                continue
            handled_line_edits.add(line_edit)
            button = self._install_clear_button(line_edit, combo)
            line_edit.setTextMargins(0, 0, button_size + gap, 0)
            style_button(button)
            drop_down_width = self.ui_scale.px(20, minimum=14)
            combo_gap = self.ui_scale.px(2, minimum=2)
            x = max(0, combo.width() - drop_down_width - button_size - combo_gap)
            y = max(0, (combo.height() - button_size) // 2)
            button.move(x, y)
            button.raise_()
            button.setVisible(bool(line_edit.text()) and combo.isEnabled() and line_edit.isEnabled())

        for line_edit in self.findChildren(QLineEdit):
            if line_edit in handled_line_edits:
                continue
            button = self._install_clear_button(line_edit)
            line_edit.setTextMargins(0, 0, button_size + gap, 0)
            style_button(button)
            x = max(0, line_edit.width() - button_size - gap)
            y = max(0, (line_edit.height() - button_size) // 2)
            button.move(x, y)
            button.raise_()
            button.setVisible(bool(line_edit.text()) and line_edit.isEnabled() and not line_edit.isReadOnly())

    def _change_ui_scale(self, text: str) -> None:
        scale = UiScale.from_percent(text)
        if scale == self.ui_scale:
            return
        self.ui_scale = scale
        self.ui_settings.setValue("appearance/scale", scale.factor)
        self.ui_settings.sync()
        self._apply_ui_scale(center=True)

    def _apply_ui_scale(self, center: bool = False) -> None:
        s = self.ui_scale.px

        self.root_layout.setContentsMargins(s(16), s(16), s(16), s(10))
        self.root_layout.setSpacing(s(10))

        self.app_header.setFixedHeight(s(100))
        self.header_layout.setContentsMargins(s(20), s(12), s(20), s(12))
        self.header_layout.setHorizontalSpacing(s(16))
        self.header_layout.setVerticalSpacing(0)
        self.header_title_layout.setSpacing(s(5))
        self.header_logo_label.setFixedSize(self.ui_scale.size(306, 68))
        self.header_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.header_actions_layout.setSpacing(s(8))
        self.header_status_layout.setSpacing(s(8))
        self.header_quick_layout.setSpacing(s(8))
        for widget in (self.header_balance, self.header_actions_box):
            widget.setFixedWidth(s(320))
        self.scale_selector.setFixedSize(self.ui_scale.size(76, 34))
        self.theme_toggle.setFixedSize(self.ui_scale.size(38, 34))

        for tab_layout in (
            self.client_tab_layout,
            self.products_tab_layout,
            self.run_tab_layout,
        ):
            tab_layout.setContentsMargins(s(3), s(3), s(3), s(3))
            tab_layout.setSpacing(s(10))
        self.tabs.setIconSize(self.ui_scale.size(17, 17))

        self.client_section_layout.setContentsMargins(s(16), s(12), s(16), s(12))
        self.client_section_layout.setSpacing(s(8))
        self.client_action_layout.setSpacing(s(8))
        self.client_form_layout.setContentsMargins(s(16), s(14), s(16), s(14))
        self.client_form_layout.setHorizontalSpacing(s(16))
        self.client_form_layout.setVerticalSpacing(s(8))
        self.comment_layout.setContentsMargins(0, 0, 0, 0)
        self.comment_layout.setSpacing(s(6))
        self.comment_header_layout.setSpacing(s(8))
        self.comment_text.setMinimumHeight(s(104))
        for layout in self._field_box_layouts:
            layout.setSpacing(s(4))
        for field in self.field_inputs.values():
            field.setFixedHeight(s(38))

        self.products_section_layout.setContentsMargins(s(18), s(16), s(18), s(18))
        self.products_section_layout.setSpacing(s(12))
        self.product_toolbar_layout.setContentsMargins(0, 0, s(8), 0)
        self.product_toolbar_layout.setSpacing(s(8))
        self.add_line_combo.setFixedSize(self.ui_scale.size(245, 40))
        self.search_input.setFixedHeight(s(40))
        for button, base_width in (
            (self.line_filter_button, 92),
            (self.product_filter_button, 112),
            (self.add_product_button, 116),
            (self.duplicate_product_button, 112),
            (self.delete_product_button, 108),
            (self.export_excel_button, 82),
        ):
            button.setFixedWidth(s(base_width))
        self.product_count_label.setFixedWidth(s(94))

        self.run_section_layout.setContentsMargins(s(22), s(20), s(22), s(22))
        self.run_section_layout.setSpacing(s(14))
        self.run_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self.run_toolbar_layout.setSpacing(s(8))
        self.autovalidation_check.setFixedHeight(s(38))
        self.autovalidation_check.set_scale(self.ui_scale)
        self.market_tab.set_scale(self.ui_scale)

        icon_size = self.ui_scale.size(17, 17)
        for button in self.critical_buttons:
            button.setIconSize(icon_size)
            button.setFixedHeight(s(38))
            if button.text() in {"Subir OC", "Cliente", "Institución"}:
                button.setMinimumWidth(s(112))

        self.product_table.setMinimumHeight(s(250))
        self.product_table.horizontalHeader().setMinimumHeight(s(44))
        self.product_table.verticalHeader().setDefaultSectionSize(s(46))
        if self.product_delegate is not None:
            self.product_delegate.ui_scale = self.ui_scale
        self.toast.set_scale(self.ui_scale)

        self._apply_theme()
        self.setFixedSize(self.ui_scale.window_size())
        self.updateGeometry()
        self._scale_field_accessory_buttons()
        self._update_product_table_layout()
        QTimer.singleShot(0, self._scale_field_accessory_buttons)
        QTimer.singleShot(80, self._scale_field_accessory_buttons)
        QTimer.singleShot(0, self._update_product_table_layout)
        if center:
            self._center_window()
            QTimer.singleShot(0, self._center_window)

    def _center_window(self) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())

    def _connect_runner(self) -> None:
        self.runner.started.connect(self._on_runner_started)
        self.runner.log.connect(self.append_log)
        self.runner.finished.connect(self._on_runner_finished)
        self.runner.manual_validation_requested.connect(self._on_manual_validation_requested)

    def _apply_theme(self) -> None:
        theme_key = (self.theme_mode.value, self.ui_scale.factor)
        if hasattr(self, "theme_toggle"):
            dark = self.theme_mode == ThemeMode.DARK
            self.theme_toggle.blockSignals(True)
            self.theme_toggle.setChecked(dark)
            self.theme_toggle.setText("☀" if dark else "☾")
            self.theme_toggle.setToolTip("Cambiar a tema claro" if dark else "Cambiar a tema oscuro")
            self.theme_toggle.blockSignals(False)
        if self._applied_theme_key != theme_key:
            self.setStyleSheet(stylesheet(self.theme_mode, self.ui_scale))
            self._applied_theme_key = theme_key
        self._refresh_action_icons()
        self._scale_field_accessory_buttons()
        self._update_header_logo()
        if set_fluent_theme and FluentTheme and self._applied_fluent_theme != self.theme_mode:
            set_fluent_theme(FluentTheme.DARK if self.theme_mode == ThemeMode.DARK else FluentTheme.LIGHT)
            self._applied_fluent_theme = self.theme_mode
        self.product_model.set_dark_mode(self.theme_mode == ThemeMode.DARK)
        self._update_pdf_state()

    def _update_header_logo(self) -> None:
        if not hasattr(self, "header_logo_label"):
            return
        logo_name = "resources/logos/SISA2.png"
        logo_path = self.paths.resource(logo_name)
        pixmap = QPixmap(str(logo_path))
        if pixmap.isNull():
            self.header_logo_label.clear()
            return
        self.header_logo_label.setPixmap(
            pixmap.scaled(
                self.header_logo_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def _toggle_theme(self, *_args) -> None:
        self.theme_mode = ThemeMode.DARK if self.theme_toggle.isChecked() else ThemeMode.LIGHT
        self._apply_theme()
        QTimer.singleShot(0, lambda: self.toast.show("Tema actualizado", "info"))

    def _load_initial_data(self) -> None:
        self._apply_data(self._blank_params(), [])
        self.status_badge.setText("Listo")

    def _settle_layout(self) -> None:
        for delay in (0, 80, 220, 500):
            QTimer.singleShot(delay, self._refresh_visual_state)

    def _refresh_visual_state(self) -> None:
        self._scale_field_accessory_buttons()
        self._update_product_table_layout()
        if hasattr(self, "tabs"):
            self.tabs.updateGeometry()
            self.tabs.repaint()
        if self.centralWidget() is not None:
            self.centralWidget().updateGeometry()
            self.centralWidget().repaint()

    def _apply_data(self, params: OrderParams, products: Iterable[Product] | None = None) -> None:
        self.loading = True
        self.params = params
        for key, field in self.field_inputs.items():
            self._set_field_text(field, getattr(params, key, ""))
        comment = params.comentarios if self.comment_manual_mode else self.excel_service.build_comment(params)
        self.comment_text.setPlainText(comment or params.comentarios)
        if products is not None:
            self.product_model.set_products(list(products))
        self.loading = False
        self.dirty_client = False
        self.dirty_products = False
        self._validation_attempted = False
        self._update_all_state()

    def _handle_client_field_changed(self, key: str | None = None) -> None:
        if self.loading:
            return
        if key == "cliente":
            self._apply_client_link_from_client_field()
        if not self.comment_manual_mode:
            self.comment_update_timer.start()
        self._mark_client_dirty()

    def _apply_client_link_from_client_field(self) -> None:
        client_field = self.field_inputs.get("cliente")
        institution_field = self.field_inputs.get("cliente_institucional")
        if client_field is None or institution_field is None:
            return
        institution = self._institution_for_client(self._field_text(client_field))
        institution_field.blockSignals(True)
        self._set_field_text(institution_field, institution or "")
        institution_field.blockSignals(False)

    def _institution_for_client(self, client: str) -> str:
        if client in self.client_links:
            return self.client_links[client]
        client_key = " ".join(client.upper().split())
        for linked_client, institution in self.client_links.items():
            if " ".join(linked_client.upper().split()) == client_key:
                return institution
        return ""

    def _mark_client_dirty(self) -> None:
        if self.loading:
            return
        self.dirty_client = True
        self.status_badge.setText("Cambios sin guardar")
        self._schedule_state_update()

    def _mark_products_dirty(self) -> None:
        if self.loading:
            return
        self.dirty_products = True
        self.status_badge.setText("Cambios sin guardar")
        self._schedule_state_update()

    def _schedule_state_update(self) -> None:
        if hasattr(self, "state_update_timer"):
            self.state_update_timer.start()

    def _update_all_state(self) -> None:
        self._update_motivo_field()
        self.params = self.collect_params()
        self._update_product_count()
        self._update_pdf_state(self.params)
        self._update_validation_styles()
        profile_text = self.active_profile_name or os.path.basename(self.product_import_path) or "Sin Perfil Activo"
        self.path_label.setText(f"Perfil Activo: {profile_text}")

    def _update_product_count(self) -> None:
        count = len(self.product_model.products())
        self.product_count_label.setText(f"{count} {'Item' if count == 1 else 'Items'}")

    def _update_pdf_state(self, params: OrderParams | None = None) -> None:
        if not hasattr(self, "pdf_state_label"):
            return
        params = params or self.collect_params()
        state = self._pdf_status_text(params)
        color = palette(self.theme_mode)["muted"]
        if state == "Archivo OC Cargado":
            color = palette(self.theme_mode)["success"]
        elif state == "Archivo OC No Encontrado":
            color = palette(self.theme_mode)["warning"]
        self.pdf_state_label.setText(state)
        self.pdf_state_label.setStyleSheet(f"color: {color}; font-weight: 800; background: transparent;")

    def _pdf_status_text(self, params: OrderParams) -> str:
        pdf = params.adjuntar_pdf.strip()
        if not pdf:
            return "SIN OC"
        resolved = self.excel_service.resolve_file(pdf)
        return "Archivo OC Cargado" if os.path.isfile(resolved) else "Archivo OC No Encontrado"

    def _pdf_card_text(self, params: OrderParams) -> str:
        pdf = params.adjuntar_pdf.strip()
        if not pdf:
            return "SIN OC"
        resolved = self.excel_service.resolve_file(pdf)
        return os.path.basename(resolved) if os.path.isfile(resolved) else "SIN OC"

    def _motivo_desde_pdf(self, *, default_when_empty: bool = True) -> str:
        field = self.field_inputs.get("adjuntar_pdf")
        pdf = self._field_text(field) if field is not None else ""
        if not pdf:
            return "SIN OC" if default_when_empty else ""
        return "CON OC" if os.path.isfile(self.excel_service.resolve_file(pdf)) else "SIN OC"

    def _update_motivo_field(self) -> None:
        field = self.field_inputs.get("motivo")
        if field is None:
            return
        motivo = self._motivo_desde_pdf(default_when_empty=True)
        field.blockSignals(True)
        self._set_field_text(field, motivo)
        field.blockSignals(False)

    def collect_params(self) -> OrderParams:
        values = {key: self._field_text(field) for key, field in self.field_inputs.items()}
        values["motivo"] = self._motivo_desde_pdf(default_when_empty=True)
        values["comentarios"] = self.comment_text.toPlainText().strip() if hasattr(self, "comment_text") else ""
        return OrderParams.from_dict(values)

    def collect_products(self) -> List[Product]:
        return self.product_model.products()

    def _update_validation_styles(self) -> None:
        errors = self._field_validation_errors(include_missing=self._validation_attempted)
        self._validation_messages = errors
        for key, field in self.field_inputs.items():
            message = errors.get(key, "")
            self._set_invalid_property(field, bool(message), message)

    def _field_validation_errors(self, include_missing: bool = False) -> Dict[str, str]:
        return self.validation_service.validate_order(
            self.collect_params(),
            catalog_options=self.catalog_options,
            client_links=self.client_links,
            resolve_file=self.excel_service.resolve_file,
            include_missing=include_missing,
        ).field_errors

    @staticmethod
    def _set_invalid_property(field: QLineEdit | QComboBox, invalid: bool, message: str = "") -> None:
        field.setProperty("invalid", invalid)
        field.setToolTip(message if invalid else "")
        field.style().unpolish(field)
        field.style().polish(field)
        if isinstance(field, QComboBox) and field.lineEdit():
            field.lineEdit().setProperty("invalid", invalid)
            field.lineEdit().setToolTip(message if invalid else "")
            field.lineEdit().style().unpolish(field.lineEdit())
            field.lineEdit().style().polish(field.lineEdit())

    def _set_comment_manual_mode(self, enabled: bool) -> None:
        if self.loading:
            return
        self.comment_manual_mode = enabled
        self.comment_text.setReadOnly(not enabled)
        self.comment_text.setFocusPolicy(Qt.StrongFocus if enabled else Qt.NoFocus)
        if enabled:
            self.comment_update_timer.stop()
        else:
            self.regenerate_comment(show_toast=False, force=True)
        self._mark_client_dirty()

    def create_profile(self) -> None:
        if not self._confirm_if_dirty("Esto limpiará los datos actuales para crear un perfil nuevo."):
            return
        self.active_profile_path = ""
        self.active_profile_name = ""
        self.product_import_path = ""
        self.client_filter = []
        self.line_filter = []
        self.product_filter_by_line = {}
        self.client_links = {}
        self._refresh_filters_in_ui()
        self._apply_data(
            self._blank_params(),
            [],
        )
        self.status_badge.setText("Perfil Nuevo")
        self.toast.show("Perfil nuevo listo", "success")

    def load_profile(self) -> None:
        if not self._confirm_if_dirty("Esto reemplazará el perfil actual."):
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Cargar Perfil",
            str(self.paths.profiles_dir),
            "Perfil InterAutomy (*.json)",
        )
        if not path:
            return
        self._run_excel_action(
            lambda: self.profile_service.load_profile_file(path),
            lambda result: self._finish_load_profile(*result),
            "Perfil Cargado",
        )

    def _finish_load_profile(self, params: OrderParams, products: List[Product], profile) -> None:
        self.active_profile_path = profile.path
        self.active_profile_name = profile.name
        self.product_import_path = ""
        credentials, warning = self.credential_service.credentials_from_profile(profile.credentials)
        if credentials.username:
            self.automy_credentials = credentials
            if credentials.password:
                self.append_log("Credenciales Automy asociadas al perfil cargadas desde keyring.\n")
            else:
                self.append_log("Usuario Automy asociado al perfil cargado; ingresa la contraseña para ejecutar.\n")
        if warning:
            self.append_log(f"Credenciales Automy: {warning}\n")
        self._apply_profile_filters(profile.filters)
        self._refresh_filters_in_ui()
        self._apply_data(params, products)
        self.status_badge.setText("Perfil Cargado")
        self.toast.show("Perfil cargado", "success")

    def save_profile(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar Perfil",
            str(self.paths.profiles_dir / "Perfil_InterAutomy.json"),
            "Perfil InterAutomy (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path = f"{path}.json"
        params = self.collect_params()
        products = self.collect_products()
        credential_result = self.credential_service.metadata_for_profile(self.automy_credentials)
        credential_key = str(credential_result.metadata.get("credential_key") or self.automy_credentials.credential_key)
        if credential_key != self.automy_credentials.credential_key:
            self.automy_credentials = AutomyCredentials(
                username=self.automy_credentials.username,
                password=self.automy_credentials.password,
                remember_with_profile=self.automy_credentials.remember_with_profile,
                credential_key=credential_key,
            )
        if credential_result.warning:
            self.append_log(f"Credenciales Automy: {credential_result.warning}\n")
        self._run_excel_action(
            lambda: self.profile_service.save_profile_file(
                path,
                params,
                products,
                self._profile_filters(),
                credential_result.metadata,
            ),
            self._finish_save_profile,
            "Perfil Guardado",
        )

    def _finish_save_profile(self, profile) -> None:
        self.active_profile_path = profile.path
        self.active_profile_name = profile.name
        self.dirty_client = False
        self.dirty_products = False
        self._update_all_state()
        self.status_badge.setText("Perfil Guardado")
        self.toast.show("Perfil guardado", "success")

    def export_advisor_excel(self) -> None:
        products = self.collect_products()
        if not products:
            self.toast.show("Agrega al menos un producto para exportar", "warning")
            return
        path = self._ask_save_path("Exportar Pedido Asesor", "Pedido_Asesor.xlsx")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path = f"{path}.xlsx"
        self._run_excel_action(
            lambda: self.excel_service.export_advisor_request(path, products),
            lambda _result: self._finish_export_advisor_excel(path),
            "Excel Exportado",
        )

    def _finish_export_advisor_excel(self, path: str) -> None:
        self.status_badge.setText("Excel Exportado")
        self.toast.show("Excel exportado", "success")
        self.append_log(f"Excel Pedido Asesor exportado:\n{path}\n")

    def refresh_catalogs(self, show_toast: bool = True) -> None:
        previous_loading = self.loading
        try:
            self.loading = True
            self.catalogos = self._load_catalogs()
            self._clean_filters()
            self.catalog_options = self._catalog_options_from_catalogs()
            self.catalog_option_sets = self._catalog_option_sets()
            self._apply_product_catalogs()
            self._refresh_combo_options()
            if hasattr(self, "product_table"):
                self._install_product_delegate()
                self._refresh_add_line_combo()
                self._update_product_table_layout()
        finally:
            self.loading = previous_loading
        self._update_all_state()
        if show_toast:
            self.toast.show("Listas actualizadas", "success")

    def configure_client_filter(self) -> None:
        available_clients = self.catalogos.clientes if self.catalogos is not None else []
        dialog = DualListFilterDialog(
            "Filtrar Instituciones",
            available_clients,
            self.client_filter,
            "Instituciones a trabajar",
            "Todas las instituciones",
            "Crear institución",
            self,
            scale=self.ui_scale,
        )
        if not dialog.exec():
            return
        self.client_filter = dialog.selected_values()
        self._refresh_filters_in_ui()
        self._mark_client_dirty()
        self.toast.show("Filtro de instituciones actualizado", "success")

    def configure_client_links(self) -> None:
        institutions = self._filtered_clients()
        dialog = ClientLinkDialog(
            institutions, self.client_links, self, scale=self.ui_scale
        )
        if not dialog.exec():
            return
        self.client_links = dialog.links()
        self._refresh_filters_in_ui()
        self._apply_client_link_from_client_field()
        self._mark_client_dirty()
        self.toast.show("Cliente actualizado", "success")

    def configure_line_filter(self) -> None:
        available_lines = self.catalogos.lineas if self.catalogos is not None else []
        dialog = DualListFilterDialog(
            "Filtrar Líneas",
            available_lines,
            self.line_filter,
            "Líneas a trabajar",
            "Todas las líneas",
            "Crear línea",
            self,
            scale=self.ui_scale,
        )
        if not dialog.exec():
            return
        self.line_filter = dialog.selected_values()
        valid_lineas = set(self._filtered_lineas())
        self.product_filter_by_line = {
            line: products
            for line, products in self.product_filter_by_line.items()
            if line in valid_lineas
        }
        self._refresh_filters_in_ui()
        self._mark_products_dirty()
        self.toast.show("Filtro de líneas actualizado", "success")

    def configure_product_filter(self) -> None:
        lineas = self._filtered_lineas()
        if not lineas:
            QMessageBox.information(self, "Productos", "Primero selecciona o crea una línea.")
            return
        productos_base = self.catalogos.productos_por_linea if self.catalogos is not None else {}
        dialog = ProductFilterDialog(
            lineas,
            {
                line: productos_base.get(line, [])
                for line in lineas
            },
            self.product_filter_by_line,
            self,
            scale=self.ui_scale,
        )
        if not dialog.exec():
            return
        self.product_filter_by_line = dialog.selected_products_by_line()
        self._refresh_filters_in_ui()
        self._mark_products_dirty()
        self.toast.show("Filtro de productos actualizado", "success")

    def _refresh_filters_in_ui(self) -> None:
        self._clean_filters()
        self.catalog_options = self._catalog_options_from_catalogs()
        self.catalog_option_sets = self._catalog_option_sets()
        self._apply_product_catalogs()
        self._refresh_combo_options()
        if hasattr(self, "product_table"):
            self._install_product_delegate()
            self._refresh_add_line_combo()
            self._update_product_table_layout()
            self._settle_layout()
        self._update_all_state()

    def select_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar OC", "", "Archivos PDF (*.pdf)")
        if not path:
            return
        self._set_field_text(self.field_inputs["adjuntar_pdf"], path)
        self._mark_client_dirty()
        self.toast.show("Archivo OC seleccionado", "success")

    def open_credentials_dialog(self) -> None:
        dialog = CredentialsDialog(self.automy_credentials, self, scale=self.ui_scale)
        if not dialog.exec():
            return
        self.automy_credentials = dialog.credentials()
        if self.automy_credentials.available:
            if self.automy_credentials.remember_with_profile and not self.credential_service.available:
                self.append_log("Credenciales Automy configuradas en memoria. keyring no esta disponible para recordarlas con el perfil.\n")
            else:
                self.append_log("Credenciales Automy configuradas en memoria para esta sesión.\n")
            self.toast.show("Credenciales configuradas", "success")
        else:
            self.append_log("Credenciales Automy limpiadas.\n")
            self.toast.show("Credenciales limpiadas", "info")

    def _toggle_autovalidation(self, enabled: bool) -> None:
        self.append_log(
            "AutoValidación activada.\n" if enabled else "AutoValidación desactivada.\n"
        )

    def _runtime_config(self) -> AutomationRuntimeConfig:
        autovalidation = self.autovalidation_check.isChecked()
        return AutomationRuntimeConfig(
            autovalidation=autovalidation,
            headless=autovalidation,
            credentials=self.automy_credentials,
        )

    @Slot(int)
    def _on_manual_validation_requested(self, timeout_seconds: int) -> None:
        dialog = ManualValidationDialog(timeout_seconds, self, scale=self.ui_scale)
        dialog.exec()
        self.runner.resolve_manual_validation(dialog.decision)

    def _show_soft_message(self, title: str, message: str) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        s = self.ui_scale.px
        dialog.setMinimumWidth(s(420))
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(s(20), s(18), s(20), s(18))
        layout.setSpacing(s(12))
        label = QLabel(message)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(label)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.button(QDialogButtonBox.Ok).setText("OK")
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    def _ensure_automy_credentials_for_run(self) -> bool:
        if self.automy_credentials.available:
            return True

        self.status_badge.setText("Credenciales requeridas")
        self.append_log("Ejecución detenida: faltan credenciales Automy.\n")
        self.toast.show("Ingresa usuario y contraseña de Automy", "warning")
        dialog = CredentialsDialog(
            self.automy_credentials,
            self,
            scale=self.ui_scale,
            require_complete=True,
        )
        if not dialog.exec():
            self.append_log("Ejecución cancelada: no se ingresaron credenciales.\n")
            return False

        self.automy_credentials = dialog.credentials()
        self.append_log("Credenciales Automy configuradas para esta ejecución.\n")
        self.toast.show("Credenciales configuradas", "success")
        return self.automy_credentials.available

    @staticmethod
    def _friendly_automation_error(error: str) -> str:
        text = str(error or "").strip()
        lowered = text.lower()
        login_error = "paso login" in lowered or "durante login" in lowered
        credential_error = (
            "credenciales" in lowered
            or "login autom" in lowered
            or "iniciar sesión" in lowered
            or "iniciar sesion" in lowered
        )
        browser_disconnected = (
            "invalid session" in lowered
            or "not connected to devtools" in lowered
            or "stacktrace" in lowered
            or "webdriver" in lowered
            or "selenium" in lowered
        )
        if login_error and (credential_error or browser_disconnected):
            return (
                "No se pudo iniciar sesión en Automy.\n\n"
                "Verifica que el usuario y la contraseña sean correctos. "
                "Si el navegador se cerró durante el login, vuelve a ejecutar después de actualizar las credenciales."
            )
        if browser_disconnected:
            return (
                "El navegador de Automy se cerró o perdió conexión durante la ejecución.\n\n"
                "Vuelve a intentar. Si ocurre al iniciar sesión, revisa usuario y contraseña en Credenciales."
            )
        return text or "Automy no pudo completar la ejecución."

    def regenerate_comment(self, show_toast: bool = True, *, force: bool = False) -> None:
        if self.loading or not hasattr(self, "comment_text"):
            return
        if self.comment_manual_mode and not force:
            return
        params = self.collect_params()
        comment = self.excel_service.build_comment(params)
        self.loading = True
        self.comment_text.blockSignals(True)
        self.comment_text.setPlainText(comment)
        self.comment_text.blockSignals(False)
        self.loading = False
        if show_toast:
            self._mark_client_dirty()
        if show_toast:
            self.toast.show("Comentario regenerado", "info")

    def _regenerate_comment_silently(self) -> None:
        self.regenerate_comment(show_toast=False)
        self._schedule_state_update()

    def add_product(self) -> None:
        if hasattr(self, "search_input") and self.search_input.text():
            self.search_input.clear()
        product = self._blank_product_for_selected_line()
        if not product.linea_pedido:
            self.toast.show("Selecciona una línea para agregar el producto", "warning")
            return
        inserted_index = self.product_model.insert_product_after_line(product)
        display_row = self.product_model.display_row_for_product_index(inserted_index)
        if display_row is not None:
            proxy_index = self.product_proxy.mapFromSource(self.product_model.index(display_row, 0))
            if proxy_index.isValid():
                self.product_table.setCurrentIndex(proxy_index)
                self.product_table.edit(proxy_index)
        self._mark_products_dirty()
        self._update_product_table_layout()
        self.toast.show("Producto agregado", "success")

    def duplicate_product(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            self.toast.show("Selecciona un producto", "warning")
            return
        for row in rows:
            product = self.product_model.product_by_index(row)
            if product:
                self.product_model.insert_product_after_line(Product.from_dict(product.to_dict()))
        self._mark_products_dirty()
        self._update_product_table_layout()
        self.toast.show("Producto duplicado", "success")

    def delete_product(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            self.toast.show("Selecciona un producto", "warning")
            return
        target_product_index = min(rows)
        self.product_model.remove_rows(rows)
        self._mark_products_dirty()
        self._update_product_table_layout()
        self._select_product_after_delete(target_product_index)
        self.toast.show("Producto eliminado", "success")

    def _select_product_after_delete(self, target_product_index: int) -> None:
        remaining = len(self.product_model.products())
        if not remaining:
            self.product_table.clearSelection()
            self.product_table.setCurrentIndex(QModelIndex())
            return
        target_product_index = min(max(0, target_product_index), remaining - 1)
        display_row = self.product_model.display_row_for_product_index(target_product_index)
        if display_row is None:
            return
        proxy_index = self.product_proxy.mapFromSource(self.product_model.index(display_row, 0))
        if proxy_index.isValid():
            self.product_table.setCurrentIndex(proxy_index)
            self.product_table.selectRow(proxy_index.row())

    def _selected_source_rows(self) -> List[int]:
        selection = self.product_table.selectionModel().selectedIndexes()
        rows = []
        for proxy_index in selection:
            source_index = self.product_proxy.mapToSource(proxy_index)
            product_index = self.product_model.product_index_at_row(source_index.row())
            if product_index is not None:
                rows.append(product_index)
        return sorted(set(rows))

    def _blank_product_for_selected_line(self) -> Product:
        line = self.add_line_combo.currentText().strip() if hasattr(self, "add_line_combo") else ""
        return Product(linea_pedido=line)

    def validate_information(self) -> bool:
        self._validation_attempted = True
        otros = self.catalogos.otros if self.catalogos is not None else {}
        validation = self.validation_service.validate_run(
            self.collect_params(),
            self.collect_products(),
            catalog_options=self.catalog_options,
            client_links=self.client_links,
            resolve_file=self.excel_service.resolve_file,
            lineas=self._filtered_lineas(),
            productos_por_linea=self._filtered_productos_por_linea(),
            unidades=otros.get("unidad_producto", []),
            categorias=otros.get("categoria_producto", []),
        )
        self._validation_messages = validation.field_errors
        for key, field in self.field_inputs.items():
            message = validation.field_errors.get(key, "")
            self._set_invalid_property(field, bool(message), message)
        if not validation.is_valid:
            ValidationDialog(
                validation.messages, self, scale=self.ui_scale
            ).exec()
            self.toast.show("Hay datos pendientes por completar", "error")
            return False
        self.toast.show("Información validada", "success")
        return True

    def run_automy(self) -> None:
        if self.runner.running:
            return
        self.append_log("Iniciando ejecución.\nVerificando datos del pedido.\n")
        if not self._ensure_automy_credentials_for_run():
            return
        if not self.validate_information():
            self.append_log("Error detectado: hay datos pendientes por completar.\n")
            return
        import_path = str(self.paths.product_import_file)
        try:
            params = self.collect_params()
            products = self.collect_products()
            self.append_log("Generando Excel de productos para Automy.\n")
            self.excel_service.export_advisor_request(import_path, products)
            self.append_log(f"Excel de productos preparado:\n{import_path}\nProductos: {len(products)}\n\n")
            self.product_import_path = import_path
            self._update_all_state()
        except PermissionError:
            self.toast.show("Cierra Pedido_Asesor_Importar.xlsx y vuelve a intentar", "error")
            QMessageBox.critical(self, "Excel abierto", "Cierra Pedido_Asesor_Importar.xlsx y vuelve a intentar.")
            return
        except Exception as exc:
            logger.exception("No se pudo preparar el Excel de productos")
            self.toast.show("No se pudo preparar el Excel de productos", "error")
            QMessageBox.critical(self, "Error", str(exc))
            return
        runtime_config = self._runtime_config()
        self.runner.start(params.to_dict(), import_path, runtime_config)

    @Slot()
    def _on_runner_started(self) -> None:
        self.status_badge.setText("Ejecutando InterAutomy")
        self.progress.setRange(0, 0)
        self._set_busy(True)
        self.append_log(f"Iniciando InterAutomy con productos importados desde:\n{self.product_import_path}\n\n")
        self.toast.show("InterAutomy en ejecución", "info")

    @Slot(bool, str, str)
    def _on_runner_finished(self, ok: bool, error: str, status: str) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if ok else 0)
        self._set_busy(False)
        self._last_run_status = status
        if ok:
            self.status_badge.setText("Proceso completado")
            self.append_log("\nProceso completado.\n")
            self.toast.show("Proceso completado", "success")
            QMessageBox.information(self, "Automy", "Proceso completado.")
        elif status == "canceled":
            self.status_badge.setText("Cancelado")
            self.append_log(f"\nEjecución cancelada:\n{error}\n")
            self.toast.show("Ejecución cancelada", "warning")
            QMessageBox.warning(self, "Automy", error)
        elif status == "expired":
            friendly_error = self._friendly_automation_error(error)
            self.status_badge.setText("Validación expirada")
            self.append_log(f"\nValidación expirada:\n{friendly_error}\n")
            self.toast.show("Validación expirada", "warning")
            self._show_soft_message("Automy", friendly_error)
        else:
            friendly_error = self._friendly_automation_error(error)
            self.status_badge.setText("Error")
            self.append_log(f"\nNo se pudo completar la ejecución:\n{friendly_error}\n")
            self.toast.show("Revisa credenciales o conexión de Automy", "warning")
            self._show_soft_message("Automy", friendly_error)

    def _set_busy(self, busy: bool) -> None:
        for button in self.critical_buttons:
            button.setEnabled(not busy)
        self.run_button.setEnabled(not busy)
        self.autovalidation_check.setEnabled(not busy)

    def append_log(self, text: str) -> None:
        cursor = self.log_console.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.log_console.setTextCursor(cursor)
        self.log_console.ensureCursorVisible()

    def clear_logs(self) -> None:
        self.log_console.clear()
        self.toast.show("Bitacora limpiada", "info")

    def _run_excel_action(self, action, on_success, success_status: str) -> None:
        self.status_badge.setText("Procesando...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        succeeded = False
        try:
            result = action()
            on_success(result)
            succeeded = True
        except PermissionError:
            self.status_badge.setText("Error")
            QMessageBox.critical(self, "Excel abierto", "Cierra el archivo Excel y vuelve a intentar.")
            self.toast.show("Excel abierto o bloqueado", "error")
        except Exception as exc:
            logger.exception("Falló una operación de archivo iniciada desde la interfaz")
            self.status_badge.setText("Error")
            QMessageBox.critical(self, "Error", str(exc))
            self.toast.show("Ocurrio un error", "error")
            self.append_log(f"Error:\n{exc}\n")
        finally:
            QApplication.restoreOverrideCursor()
            if succeeded and self.status_badge.text() == "Procesando...":
                self.status_badge.setText(success_status)

    def _ask_save_path(self, title: str, initial: str) -> str:
        path, _ = QFileDialog.getSaveFileName(
            self,
            title,
            str(self.paths.data_root / initial),
            "Archivos Excel (*.xlsx)",
        )
        return path

    def _confirm_if_dirty(self, message: str) -> bool:
        if not (self.dirty_client or self.dirty_products):
            return True
        return self._confirm("Cambios sin guardar", message)

    def _confirm(self, title: str, message: str) -> bool:
        reply = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _animate_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is None:
            return
        if index == 1:
            QTimer.singleShot(0, self._update_product_table_layout)
            QTimer.singleShot(120, self._update_product_table_layout)
        animation = QPropertyAnimation(widget, b"windowOpacity", self)
        animation.setDuration(120)
        animation.setStartValue(0.94)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start(QPropertyAnimation.DeleteWhenStopped)

    def eventFilter(self, watched, event) -> bool:
        if (
            hasattr(self, "product_table")
            and watched is self.product_table.viewport()
            and event.type() == QEvent.Resize
        ):
            QTimer.singleShot(0, self._update_product_table_layout)
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._scale_field_accessory_buttons)
        if hasattr(self, "product_table"):
            QTimer.singleShot(0, self._update_product_table_layout)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._center_window)
        QTimer.singleShot(0, self._scale_field_accessory_buttons)
        QTimer.singleShot(120, self._scale_field_accessory_buttons)
        if hasattr(self, "product_table"):
            QTimer.singleShot(0, self._update_product_table_layout)
            QTimer.singleShot(180, self._update_product_table_layout)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.runner.running:
            QMessageBox.warning(self, "Automy En Ejecución", "Espera a que InterAutomy termine antes de cerrar.")
            event.ignore()
            return
        if self.dirty_client or self.dirty_products:
            reply = QMessageBox.question(
                self,
                "Cambios sin guardar",
                "Hay cambios sin guardar. Deseas cerrar de todas formas?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()


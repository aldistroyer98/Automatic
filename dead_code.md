# Auditoría de código residual

Fecha: 2026-06-24

## Código eliminado

- Botones ocultos de pegado/OCR en `EquivalenceTab`.
- Botones ocultos Arriba/Abajo duplicados en `ProductOrderDialog`.
- Métodos de diálogo sin conexión a señales: `reprocess()` y `export_review()`.
- Métodos internos sin referencias: `move_product()`, `_sorted_products()`,
  `assign_product_category()`, `_extend_date_period()`, `_block_period()`,
  `_block_months_formula()`, `extract_tender_tests_from_image()` y
  `_style_section()`.
- Constante `SECTION_FILL`, utilizada únicamente por código eliminado.
- Reexportación rota del paquete raíz hacia un módulo inexistente
  (`.shipment_tab`).

## Duplicación corregida

- Redimensionamiento proporcional de columnas centralizado en
  `ui/common/table_helpers.py`.
- Creación/alineación de celdas de solo lectura centralizada.
- Movimiento y normalización de orden de categorías centralizados en
  `services/category_manager.py`.
- Las clases `ImportPreviewDialog`, `ProductOrderDialog` y
  `HomologationDialog` se extrajeron del tab coordinador.

## Código oculto conservado

- Los layouts ocultos de `EquivalenceTab` contienen tablas que todavía actúan
  como estado de trabajo para cálculo, homologación y exportación. Eliminarlos
  exigiría cambiar la lógica de negocio.
- El log de `ShipmentTab` inicia oculto, pero el botón “Ver detalle” lo muestra.

## APIs públicas sin llamadas internas

Se conservaron por compatibilidad: propiedades auxiliares de `AppPaths`,
`parse_clipboard_text()`, `export_import_review()`, `scale_for()` y
`CheckableComboBox.set_selected_data()`. La ausencia de llamadas dentro del
repositorio no demuestra que no sean usadas por integraciones externas.

## Clases, constantes y archivos

- Todas las clases de UI tienen una ruta de instanciación.
- No quedan constantes privadas inequívocamente muertas.
- Los recursos de iconos y logos están referenciados.
- Los únicos archivos huérfanos detectados fueron residuos no versionados
  indicados en la solicitud; se eliminaron durante la limpieza.

## Duplicación no fusionada

`normalize_text()` y `normalize_description()` son estructuralmente similares,
pero permanecen separadas para no acoplar modelos de envío y equivalencia ni
alterar sus contratos públicos.

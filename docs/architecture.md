# Arquitectura técnica

## Visión general

`main.py` configura logging, rutas de ejecución y la aplicación Qt.
`MainWindow` crea dos flujos independientes: Envío y Equivalencia. Los widgets
coordinan interacción; los servicios contienen lectura, validación, cálculo y
escritura; los modelos son dataclasses sin dependencias de Qt.

Los datos mutables se guardan bajo `%LOCALAPPDATA%/Automatic`. En el primer
inicio, una instalación que solo tenga la carpeta de datos anterior se copia de
forma no destructiva; la carpeta de origen permanece como respaldo.

## Flujo de envío

1. `ShipmentTab` solicita un `.xlsx` o `.xlsm`.
2. `ShipmentService.analyze()` valida encabezados, ignora filas vacías,
   normaliza fechas/cantidades y produce `ShipmentAnalysis`.
3. `ShipmentConfigService` carga categorías persistidas y combina productos
   nuevos sin cambiar claves ni formato JSON.
4. Los filtros generan `ShipmentOptions`; `preview()` agrega cantidades por
   cliente, periodo, línea y producto.
5. `generate_report()` crea Resumen, Total General, hojas por cliente y
   `Data_Normalizada`, y luego valida el libro generado.

## Flujo de homologación

1. `EquivalenceTab` carga la configuración desde
   `equivalence_config.json` y coordina estado, cálculo y exportación.
2. `ImportPreviewDialog` valida y confirma pruebas importadas.
3. `HomologationDialog` relaciona pruebas con productos y valida `DET RVO`.
4. `ProductOrderDialog` administra categorías y orden mediante
   `CategoryManager`, conservando los nombres internos persistidos.
5. `EquivalenceService.calculate()` calcula DET OC, DET ENV y cantidades,
   generando alertas sin modificar la lógica de cálculo.

La entrada activa de licitaciones usa CSV. El proyecto no incluye OCR ni
procesamiento de imágenes/PDF.

## Flujo Excel

- Entrada: `services/excel_reader.py` elimina filas vacías, columnas finales
  vacías y columnas de índice `Unnamed: n`.
- Envío: se exigen Cliente, CodProd, Producto, CodEqv, Cantidad y Línea, además
  de Fecha o Año + Mes.
- Equivalencia: se validan encabezados de productos y `DET RVO` numérico no
  negativo; se mantiene soporte para archivos heredados sin encabezado.
- Salida: se usa `openpyxl` con encabezados explícitos. No se exportan índices
  ni se crean columnas `Unnamed`.
- Los nombres de hojas, orden de columnas y formatos existentes se conservan.

## Flujo Power BI

1. `ShipmentTab.export_powerbi()` reutiliza los filtros activos.
2. `ShipmentPowerBIService` valida registros y construye `FactEnvios`,
   `DimCliente`, `DimProducto`, `DimFecha`, `DimLinea` y `DimTipoProducto`.
3. Cada tabla se escribe como CSV UTF-8 con BOM y encabezado explícito.
4. Se generan medidas DAX, Power Query M, README, registro de filas ignoradas
   y tema JSON.
5. Si existe una plantilla `.pbit` o `.pbix`, se copia sin modificarla.

Los nombres internos heredados de Power BI se mantienen para no romper medidas,
relaciones ni plantillas existentes.

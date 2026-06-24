# Auditoría de limpieza y marca

Fecha: 2026-06-24

## Inventario

Árbol funcional, excluyendo `.git`, entornos virtuales, cachés y salidas de
compilación:

```text
app/
docs/
models/
resources/
  icons/
  logos/
services/
tests/
ui/
  common/
  dialogs/
  tabs/
main.py
requirements.txt
```

Tamaños medidos antes de la limpieza:

| Elemento | Tamaño |
|---|---:|
| `.venv` local, no trackeado | 901.72 MB |
| `.git` | 353.14 MB |
| Recursos | 2.31 MB |
| Código, pruebas y documentación | < 1 MB |
| Total local | 1,257.44 MB |

No hay archivos funcionales mayores de 5 MB fuera de `.git` y `.venv`.
Los assets trackeados más grandes son `SISA1.png` (1.32 MB),
`Automatic.png` (0.74 MB) y `Automatic.ico` (0.25 MB).

El objeto Git inalcanzable de 350.11 MB se eliminó con
`git gc --prune=now`. `.git` quedó en 2.64 MB sin reescribir commits.
El total local estimado quedó en 907.35 MB; 901.72 MB corresponden a `.venv`.
El checkout funcional, excluyendo `.git` y `.venv`, ocupa 2.99 MB.

## Hallazgos de marca y OCR

| Ubicación original | Estado | Decisión |
|---|---|---|
| `app/paths.py`: nombre y ruta de datos anteriores | ACTIVO | Reemplazado por `Automatic` y `AUTOMATIC_DATA_DIR` |
| `app/logging_config.py`: logger y archivo anteriores | ACTIVO | Renombrado a `automatic` y `automatic.log` |
| `services/shipment_powerbi_service.py`: nombre del tema | ACTIVO | Renombrado a `Automatic Envíos` |
| `resources/icons/Automy1.*` | ACTIVO / ASSET | Renombrado a `Automatic.*` y referencias actualizadas |
| Carpeta de datos anterior en `%LOCALAPPDATA%` | PROBABLEMENTE ACTIVO | Migración no destructiva a `%LOCALAPPDATA%/Automatic` |
| Variable de entorno anterior | DUDOSO / COMPATIBILIDAD | Fallback de migración; la variable nueva tiene prioridad |
| Botones de imagen/PDF | MUERTO | Ya no existían en la UI activa |
| Métodos OCR/PDF de `EquivalenceService` | MUERTO | Eliminados |
| Parser de portapapeles y exportación de revisión desconectados | MUERTO | Eliminados |
| `Pillow`, `pytesseract`, `PyMuPDF` | MUERTO | Eliminados de `requirements.txt` |
| `ui/theme.py`: `image: none` | ACTIVO | Conservado; es una propiedad CSS, no OCR |
| `SISA1.png` y `Automatic.png` | ACTIVO | Conservados; se cargan desde `MainWindow` y `main.py` |
| `Automatic.ico` | PROBABLEMENTE ACTIVO | Conservado para empaquetado Windows |

Las únicas cadenas de la marca anterior que permanecen están aisladas en
`app/paths.py` como identificadores de compatibilidad para localizar datos de
usuarios existentes. No se muestran en UI, logs, exports ni nombres nuevos.

## Grafo de uso

ACTIVO:

- `main.py`, `app.logging_config`, `app.paths`.
- Todos los modelos.
- Todos los servicios.
- `ui.main_window`, tabs, diálogos, helpers, iconos, escalado y tema.

PROBABLEMENTE ACTIVO:

- Archivos `__init__.py`, necesarios para paquetes y reexportaciones.
- `Automatic.ico`, usado normalmente por empaquetado aunque no haya `.spec`
  versionado.

DUDOSO, conservado:

- `UiScale.from_percent()`.
- `scale_for()`.
- `CheckableComboBox.set_selected_data()`.

Son APIs auxiliares pequeñas y seguras; eliminarlas no aporta una reducción
material y podría romper consumidores externos o futuros perfiles UI.

MUERTO y eliminado:

- Cadena OCR completa.
- Propiedades antiguas de rutas para Chrome, temporales e imports de producto.
- Resolución de rutas heredadas sin consumidores.
- Controles ocultos y métodos desconectados documentados en `dead_code.md`.

No se detectaron módulos funcionales huérfanos.

## Peso del entorno local

`.venv` no está trackeado y continúa intacto. Contiene paquetes que ya no son
requeridos:

| Paquete/carpeta | Tamaño aproximado |
|---|---:|
| OpenCV (`cv2`) | 108.59 MB |
| PyMuPDF | 46.05 MB |
| Selenium | 21.09 MB |
| Pillow | 13.91 MB |
| NumPy y librerías | 39.47 MB |

Para retirar esos paquetes y evitar dependencias transitivas obsoletas se
recomienda recrear `.venv` desde `requirements.txt`.

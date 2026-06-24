# Auditoría de imports

Fecha: 2026-06-24

## Método

- `ruff check` sobre todos los módulos Python, excluyendo `.venv`.
- Verificación AST de símbolos importados y referencias.
- Compilación completa con `python -m compileall`.

## Hallazgos

- La línea base no contenía imports funcionales sin uso.
- Los aparentes imports sin uso en `__init__.py` son reexportaciones públicas.
- La división de `equivalence_tab.py` dejó imports transitorios que fueron retirados:
  `QApplication`, `QFileDialog` y una importación circular de `ProductOrderDialog`.

## Estado final

`ruff check` no reporta imports sin uso. No se modificaron las reexportaciones públicas.

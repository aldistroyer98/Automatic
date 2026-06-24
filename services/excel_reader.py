from __future__ import annotations

from collections.abc import Iterable, Sequence


def is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def is_empty_row(row: Sequence[object]) -> bool:
    return not row or all(is_blank(value) for value in row)


def sanitize_tabular_rows(rows: Iterable[Sequence[object]]) -> list[tuple[object, ...]]:
    """Remove empty rows, trailing empty columns and exported index columns."""
    materialized = [tuple(row) for row in rows if not is_empty_row(row)]
    if not materialized:
        return []

    width = max(len(row) for row in materialized)
    padded = [row + (None,) * (width - len(row)) for row in materialized]
    headers = [str(value or "").strip().casefold() for value in padded[0]]
    keep = [
        index
        for index in range(width)
        if not headers[index].startswith("unnamed:")
        and any(not is_blank(row[index]) for row in padded)
    ]
    return [tuple(row[index] for index in keep) for row in padded]

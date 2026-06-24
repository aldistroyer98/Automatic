from __future__ import annotations

from collections.abc import Iterable

from models.shipment import ShipmentFilterState, ShipmentRecord


FILTER_FIELDS = {
    "clients": ("cliente", "selected_clients"),
    "years": ("anio", "selected_years"),
    "lines": ("linea", "selected_lines"),
    "comodatos": ("comodato", "selected_comodatos"),
}


def filter_records(
    records: Iterable[ShipmentRecord],
    state: ShipmentFilterState,
    *,
    ignore_field: str | None = None,
) -> list[ShipmentRecord]:
    selected_by_record_field = {
        record_field: getattr(state, state_field)
        for key, (record_field, state_field) in FILTER_FIELDS.items()
        if key != ignore_field
    }
    return [
        record
        for record in records
        if all(
            not selected or getattr(record, record_field) in selected
            for record_field, selected in selected_by_record_field.items()
        )
    ]


def compute_available_filter_options(
    records: Iterable[ShipmentRecord],
    state: ShipmentFilterState,
    ignore_field: str | None = None,
) -> dict[str, tuple[object, ...]] | tuple[object, ...]:
    materialized = tuple(records)

    def values_for(field: str) -> tuple[object, ...]:
        record_field, _state_field = FILTER_FIELDS[field]
        candidates = filter_records(materialized, state, ignore_field=field)
        values = {
            getattr(record, record_field)
            for record in candidates
            if getattr(record, record_field) not in (None, "")
        }
        return tuple(sorted(values, key=lambda value: str(value).casefold()))

    if ignore_field is not None:
        return values_for(ignore_field)
    return {field: values_for(field) for field in FILTER_FIELDS}

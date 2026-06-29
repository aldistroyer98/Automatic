from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

from openpyxl.utils.datetime import from_excel

from models.shipment import ShipmentRecord
from models.shipment_config import ShipmentForecastConfig, product_key


@dataclass(frozen=True)
class ShipmentForecastSegment:
    product_key: str
    delivery_date: date
    performance_start: date
    performance_end: date
    expiration_date: date | None
    quantity: float
    logistics_days: int
    performance_days: int

    def status_on(self, day: date) -> str | None:
        if day == self.delivery_date:
            return "actual_delivery"
        if self.delivery_date < day < self.performance_start:
            return "logistics"
        if self.performance_start <= day <= self.performance_end:
            if self.expiration_date is not None and day >= self.expiration_date:
                return "expired"
            return "performance"
        return None


def parse_forecast_date(value: object) -> date | None:
    """Return a date for supported Excel/date values; invalid or blank values are ignored."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            converted = from_excel(value)
            return converted.date() if isinstance(converted, datetime) else converted
        except (TypeError, ValueError, OverflowError):
            return None
    text = " ".join(str(value).replace("\xa0", " ").split())
    for fmt in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def build_forecast_segments(
    records: Iterable[ShipmentRecord],
    config: ShipmentForecastConfig,
) -> dict[str, ShipmentForecastSegment]:
    """Build one projection per selected product from its latest real delivery."""
    dated: dict[str, list[tuple[date, ShipmentRecord]]] = {}
    for record in records:
        key = product_key(record.cod_prod, record.cod_eqv, record.producto)
        product_config = config.product(key)
        if not product_config.enabled or product_config.performance_days <= 0:
            continue
        delivery = parse_forecast_date(record.fecha)
        if delivery is None:
            continue
        dated.setdefault(key, []).append((delivery, record))

    result: dict[str, ShipmentForecastSegment] = {}
    for key, rows in dated.items():
        latest = max(day for day, _record in rows)
        latest_rows = [record for day, record in rows if day == latest]
        quantity = sum(max(0.0, float(record.cantidad)) for record in latest_rows)
        product_config = config.product(key)
        performance_days = int(math.ceil(quantity * product_config.performance_days))
        if performance_days <= 0:
            continue
        logistics_days = (
            config.logistics_days
            if product_config.logistics_days is None
            else product_config.logistics_days
        )
        logistics_days = max(0, int(logistics_days))
        performance_start = latest + timedelta(days=logistics_days)
        performance_end = performance_start + timedelta(days=performance_days - 1)
        expirations = [
            parsed
            for record in latest_rows
            if (parsed := parse_forecast_date(record.expira)) is not None
        ]
        result[key] = ShipmentForecastSegment(
            product_key=key,
            delivery_date=latest,
            performance_start=performance_start,
            performance_end=performance_end,
            expiration_date=min(expirations) if expirations else None,
            quantity=quantity,
            logistics_days=logistics_days,
            performance_days=performance_days,
        )
    return result


def forecast_date_range(
    segments: Iterable[ShipmentForecastSegment],
) -> tuple[date, date] | None:
    items = tuple(segments)
    if not items:
        return None
    return min(item.delivery_date for item in items), max(item.performance_end for item in items)

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

from dateutil import parser
from rapidfuzz import fuzz
from sqlmodel import Session, select

from ..auth import record_activity
from ..models import ActivityEntityType, Order, OrderItem, Store, StoreStatus, User, UserRole

MANDATORY_COLUMNS = {
    "order_id",
    "order_date",
    "billing_company",
    "billing_email",
    "billing_address1",
    "billing_city",
    "billing_state/province",
    "billing_postcode",
    "subtotal",
    "total",
    "payment_method",
    "status",
}


class ImportSummary:
    def __init__(self) -> None:
        self.inserted = 0
        self.updated = 0
        self.skipped = 0
        self.unmatched = 0
        self.unmatched_rows: List[Dict[str, str]] = []

    def as_dict(self) -> Dict[str, int]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "unmatched": self.unmatched,
        }


def normalize_header(header: str) -> str:
    return header.strip().lower()


def _validate_headers(headers: Iterable[str]) -> None:
    missing = [column for column in MANDATORY_COLUMNS if column not in headers]
    if missing:
        raise ValueError(f"Missing mandatory columns: {', '.join(missing)}")


def _parse_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_date(value: str) -> datetime:
    return parser.parse(value)


def match_store(session: Session, row: Dict[str, str]) -> Optional[Store]:
    company = (row.get("billing_company") or "").strip()
    email = (row.get("billing_email") or "").strip().lower()
    phone = (row.get("billing_phone") or "").strip()

    if company:
        store = session.exec(select(Store).where(Store.display_name == company)).first()
        if store:
            return store
        stores = session.exec(select(Store)).all()
        for candidate in stores:
            score = fuzz.ratio(candidate.display_name.lower(), company.lower())
            if score > 90:
                return candidate

    if email:
        store = session.exec(select(Store).where(Store.email == email)).first()
        if store:
            return store

    if phone:
        store = session.exec(select(Store).where(Store.phone == phone)).first()
        if store:
            return store

    return None


def _infer_store_province(row: Dict[str, str]) -> str:
    province = (row.get("billing_state/province") or "").strip().upper()
    if len(province) == 2:
        return province
    mapping = {
        "ALBERTA": "AB",
        "BRITISH COLUMBIA": "BC",
        "ONTARIO": "ON",
        "QUEBEC": "QC",
    }
    return mapping.get(province, province[:2]) or "NA"


def infer_item_attributes(name: str) -> Tuple[Optional[float], Optional[int], Optional[str]]:
    nicotine = None
    puffs = None
    ice = None

    for token in name.split():
        if token.endswith("mg"):
            try:
                nicotine = float(token.replace("mg", ""))
            except ValueError:
                pass
        if token.lower().endswith("puff") or token.lower().endswith("puffs"):
            digits = "".join(filter(str.isdigit, token))
            if digits:
                puffs = int(digits)
        if token.lower() in {"ice", "iced"}:
            ice = "ICE"
    return nicotine, puffs, ice


def import_orders(session: Session, *, current_user: User, file_content: bytes) -> ImportSummary:
    summary = ImportSummary()
    decoded = file_content.decode("utf-8-sig")
    buffer = io.StringIO(decoded)
    reader = csv.DictReader(buffer)
    headers = [normalize_header(h) for h in reader.fieldnames or []]
    header_map = dict(zip(reader.fieldnames or [], headers))
    _validate_headers(headers)

    for raw_row in reader:
        row = {header_map[key]: value for key, value in raw_row.items()}
        if not row.get("order_id"):
            summary.skipped += 1
            continue
        try:
            order_date = _parse_date(row.get("order_date") or "")
        except (ValueError, TypeError):
            summary.skipped += 1
            continue

        store = match_store(session, row)
        if not store:
            store = Store(
                display_name=row.get("billing_company") or "Unknown Store",
                email=row.get("billing_email"),
                phone=row.get("billing_phone"),
                address1=row.get("billing_address1"),
                city=row.get("billing_city") or "",
                province=_infer_store_province(row),
                postal_code=row.get("billing_postcode"),
                status=StoreStatus.LEAD,
                notes="Created from WooCommerce import (needs review)",
            )
            if current_user.role in {UserRole.SALESMAN, UserRole.SUBSALESMAN}:
                store.owner_user_id = current_user.id
            session.add(store)
            session.commit()
            session.refresh(store)
            summary.unmatched += 1

        order = session.exec(select(Order).where(Order.external_id == row["order_id"])).first()
        is_new = order is None
        if not order:
            order = Order(external_id=row["order_id"], store_id=store.id)
        order.order_date = order_date
        order.subtotal = _parse_float(row.get("subtotal"))
        order.shipping = _parse_float(row.get("shipping_total"))
        order.discount = _parse_float(row.get("discount_total"))
        order.total = _parse_float(row.get("total"))
        order.payment_method = row.get("payment_method")
        order.status = row.get("status")
        order.excise_tax = _parse_float(row.get("excise_tax"))
        tax_total = _parse_float(row.get("tax_total"))
        order.gst_hst = tax_total * 0.7
        order.pst = tax_total * 0.3
        order.raw_import_payload = str(row)
        order.store_id = store.id
        session.add(order)
        session.commit()
        session.refresh(order)

        existing_items = list(session.exec(select(OrderItem).where(OrderItem.order_id == order.id)))
        for existing in existing_items:
            session.delete(existing)
        session.commit()

        line_items: List[Dict[str, str]] = []
        for index in range(1, 20):
            prefix = f"line_{index}_"
            if not any(key.startswith(prefix) for key in row.keys()):
                continue
            name = row.get(f"{prefix}name") or row.get(f"{prefix}product_name")
            if not name:
                continue
            qty = _parse_int(row.get(f"{prefix}quantity") or "1")
            unit_price = _parse_float(row.get(f"{prefix}subtotal")) / max(qty, 1)
            line_total = _parse_float(row.get(f"{prefix}total")) or (unit_price * qty)
            category = row.get(f"{prefix}category")
            nicotine, puffs, ice = infer_item_attributes(name)
            line_items.append(
                {
                    "sku": row.get(f"{prefix}sku"),
                    "product_name": name,
                    "category": category,
                    "nicotine_pct": nicotine,
                    "puff_count": puffs,
                    "ice_level": ice,
                    "qty": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                }
            )

        if not line_items and row.get("line_items"):
            try:
                import json

                parsed = json.loads(row["line_items"])
                for item in parsed:
                    nicotine, puffs, ice = infer_item_attributes(item.get("name", ""))
                    line_items.append(
                        {
                            "sku": item.get("sku"),
                            "product_name": item.get("name", "Unknown"),
                            "category": item.get("category"),
                            "nicotine_pct": nicotine,
                            "puff_count": puffs,
                            "ice_level": ice,
                            "qty": int(item.get("quantity", 1)),
                            "unit_price": float(item.get("price", 0.0)),
                            "line_total": float(item.get("subtotal", item.get("total", 0.0))),
                        }
                    )
            except Exception:  # noqa: BLE001
                summary.skipped += 1
                continue

        for item in line_items:
            order_item = OrderItem(order_id=order.id, **item)
            session.add(order_item)
        session.commit()

        dates = [value for value in [store.last_order_date, order.order_date.date()] if value]
        if dates:
            store.last_order_date = max(dates)
            session.add(store)
            session.commit()

        record_activity(
            session,
            actor=current_user,
            entity_type=ActivityEntityType.ORDER,
            entity_id=order.id,
            action="order_imported" if is_new else "order_updated",
            metadata=row.get("status"),
        )

        if is_new:
            summary.inserted += 1
        else:
            summary.updated += 1

    return summary

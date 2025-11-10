from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List

from sqlmodel import Session, func, select

from ..models import Order, OrderItem, Store, User, UserRole


def revenue_totals(session: Session, current_user: User, start: datetime | None = None, end: datetime | None = None) -> Dict[str, float]:
    query = select(func.sum(Order.total), func.sum(Order.subtotal), func.count(Order.id)).join(Store)
    if start:
        query = query.where(Order.order_date >= start)
    if end:
        query = query.where(Order.order_date <= end)
    if current_user.role == UserRole.SALESMAN:
        query = query.where(Store.owner_user_id == current_user.id)
    elif current_user.role == UserRole.SUBSALESMAN:
        query = query.where(Store.sub_owner_user_id == current_user.id)
    elif current_user.role == UserRole.CLIENT:
        query = query.where(Store.owner_user_id == current_user.id)
    total, subtotal, count = session.exec(query).first()
    return {
        "total": float(total or 0),
        "subtotal": float(subtotal or 0),
        "orders": int(count or 0),
    }


def monthly_spend(session: Session, current_user: User) -> List[Dict[str, object]]:
    query = select(
        Store.display_name,
        func.strftime("%Y-%m", Order.order_date).label("month"),
        func.sum(Order.total),
        func.sum(Order.excise_tax),
        func.sum(Order.gst_hst + Order.pst),
        func.sum(Order.subtotal),
        func.count(Order.id),
    ).join(Store)

    if current_user.role == UserRole.SALESMAN:
        query = query.where(Store.owner_user_id == current_user.id)
    elif current_user.role == UserRole.SUBSALESMAN:
        query = query.where(Store.sub_owner_user_id == current_user.id)
    elif current_user.role == UserRole.CLIENT:
        query = query.where(Store.owner_user_id == current_user.id)

    query = query.group_by(Store.display_name, "month").order_by("month")

    results = []
    for name, month, total, excise, taxes, subtotal, count in session.exec(query):
        results.append(
            {
                "store": name,
                "month": month,
                "orders": int(count or 0),
                "subtotal": float(subtotal or 0),
                "excise_tax": float(excise or 0),
                "taxes": float(taxes or 0),
                "total": float(total or 0),
            }
        )
    return results


def province_breakdown(session: Session, current_user: User) -> List[Dict[str, object]]:
    query = select(
        Store.province,
        func.count(Store.id),
        func.sum(Order.total),
    ).join(Store)

    if current_user.role == UserRole.SALESMAN:
        query = query.where(Store.owner_user_id == current_user.id)
    elif current_user.role == UserRole.SUBSALESMAN:
        query = query.where(Store.sub_owner_user_id == current_user.id)
    elif current_user.role == UserRole.CLIENT:
        query = query.where(Store.owner_user_id == current_user.id)

    query = query.group_by(Store.province).order_by(Store.province)
    results = []
    for province, store_count, total in session.exec(query):
        results.append({"province": province, "stores": int(store_count or 0), "total": float(total or 0)})
    return results


def inactive_stores(session: Session, current_user: User, days: int = 30) -> List[Store]:
    cutoff = datetime.utcnow().date() - timedelta(days=days)
    query = select(Store).where((Store.last_order_date == None) | (Store.last_order_date < cutoff))  # noqa: E711
    if current_user.role == UserRole.SALESMAN:
        query = query.where(Store.owner_user_id == current_user.id)
    elif current_user.role == UserRole.SUBSALESMAN:
        query = query.where(Store.sub_owner_user_id == current_user.id)
    elif current_user.role == UserRole.CLIENT:
        query = query.where(Store.owner_user_id == current_user.id)
    return list(session.exec(query))


def category_mix(session: Session, current_user: User) -> Dict[str, float]:
    query = select(OrderItem.category, func.sum(OrderItem.line_total)).join(Order).join(Store)
    if current_user.role == UserRole.SALESMAN:
        query = query.where(Store.owner_user_id == current_user.id)
    elif current_user.role == UserRole.SUBSALESMAN:
        query = query.where(Store.sub_owner_user_id == current_user.id)
    elif current_user.role == UserRole.CLIENT:
        query = query.where(Store.owner_user_id == current_user.id)
    query = query.group_by(OrderItem.category)

    totals: Dict[str, float] = {}
    overall = 0.0
    for category, total in session.exec(query):
        totals[category or "Uncategorized"] = float(total or 0)
        overall += float(total or 0)
    if overall == 0:
        return totals
    return {category: round(value / overall * 100, 2) for category, value in totals.items()}


def top_products(session: Session, current_user: User, limit: int = 20) -> List[Dict[str, object]]:
    query = (
        select(
            OrderItem.product_name,
            func.sum(OrderItem.line_total),
            func.sum(OrderItem.qty),
        )
        .join(Order)
        .join(Store)
    )

    if current_user.role == UserRole.SALESMAN:
        query = query.where(Store.owner_user_id == current_user.id)
    elif current_user.role == UserRole.SUBSALESMAN:
        query = query.where(Store.sub_owner_user_id == current_user.id)
    elif current_user.role == UserRole.CLIENT:
        query = query.where(Store.owner_user_id == current_user.id)

    query = query.group_by(OrderItem.product_name).order_by(func.sum(OrderItem.line_total).desc()).limit(limit)
    results = []
    for name, revenue, qty in session.exec(query):
        results.append({"product": name, "revenue": float(revenue or 0), "quantity": int(qty or 0)})
    return results

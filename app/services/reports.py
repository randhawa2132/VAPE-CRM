from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlmodel import Session, func, select

from ..models import Franchise, Order, OrderItem, Store, User, UserRole


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


def _store_access_filters(query, current_user: User):
    if current_user.role == UserRole.SALESMAN:
        query = query.where(Store.owner_user_id == current_user.id)
    elif current_user.role == UserRole.SUBSALESMAN:
        query = query.where(Store.sub_owner_user_id == current_user.id)
    elif current_user.role == UserRole.CLIENT:
        query = query.where(Store.owner_user_id == current_user.id)
    return query


def franchise_overview(session: Session, current_user: User) -> List[Dict[str, object]]:
    store_query = select(Store)
    store_query = _store_access_filters(store_query, current_user)
    stores = session.exec(store_query).all()

    franchise_ids = {store.franchise_id for store in stores if store.franchise_id}

    franchises_query = select(Franchise)
    if current_user.role != UserRole.ADMIN and franchise_ids:
        franchises_query = franchises_query.where(Franchise.id.in_(franchise_ids))
    franchises = session.exec(franchises_query.order_by(Franchise.name)).all()

    if not franchises:
        return []

    orders_query = (
        select(Store.franchise_id, func.sum(Order.total), func.count(Order.id))
        .select_from(Store)
        .join(Order, Order.store_id == Store.id, isouter=True)
    )
    orders_query = _store_access_filters(orders_query, current_user)
    orders_query = orders_query.group_by(Store.franchise_id)
    revenue_lookup: Dict[Optional[int], Dict[str, float]] = {}
    for franchise_id, revenue, order_count in session.exec(orders_query):
        revenue_lookup[franchise_id] = {
            "revenue": float(revenue or 0),
            "orders": int(order_count or 0),
        }

    store_revenue_query = (
        select(Store.id, Store.franchise_id, func.sum(Order.total))
        .select_from(Store)
        .join(Order, Order.store_id == Store.id, isouter=True)
    )
    store_revenue_query = _store_access_filters(store_revenue_query, current_user)
    store_revenue_query = store_revenue_query.group_by(Store.id)
    store_revenue: Dict[int, float] = {}
    for store_id, franchise_id, total in session.exec(store_revenue_query):
        store_revenue[store_id] = float(total or 0)

    thirty_day_cutoff = datetime.utcnow().date() - timedelta(days=30)
    results: List[Dict[str, object]] = []
    store_map: Dict[int, List[Store]] = {franchise.id: [] for franchise in franchises}
    for store in stores:
        if store.franchise_id in store_map:
            store_map[store.franchise_id].append(store)

    for franchise in franchises:
        franchise_stores = store_map.get(franchise.id, [])
        if current_user.role != UserRole.ADMIN and not franchise_stores:
            continue

        total_revenue = revenue_lookup.get(franchise.id, {}).get("revenue", 0.0)
        total_orders = revenue_lookup.get(franchise.id, {}).get("orders", 0)
        avg_order_value = round(total_revenue / total_orders, 2) if total_orders else 0.0
        last_order = None
        if franchise_stores:
            last_order = max((store.last_order_date for store in franchise_stores if store.last_order_date), default=None)
        inactive_count = sum(
            1
            for store in franchise_stores
            if not store.last_order_date or store.last_order_date < thirty_day_cutoff
        )

        top_store_name = None
        top_store_revenue = 0.0
        for store in franchise_stores:
            revenue = store_revenue.get(store.id, 0.0)
            if revenue >= top_store_revenue:
                top_store_revenue = revenue
                top_store_name = store.display_name

        results.append(
            {
                "id": franchise.id,
                "name": franchise.name,
                "color": franchise.color_hex,
                "description": franchise.description,
                "store_count": len(franchise_stores),
                "total_revenue": round(total_revenue, 2),
                "total_orders": total_orders,
                "avg_order_value": avg_order_value,
                "inactive_stores": inactive_count,
                "last_order_date": last_order,
                "top_store": top_store_name,
                "top_store_revenue": round(top_store_revenue, 2),
            }
        )

    return results

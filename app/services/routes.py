from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt
from typing import List, Sequence

from sqlmodel import Session, select

from ..models import Route, RouteStatus, RouteStop, Store, User, UserRole


AVERAGE_SPEED_KMH = 55.0  # heuristic for travel time estimations


def _haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlon1, rlat2, rlon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    earth_radius_km = 6371.0
    return earth_radius_km * c


def _travel_minutes(distance_km: float) -> float:
    if distance_km <= 0:
        return 0.0
    return (distance_km / AVERAGE_SPEED_KMH) * 60.0


def optimize_store_sequence(stores: Sequence[Store]) -> List[Store]:
    """Return stores ordered using a nearest-neighbour heuristic."""

    remaining = [store for store in stores if store.latitude is not None and store.longitude is not None]
    unordered = [store for store in stores if store not in remaining]
    if not remaining:
        return list(stores)

    ordered: List[Store] = []
    current = remaining.pop(0)
    ordered.append(current)
    while remaining:
        current_lat = current.latitude or 0.0
        current_lon = current.longitude or 0.0
        next_store = min(
            remaining,
            key=lambda candidate: _haversine_distance_km(
                current_lat,
                current_lon,
                candidate.latitude or current_lat,
                candidate.longitude or current_lon,
            ),
        )
        ordered.append(next_store)
        remaining.remove(next_store)
        current = next_store

    ordered.extend(unordered)
    return ordered


@dataclass
class RouteMetrics:
    total_distance_km: float
    total_travel_minutes: float


def calculate_route_metrics(stores: Sequence[Store]) -> RouteMetrics:
    total_distance = 0.0
    total_minutes = 0.0
    if not stores:
        return RouteMetrics(total_distance, total_minutes)

    for prev, current in zip(stores, stores[1:]):
        if (
            prev.latitude is None
            or prev.longitude is None
            or current.latitude is None
            or current.longitude is None
        ):
            continue
        distance = _haversine_distance_km(prev.latitude, prev.longitude, current.latitude, current.longitude)
        total_distance += distance
        total_minutes += _travel_minutes(distance)
    return RouteMetrics(total_distance, total_minutes)


def rebuild_route_stops(route: Route, stores: Sequence[Store], existing_comments: dict[int, str] | None = None) -> None:
    ordered = optimize_store_sequence(stores)
    metrics = calculate_route_metrics(ordered)
    route.total_distance_km = round(metrics.total_distance_km, 1)
    route.total_travel_minutes = round(metrics.total_travel_minutes, 1)

    comment_lookup = existing_comments or {}
    route.stops.clear()
    previous_store: Store | None = None
    for index, store in enumerate(ordered, start=1):
        distance = 0.0
        minutes = 0.0
        if (
            previous_store
            and previous_store.latitude is not None
            and previous_store.longitude is not None
            and store.latitude is not None
            and store.longitude is not None
        ):
            distance = _haversine_distance_km(
                previous_store.latitude,
                previous_store.longitude,
                store.latitude,
                store.longitude,
            )
            minutes = _travel_minutes(distance)
        stop = RouteStop(
            sequence=index,
            store_id=store.id,
            comments=comment_lookup.get(store.id),
            travel_distance_km=round(distance, 2),
            travel_minutes=round(minutes, 1),
        )
        route.stops.append(stop)
        previous_store = store


def user_can_edit_route(user: User, route: Route) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    if route.status == RouteStatus.CONFIRMED:
        return False
    if user.id in {route.created_by_user_id, route.assigned_user_id}:
        return True
    return False


def user_can_view_route(user: User, route: Route) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    if user.id in {route.created_by_user_id, route.assigned_user_id}:
        return True
    return False


def list_accessible_routes(session: Session, current_user: User) -> List[Route]:
    query = select(Route)
    if current_user.role != UserRole.ADMIN:
        query = query.where(
            (Route.created_by_user_id == current_user.id) | (Route.assigned_user_id == current_user.id)
        )
    query = query.order_by(Route.created_at.desc())
    return list(session.exec(query))

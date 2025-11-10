from __future__ import annotations

import enum
from datetime import datetime, date
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    SALESMAN = "SALESMAN"
    SUBSALESMAN = "SUBSALESMAN"
    CLIENT = "CLIENT"


class StoreStatus(str, enum.Enum):
    LEAD = "LEAD"
    ACTIVE = "ACTIVE"
    DORMANT = "DORMANT"
    CLOSED = "CLOSED"


class ActivityEntityType(str, enum.Enum):
    STORE = "store"
    ORDER = "order"
    USER = "user"


class EmailTrigger(str, enum.Enum):
    NEW_STORE_CREATED = "NEW_STORE_CREATED"
    INACTIVE_30D = "INACTIVE_30D"
    MONTHLY_SUMMARY = "MONTHLY_SUMMARY"


class UserBase(SQLModel):
    name: str
    email: str = Field(index=True, unique=True)
    role: UserRole = Field(default=UserRole.CLIENT)
    active: bool = True


class User(UserBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    owned_stores: List["Store"] = Relationship(back_populates="owner", sa_relationship_kwargs={"foreign_keys": "Store.owner_user_id"})
    sub_owned_stores: List["Store"] = Relationship(back_populates="sub_owner", sa_relationship_kwargs={"foreign_keys": "Store.sub_owner_user_id"})
    activities: List["Activity"] = Relationship(back_populates="actor")


class StoreBase(SQLModel):
    display_name: str
    legal_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address1: Optional[str] = None
    address2: Optional[str] = None
    city: str
    province: str
    postal_code: Optional[str] = None
    country: str = "Canada"
    latitude: Optional[float] = Field(default=None, index=True)
    longitude: Optional[float] = Field(default=None, index=True)
    google_place_id: Optional[str] = Field(default=None, index=True)
    status: StoreStatus = Field(default=StoreStatus.LEAD)
    tags: List[str] = Field(default_factory=list, sa_column_kwargs={"type_": "JSON"})
    notes: Optional[str] = None
    last_order_date: Optional[date] = Field(default=None, index=True)


class Store(StoreBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    sub_owner_user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    franchise_id: Optional[int] = Field(default=None, foreign_key="franchise.id")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    owner: Optional[User] = Relationship(back_populates="owned_stores", sa_relationship_kwargs={"foreign_keys": "Store.owner_user_id"})
    sub_owner: Optional[User] = Relationship(back_populates="sub_owned_stores", sa_relationship_kwargs={"foreign_keys": "Store.sub_owner_user_id"})
    franchise: Optional["Franchise"] = Relationship(back_populates="stores")
    orders: List["Order"] = Relationship(back_populates="store")
    activities: List["Activity"] = Relationship(back_populates="store")


class OrderBase(SQLModel):
    external_id: str = Field(index=True, unique=True)
    order_date: datetime
    subtotal: float
    excise_tax: float = 0.0
    gst_hst: float = 0.0
    pst: float = 0.0
    shipping: float = 0.0
    discount: float = 0.0
    total: float
    payment_method: Optional[str] = None
    status: Optional[str] = None
    raw_import_payload: Optional[str] = Field(default=None, sa_column_kwargs={"type_": "TEXT"})


class Order(OrderBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: Optional[int] = Field(default=None, foreign_key="store.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    store: Optional[Store] = Relationship(back_populates="orders")
    items: List["OrderItem"] = Relationship(back_populates="order")
    activities: List["Activity"] = Relationship(back_populates="order")


class OrderItemBase(SQLModel):
    sku: Optional[str] = None
    product_name: str
    category: Optional[str] = None
    nicotine_pct: Optional[float] = None
    puff_count: Optional[int] = None
    ice_level: Optional[str] = None
    qty: int
    unit_price: float
    line_total: float


class OrderItem(OrderItemBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")

    order: Order = Relationship(back_populates="items")


class ActivityBase(SQLModel):
    entity_type: ActivityEntityType
    entity_id: int
    action: str
    metadata: Optional[str] = Field(default=None, sa_column_kwargs={"type_": "TEXT"})


class Activity(ActivityBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    actor_user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    actor: Optional[User] = Relationship(back_populates="activities")
    store: Optional[Store] = Relationship(sa_relationship_kwargs={"primaryjoin": "Activity.entity_id==Store.id", "foreign_keys": "Activity.entity_id"})
    order: Optional[Order] = Relationship(sa_relationship_kwargs={"primaryjoin": "Activity.entity_id==Order.id", "foreign_keys": "Activity.entity_id"})


class EmailRuleBase(SQLModel):
    trigger: EmailTrigger
    to_emails: List[str] = Field(default_factory=list, sa_column_kwargs={"type_": "JSON"})
    cc_emails: List[str] = Field(default_factory=list, sa_column_kwargs={"type_": "JSON"})
    active: bool = True
    template_name: str


class EmailRule(EmailRuleBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class FranchiseBase(SQLModel):
    name: str = Field(index=True, unique=True)
    color_hex: str = Field(default="#6c757d")
    description: Optional[str] = None


class Franchise(FranchiseBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    stores: List[Store] = Relationship(back_populates="franchise")


class RouteStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"


class RouteBase(SQLModel):
    name: str
    status: RouteStatus = Field(default=RouteStatus.DRAFT)
    planned_date: Optional[date] = None
    created_by_user_id: int = Field(foreign_key="user.id")
    assigned_user_id: int = Field(foreign_key="user.id")
    notes: Optional[str] = None
    total_distance_km: float = 0.0
    total_travel_minutes: float = 0.0


class Route(RouteBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    created_by: User = Relationship(sa_relationship_kwargs={"foreign_keys": "Route.created_by_user_id"})
    assigned_user: User = Relationship(sa_relationship_kwargs={"foreign_keys": "Route.assigned_user_id"})
    stops: List["RouteStop"] = Relationship(back_populates="route", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class RouteStopBase(SQLModel):
    sequence: int
    store_id: int = Field(foreign_key="store.id")
    comments: Optional[str] = None
    travel_distance_km: float = 0.0
    travel_minutes: float = 0.0


class RouteStop(RouteStopBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    route_id: int = Field(foreign_key="route.id")

    route: Route = Relationship(back_populates="stops")
    store: Store = Relationship()

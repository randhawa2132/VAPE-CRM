from __future__ import annotations

import random
from datetime import datetime, timedelta

from faker import Faker
from sqlmodel import Session, select

from .auth import get_password_hash
from .database import engine, init_db
from .models import (
    EmailRule,
    EmailTrigger,
    Franchise,
    Order,
    OrderItem,
    Route,
    Store,
    StoreStatus,
    User,
    UserRole,
)
from .services.routes import rebuild_route_stops
from .settings import settings

fake = Faker("en_CA")

PROVINCES = ["AB", "BC", "ON", "QC"]
CATEGORIES = ["Disposable", "E-Liquid", "Pod", "Accessory"]
FRANCHISES = [
    ("VapeWave Collective", "#8b5cf6", "Urban storefronts across Western Canada"),
    ("Northern Clouds", "#0ea5e9", "Family-owned franchise with strong loyalty programs"),
    ("Prairie Vapor", "#f97316", "High-volume retailers along the Trans-Canada"),
    ("Coastal Mist", "#10b981", "BC-based experiential lounges and boutiques"),
]


def create_user(session: Session, name: str, email: str, role: UserRole) -> User:
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        return existing
    user = User(name=name, email=email, role=role, password_hash=get_password_hash("Welcome123"))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def seed() -> None:
    init_db()
    with Session(engine) as session:
        admin = create_user(session, "Admin", "admin@example.com", UserRole.ADMIN)
        salesmen = [create_user(session, f"Sales {i}", f"sales{i}@example.com", UserRole.SALESMAN) for i in range(1, 4)]
        subs = [create_user(session, f"Sub {i}", f"sub{i}@example.com", UserRole.SUBSALESMAN) for i in range(1, 6)]

        if session.exec(select(Store)).first():
            return

        franchises = []
        for name, color, description in FRANCHISES:
            existing_franchise = session.exec(select(Franchise).where(Franchise.name == name)).first()
            if existing_franchise:
                franchises.append(existing_franchise)
                continue
            franchise = Franchise(name=name, color_hex=color, description=description)
            session.add(franchise)
            session.commit()
            session.refresh(franchise)
            franchises.append(franchise)

        stores: list[Store] = []
        for _ in range(100):
            owner = random.choice(salesmen)
            sub_owner = random.choice(subs)
            status = random.choices(
                [StoreStatus.LEAD, StoreStatus.ACTIVE, StoreStatus.DORMANT, StoreStatus.CLOSED],
                weights=[0.2, 0.5, 0.2, 0.1],
                k=1,
            )[0]
            city = fake.city()
            province = random.choice(PROVINCES)
            franchise_choice = random.choice(franchises + [None, None]) if franchises else None
            store = Store(
                display_name=fake.company(),
                city=city,
                province=province,
                address1=fake.street_address(),
                postal_code=fake.postalcode(),
                phone=fake.phone_number(),
                email=fake.company_email(),
                latitude=float(fake.latitude()),
                longitude=float(fake.longitude()),
                status=status,
                owner_user_id=owner.id,
                sub_owner_user_id=sub_owner.id,
                franchise_id=franchise_choice.id if franchise_choice else None,
            )
            session.add(store)
            session.commit()
            session.refresh(store)
            stores.append(store)

        for store in stores:
            for months_back in range(1, 13):
                if random.random() < 0.4:
                    continue
                order_date = datetime.utcnow() - timedelta(days=30 * months_back) + timedelta(days=random.randint(0, 28))
                order = Order(
                    external_id=f"{store.id}-{months_back}-{random.randint(1000,9999)}",
                    store_id=store.id,
                    order_date=order_date,
                    subtotal=random.uniform(200, 1500),
                    excise_tax=random.uniform(20, 120),
                    gst_hst=random.uniform(10, 60),
                    pst=random.uniform(5, 40),
                    shipping=random.uniform(0, 30),
                    discount=random.uniform(0, 100),
                    total=0,
                    payment_method="Credit Card",
                    status="completed",
                )
                order.total = order.subtotal + order.excise_tax + order.gst_hst + order.pst + order.shipping - order.discount
                session.add(order)
                session.commit()
                session.refresh(order)

                for _ in range(random.randint(1, 4)):
                    category = random.choice(CATEGORIES)
                    qty = random.randint(1, 12)
                    unit_price = random.uniform(10, 40)
                    item = OrderItem(
                        order_id=order.id,
                        sku=fake.ean(length=8),
                        product_name=f"{category} {fake.word().title()}",
                        category=category,
                        nicotine_pct=random.choice([None, 20.0, 35.0, 50.0]),
                        puff_count=random.choice([None, 2000, 3000, 5000]),
                        ice_level=random.choice([None, "ICE", "NORMAL"]),
                        qty=qty,
                        unit_price=unit_price,
                        line_total=qty * unit_price,
                    )
                    session.add(item)
                store.last_order_date = order.order_date.date()
                session.add(store)
                session.commit()

        for trigger in EmailTrigger:
            rule = EmailRule(trigger=trigger, to_emails=[settings.default_admin_email], template_name="default")
            session.add(rule)
        session.commit()

        # Seed sample planned routes for quick demos
        for salesman in salesmen:
            assigned_stores = [store for store in stores if store.owner_user_id == salesman.id][:5]
            if not assigned_stores:
                continue
            route = Route(
                name=f"{salesman.name.split()[0]} Territory Tour",
                planned_date=datetime.utcnow().date(),
                created_by_user_id=admin.id,
                assigned_user_id=salesman.id,
                notes="Generated demo route for onboarding",
            )
            rebuild_route_stops(route, assigned_stores)
            session.add(route)
        session.commit()


if __name__ == "__main__":
    seed()

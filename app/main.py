from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlmodel import Session, select

from . import auth
from .auth import SESSION_COOKIE_NAME, create_session_cookie, get_current_user, get_password_hash, require_roles
from .database import get_session, init_db
from .email.service import send_email
from .models import ActivityEntityType, EmailRule, EmailTrigger, Store, StoreStatus, User, UserRole
from .services import reports
from .services.importer import import_orders
from .settings import settings
from .utils.geocode import geocode_address

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title=settings.app_name)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.on_event("startup")
def startup() -> None:
    init_db()


def _set_session_cookie(response: Response, user_id: int) -> None:
    cookie = create_session_cookie(user_id)
    response.set_cookie(SESSION_COOKIE_NAME, cookie, httponly=True, max_age=auth.SESSION_MAX_AGE)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request) -> Response:
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie and auth.load_session_cookie(cookie):
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "app_name": settings.app_name})


@app.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...), session: Session = Depends(get_session)):
    user = auth.authenticate_user(email, password, session)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "app_name": settings.app_name, "error": "Invalid credentials"},
            status_code=400,
        )
    response = RedirectResponse(url="/dashboard", status_code=302)
    _set_session_cookie(response, user.id)
    return response


@app.get("/logout")
async def logout() -> Response:
    response = RedirectResponse(url="/login")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    now = datetime.utcnow()
    start_month = datetime(now.year, now.month, 1)
    previous_month = start_month - timedelta(days=1)
    mtd = reports.revenue_totals(session, current_user, start=start_month)
    ytd = reports.revenue_totals(session, current_user, start=datetime(now.year, 1, 1))
    inactive = reports.inactive_stores(session, current_user, days=30)
    category = reports.category_mix(session, current_user)
    top_products = reports.top_products(session, current_user, limit=5)

    context = {
        "request": request,
        "user": current_user,
        "mtd": mtd,
        "ytd": ytd,
        "inactive": inactive,
        "category_mix": category,
        "top_products": top_products,
        "previous_month": previous_month.strftime("%B %Y"),
    }
    return templates.TemplateResponse("dashboard.html", context)


@app.get("/stores", response_class=HTMLResponse)
async def list_stores(request: Request, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    query = select(Store)
    if current_user.role == UserRole.SALESMAN:
        query = query.where(Store.owner_user_id == current_user.id)
    elif current_user.role == UserRole.SUBSALESMAN:
        query = query.where(Store.sub_owner_user_id == current_user.id)
    stores = session.exec(query.order_by(Store.city, Store.display_name)).all()
    return templates.TemplateResponse(
        "stores.html",
        {
            "request": request,
            "stores": stores,
            "user": current_user,
            "status_options": list(StoreStatus),
        },
    )


@app.get("/stores/map", response_class=HTMLResponse)
async def stores_map(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        "map.html",
        {
            "request": request,
            "user": current_user,
            "google_maps_api_key": settings.google_maps_api_key,
        },
    )


@app.get("/api/stores.geojson")
async def stores_geojson(session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    query = select(Store)
    if current_user.role == UserRole.SALESMAN:
        query = query.where(Store.owner_user_id == current_user.id)
    elif current_user.role == UserRole.SUBSALESMAN:
        query = query.where(Store.sub_owner_user_id == current_user.id)
    stores = session.exec(query).all()
    features: List[Dict[str, Any]] = []
    for store in stores:
        if store.latitude is None or store.longitude is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [store.longitude, store.latitude]},
                "properties": {
                    "id": store.id,
                    "name": store.display_name,
                    "status": store.status,
                    "city": store.city,
                    "province": store.province,
                    "owner": store.owner.name if store.owner else None,
                    "sub_owner": store.sub_owner.name if store.sub_owner else None,
                    "last_order_date": store.last_order_date.isoformat() if store.last_order_date else None,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


@app.get("/stores/new", response_class=HTMLResponse)
async def new_store_form(request: Request, session: Session = Depends(get_session), current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SALESMAN))):
    salesmen = session.exec(select(User).where(User.role == UserRole.SALESMAN)).all()
    subs = session.exec(select(User).where(User.role == UserRole.SUBSALESMAN)).all()
    return templates.TemplateResponse(
        "store_form.html",
        {"request": request, "user": current_user, "salesmen": salesmen, "subs": subs},
    )


@app.post("/stores/new")
async def create_store(
    request: Request,
    display_name: str = Form(...),
    city: str = Form(...),
    province: str = Form(...),
    owner_user_id: Optional[int] = Form(None),
    sub_owner_user_id: Optional[int] = Form(None),
    address1: Optional[str] = Form(None),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    google_place_id: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SALESMAN)),
):
    duplicate = None
    if google_place_id:
        duplicate = session.exec(select(Store).where(Store.google_place_id == google_place_id)).first()
    elif address1:
        duplicate = session.exec(
            select(Store).where(Store.display_name == display_name, Store.address1 == address1)
        ).first()
    if duplicate:
        raise HTTPException(status_code=400, detail="Store already exists")

    store = Store(
        display_name=display_name,
        city=city,
        province=province,
        owner_user_id=owner_user_id or current_user.id,
        sub_owner_user_id=sub_owner_user_id,
        address1=address1,
        google_place_id=google_place_id,
    )

    if (latitude is None or longitude is None) and address1:
        geo = await geocode_address(f"{address1}, {city}, {province}")
        if geo:
            store.latitude, store.longitude, place_id = geo
            if not store.google_place_id:
                store.google_place_id = place_id
    else:
        store.latitude = latitude
        store.longitude = longitude

    session.add(store)
    session.commit()
    session.refresh(store)

    auth.record_activity(session, actor=current_user, entity_type=ActivityEntityType.STORE, entity_id=store.id, action="created")

    admin_rule = session.exec(select(EmailRule).where(EmailRule.trigger == EmailTrigger.NEW_STORE_CREATED)).first()
    recipients = [settings.default_admin_email]
    if admin_rule and admin_rule.active:
        recipients = admin_rule.to_emails or recipients
    map_link = f"https://www.google.com/maps/search/?api=1&query={store.latitude},{store.longitude}" if store.latitude else ""
    send_email(
        subject=f"New store created: {store.display_name}",
        body=f"Store {store.display_name} created by {current_user.name}. View: {map_link}",
        to_emails=recipients,
        cc_emails=admin_rule.cc_emails if admin_rule else None,
    )

    return RedirectResponse(url=f"/stores/{store.id}", status_code=302)


@app.get("/stores/{store_id}", response_class=HTMLResponse)
async def store_detail(store_id: int, request: Request, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    store = session.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404)
    if not auth.can_access_store(current_user, store):
        raise HTTPException(status_code=403)
    orders = sorted(store.orders, key=lambda o: o.order_date, reverse=True)
    return templates.TemplateResponse(
        "store_detail.html",
        {
            "request": request,
            "store": store,
            "orders": orders,
            "user": current_user,
        },
    )


@app.post("/stores/{store_id}/update")
async def update_store(
    store_id: int,
    request: Request,
    status: StoreStatus = Form(...),
    notes: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    store = session.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404)
    if not auth.can_access_store(current_user, store):
        raise HTTPException(status_code=403)
    store.status = status
    store.notes = notes
    session.add(store)
    session.commit()

    auth.record_activity(session, actor=current_user, entity_type=ActivityEntityType.STORE, entity_id=store.id, action="updated")
    return RedirectResponse(url=f"/stores/{store.id}", status_code=302)


@app.get("/orders/import", response_class=HTMLResponse)
async def order_import_page(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("order_import.html", {"request": request, "user": current_user})


@app.post("/orders/import")
async def order_import(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    summary = import_orders(session, current_user=current_user, file_content=content)
    return templates.TemplateResponse(
        "order_import.html",
        {
            "request": request,
            "user": current_user,
            "summary": summary.as_dict(),
        },
    )


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, session: Session = Depends(get_session), current_user: User = Depends(get_current_user)):
    monthly = reports.monthly_spend(session, current_user)
    province = reports.province_breakdown(session, current_user)
    inactive_30 = reports.inactive_stores(session, current_user, days=30)
    top = reports.top_products(session, current_user)
    return templates.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "user": current_user,
            "monthly": monthly,
            "province": province,
            "inactive": inactive_30,
            "top_products": top,
        },
    )


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, session: Session = Depends(get_session), current_user: User = Depends(require_roles(UserRole.ADMIN))):
    users = session.exec(select(User).order_by(User.role, User.name)).all()
    return templates.TemplateResponse("users.html", {"request": request, "user": current_user, "users": users})


@app.post("/users")
async def create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    role: UserRole = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
    user = User(name=name, email=email, role=role, password_hash=get_password_hash(password))
    session.add(user)
    session.commit()
    auth.record_activity(session, actor=current_user, entity_type=ActivityEntityType.USER, entity_id=user.id, action="created")
    return RedirectResponse(url="/users", status_code=302)


@app.get("/settings/email", response_class=HTMLResponse)
async def email_settings(request: Request, session: Session = Depends(get_session), current_user: User = Depends(require_roles(UserRole.ADMIN))):
    rules = session.exec(select(EmailRule)).all()
    return templates.TemplateResponse("email_settings.html", {"request": request, "user": current_user, "rules": rules})


@app.post("/settings/email")
async def update_email_rule(
    rule_id: Optional[int] = Form(None),
    trigger: EmailTrigger = Form(...),
    to_emails: str = Form(""),
    cc_emails: str = Form(""),
    active: Optional[bool] = Form(None),
    template_name: str = Form("default"),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    to_list = [email.strip() for email in to_emails.split(",") if email.strip()]
    cc_list = [email.strip() for email in cc_emails.split(",") if email.strip()]
    if rule_id:
        rule = session.get(EmailRule, rule_id)
        if not rule:
            raise HTTPException(status_code=404)
    else:
        rule = EmailRule(trigger=trigger, template_name=template_name)
    rule.to_emails = to_list
    rule.cc_emails = cc_list
    rule.active = bool(active)
    rule.template_name = template_name
    session.add(rule)
    session.commit()
    return RedirectResponse(url="/settings/email", status_code=302)


@app.get("/health")
async def healthcheck() -> Dict[str, str]:
    return {"status": "ok"}

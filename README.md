# Vape CRM

An internal CRM for vape distribution teams built with FastAPI, SQLModel, and Jinja templates. The application centralises vape store data, visualises locations on Google Maps, imports WooCommerce orders, and offers dashboards plus reports tailored by role (Admin, Salesman, Sub-Salesman, Client).

## Features

- Role-based access control for Admin, Salesman, Sub-Salesman, and Client users.
- Store management with ownership assignments, pipeline statuses, activity logging, and notes.
- Google Maps view with clustering, status-coloured markers, and quick-create workflow.
- Territory route planning for Sales and Sub-Sales teams with automated stop optimisation, ownership handoffs, and visit notes.
- WooCommerce CSV ingestion with fuzzy store matching, duplicate prevention, item parsing, and summary reporting.
- Dashboards for revenue KPIs, inactive store follow-ups, category mix, and top products.
- Reporting tabs for monthly spend, provincial totals, inactive stores, and product leaders.
- Franchise management and analytics with colour-coded map overlays, aggregated KPIs, and top-performer insights.
- Email automation rules (new store, inactivity, monthly summary) with SMTP integration or console mock.
- Seed script that loads demo users, 100 Canadian stores (with franchise coverage), 12 months of synthetic orders, and pre-built sample routes.

## Getting Started

If you just want the TL;DR for spinning the CRM up on your laptop, jump to the
[Localhost Deployment Quickstart](docs/LOCALHOST_DEPLOYMENT.md). The sections
below walk through the same process in more detail.

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment (optional)

Create a `.env` file to override defaults:

```env
SECRET_KEY=super-secret
GOOGLE_MAPS_API_KEY=your_google_maps_key
DEFAULT_ADMIN_EMAIL=admin@example.com
SMTP_HOST=smtp.yourdomain.com
SMTP_USERNAME=user
SMTP_PASSWORD=pass
SMTP_FROM_EMAIL=crm@yourdomain.com
```

### 3. Seed demo data

```bash
python -m app.seeds
```

This creates an admin (`admin@example.com` / `Welcome123`), three salesmen, five sub-salesmen, colour-coded franchise groups, geo-coded stores, demo routes, and a year of synthetic WooCommerce-style orders.

### 4. Run the server

```bash
uvicorn app.main:app --reload
```

Browse to `http://localhost:8000/login` and sign in with one of the seeded accounts.

## CSV Import Notes

- Required columns: `order_id`, `order_date`, `billing_company`, `billing_email`, `billing_address1`, `billing_city`, `billing_state/province`, `billing_postcode`, `subtotal`, `total`, `payment_method`, `status`.
- Optional columns for richer data: `shipping_total`, `discount_total`, `tax_total`, per-line columns such as `line_1_name`, `line_1_quantity`, etc., or a JSON `line_items` field.
- The importer matches stores by company name (exact/fuzzy), email, then phone. Unmatched rows create Lead stores flagged for review.
- Re-importing the same order `order_id` updates the existing record (idempotent).

## Testing

The project includes a `/health` endpoint for uptime checks and deterministic seed data for demos. Use FastAPI's interactive docs at `/docs` for API exploration.

## Deployment Notes

- The dependency set is intentionally lightweight so the FastAPI app can be deployed to serverless providers such as Vercel without exceeding their 250 MB uncompressed bundle limits. If you need heavy analytics libraries (e.g., pandas, NumPy, scikit-learn), prefer offloading those workloads to background jobs or analytics pipelines instead of bundling them with the API service.

## Project Structure

```
app/
  main.py             # FastAPI entry point and routes
  models.py           # SQLModel ORM models & enums
  database.py         # Engine + session helpers
  auth.py             # Session auth helpers and activity logging
  services/
    importer.py       # WooCommerce CSV ingestion
    reports.py        # Dashboard/report aggregations
    routes.py         # Route optimisation helpers and access checks
  utils/
    geocode.py        # Google geocoding helper
  email/
    service.py        # SMTP/console email sender
  templates/          # Jinja2 templates for UI
  static/             # CSS assets
  seeds.py            # Demo data generator
requirements.txt      # Python dependencies
```

## Roadmap

- Extend API with JSON endpoints for modern front-end frameworks.
- Add scheduled tasks for inactivity/monthly emails.
- Implement RFM scoring badges and advanced filtering UI.
- Integrate background geocoding queues for high-volume imports.

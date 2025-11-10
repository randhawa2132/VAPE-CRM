# Localhost Deployment Quickstart

This guide walks you through cloning the Vape CRM, configuring environment variables, loading demo data, and running the FastAPI server entirely on your workstation.

## 1. Clone and enter the project

```bash
git clone https://github.com/your-org/vape-crm.git
cd vape-crm
```

> Replace the repository URL above with the location of your fork if needed.

## 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell, run `python -m venv .venv` followed by `.venv\Scripts\Activate.ps1`.

## 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Configure environment variables

Copy `.env.example` to `.env` (or create the file) and override values as required:

```env
SECRET_KEY=your-local-secret
DATABASE_URL=sqlite:///./app/vape_crm.db
GOOGLE_MAPS_API_KEY=optional_google_key
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_FROM_EMAIL=crm@example.com
```

- The default SQLite path stores the database inside the `app/` directory so it is automatically picked up by the server.
- If you do not have a Google Maps API key handy, the map will still load with limited functionality.
- For email testing, you can run Python's debug SMTP server: `python -m smtpd -c DebuggingServer -n localhost:1025`.

## 5. Seed demo data (optional but recommended)

```bash
python -m app.seeds
```

This populates an admin user (`admin@example.com` / `Welcome123`), sample sales teams, 100 stores with geocodes/franchises, historical orders, and a few pre-built routes.

## 6. Run the development server

You can use Uvicorn directly or rely on the module's helper:

```bash
# Option A: using uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Option B: python -m entrypoint
python -m app.main
```

Either command serves the app at `http://localhost:8000/`. Visit `/login` and sign in with the seeded credentials.

## 7. Verify health

Open a new terminal (with the virtual environment activated) and run:

```bash
curl http://localhost:8000/health
```

You should receive `{ "status": "ok" }`.

## 8. Stopping the server

Press `CTRL+C` in the terminal running the server to shut it down. Your SQLite database (`app/vape_crm.db`) remains intact for subsequent runs.

---

For deployment to container platforms or cloud hosts, see the main README for additional guidance on dependency management and environment configuration.

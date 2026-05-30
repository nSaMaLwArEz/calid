# CALID

CALID is a congressional activity dashboard for exploring members, legislation, committees, actions, votes, and early analytics.

## What Is Included

- FastAPI backend with Congress.gov API client hooks and demo fallback data
- React + Vite frontend for member search, profile pages, bill details, vote explorer, and analytics
- PostgreSQL-ready schema models for later ETL persistence
- ETL starter command for scheduled Congress.gov pulls

## Project Layout

```text
backend/   FastAPI app, Congress.gov client, demo repository, ETL starter
frontend/  React app powered by Vite
```

## Requirements

- Python 3.11+
- Node.js 20+
- Optional: Congress.gov API key from https://api.congress.gov/

## Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 8000
```

If `CONGRESS_API_KEY` is not set, the backend serves demo data so the app is still explorable.

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

The frontend expects the backend at `http://localhost:8000`. Override with `VITE_API_BASE_URL`.

## ETL Starter

```powershell
cd backend
python -m app.etl.pull_congress --congress 119 --limit 25
```

The starter demonstrates member and bill pulls. The next production step is persisting these payloads into PostgreSQL on a scheduler.

## PostgreSQL

Start a local database:

```powershell
docker compose up -d postgres
cd backend
python -m app.create_schema
```

## Vote Data Note

Congress.gov exposes beta House roll-call vote endpoints. Senate vote coverage and some bill-level vote details may require additional sources, such as Senate XML feeds, GovInfo, Voteview, or another licensed civic data provider.

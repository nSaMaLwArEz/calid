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

## Data Diagnostics

Use these endpoints when Render is live but the app looks like it is showing stale, partial, or demo data:

```text
GET /health
GET /diagnostics/congress
GET /diagnostics/data
```

`/health` now reports whether Congress.gov is actually reachable, whether the roll-call vote cache has records, and whether demo fallback is active. `/diagnostics/data` shows cached roll-call vote totals, cached vote positions, the database backend, and the redacted Congress.gov probe error if the API is returning 403/other failures.

If Congress.gov is configured but `cached_roll_call_votes` is `0`, member and bill search can still use live Congress.gov data, but historical vote analytics will remain empty until the House vote sync runs.

## Frontend

```powershell
cd frontend
npm install
npm run dev
```

The frontend expects the backend at `http://localhost:8000`. Override with `VITE_API_BASE_URL`.

To build the frontend into the FastAPI service:

```powershell
cd frontend
npm install
npm run build
```

The production build is emitted to `backend/static` and served by FastAPI at `/`.

## ETL Starter

```powershell
cd backend
python -m app.etl.pull_congress --congress 119 --limit 25
```

The starter demonstrates member and bill pulls. The next production step is persisting these payloads into PostgreSQL on a scheduler.

Sync House roll-call vote rosters into the database:

```powershell
cd backend
python -m app.etl.sync_house_votes --congress 119 --session 1 --limit 25 --offset 0
```

On Render, attach a PostgreSQL database and set `DATABASE_URL` to the internal database URL. Then call the admin sync endpoint in batches:

```text
POST /admin/sync/house-votes?congress=119&session=1&limit=25&offset=0
```

Optionally set `SYNC_ADMIN_TOKEN` in Render and pass `&token=your-token` to protect the sync endpoint.

Repeat with offsets `25`, `50`, `75`, etc. Once synced, vote counts, member participation, missed votes, monthly history, and vote rosters are computed from PostgreSQL instead of live sampled API calls.

## PostgreSQL

Start a local database:

```powershell
docker compose up -d postgres
cd backend
python -m app.create_schema
```

## Vote Data Note

Congress.gov exposes beta House roll-call vote endpoints. Senate vote coverage and some bill-level vote details may require additional sources, such as Senate XML feeds, GovInfo, Voteview, or another licensed civic data provider.

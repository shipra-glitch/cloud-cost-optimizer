# Cloud Cost & Resource Optimization Dashboard

Full-stack FinOps tool: ingests infrastructure usage and cost data, flags idle / underused / orphaned
resources and cost spikes with rule-based Pandas pipelines, and estimates monthly savings.

**Stack:** React (Vite, Recharts) · FastAPI · PostgreSQL · Pandas · Docker · GitHub Actions

## Run with Docker (recommended)
    docker compose up --build
    # UI  -> http://localhost:3000
    # API -> http://localhost:8000/docs

On first start the API creates the schema, seeds 30 days of synthetic data and runs the analysis.

## Run locally without Docker
    # 1. database
    docker run -d --name cc-db -p 5432:5432 -e POSTGRES_USER=cloudcost \
      -e POSTGRES_PASSWORD=cloudcost -e POSTGRES_DB=cloudcost postgres:16-alpine
    # 2. backend
    cd backend && python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000
    # 3. frontend (new terminal)
    cd frontend && npm install && npm run dev      # http://localhost:5173

## Tests
    cd backend && python -m pytest -q

## Detection rules (backend/app/analysis.py)
| Rule | Condition (14-day window) | Estimated saving |
|---|---|---|
| Idle | EC2/RDS avg CPU < 5% and network < 50 MB/day | 100% of monthly cost |
| Underused | avg CPU < 20% and peak < 45% | 50% (one size down) |
| Unattached | EBS volume not attached | 100% |
| Cost spike | last 7-day avg cost >= 1.5x previous 7 days | informational |

## API
GET `/api/summary` · `/api/costs/daily` · `/api/costs/breakdown?by=team|type|region` ·
`/api/resources` · `/api/recommendations?rule=idle` — POST `/api/analyze` · `/api/seed`

## Using your own data
Load rows into `resources`, `usage_metrics` (daily cpu_avg, network_mb) and `cost_records`
(daily cost), then call `POST /api/analyze`. Set `AUTO_SEED=false` on the backend to skip sample data.

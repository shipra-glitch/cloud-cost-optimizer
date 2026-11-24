import json
import os
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .analysis import run_analysis
from .database import Base, engine
from . import models
from .seed import seed


def records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe list of dicts (NaN becomes null, dates become ISO strings)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        empty = conn.execute(text("SELECT COUNT(*) FROM resources")).scalar() == 0
    if empty and os.getenv("AUTO_SEED", "true").lower() == "true":
        seed()
        run_analysis(engine)
    yield


app = FastAPI(title="Cloud Cost & Resource Optimization API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

WINDOW = "c.date > (SELECT MAX(date) FROM cost_records) - 30"


@app.get("/api/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/summary")
def summary():
    with engine.connect() as conn:
        spend = conn.execute(text(f"SELECT COALESCE(SUM(c.cost), 0) FROM cost_records c WHERE {WINDOW}")).scalar()
        resource_count = conn.execute(text("SELECT COUNT(*) FROM resources")).scalar()
    by_rule = pd.read_sql(
        "SELECT rule, COUNT(*) AS count, COALESCE(SUM(monthly_savings), 0) AS savings "
        "FROM recommendations GROUP BY rule",
        engine,
    )
    savings = float(by_rule["savings"].sum())
    return {
        "spend_30d": round(float(spend), 2),
        "potential_savings": round(savings, 2),
        "savings_pct": round(savings / float(spend) * 100, 1) if spend else 0,
        "resources": int(resource_count),
        "findings": int(by_rule["count"].sum()),
        "by_rule": records(by_rule),
    }


@app.get("/api/costs/daily")
def daily_costs():
    df = pd.read_sql(
        f"SELECT c.date, ROUND(SUM(c.cost)::numeric, 2) AS cost FROM cost_records c "
        f"WHERE {WINDOW} GROUP BY c.date ORDER BY c.date",
        engine,
    )
    df["cost"] = df["cost"].astype(float)
    return records(df)


@app.get("/api/costs/breakdown")
def cost_breakdown(by: str = Query("team", pattern="^(team|type|region)$")):
    # `by` is validated by the regex above, so interpolating the column name is safe.
    df = pd.read_sql(
        f"SELECT r.{by} AS name, ROUND(SUM(c.cost)::numeric, 2) AS cost "
        f"FROM cost_records c JOIN resources r ON r.id = c.resource_id "
        f"WHERE {WINDOW} GROUP BY r.{by} ORDER BY cost DESC",
        engine,
    )
    df["cost"] = df["cost"].astype(float)
    return records(df)


@app.get("/api/resources")
def list_resources(type: str | None = None, team: str | None = None):
    df = pd.read_sql(
        text(
            f"""
            SELECT r.id, r.name, r.type, r.size, r.region, r.team, r.attached,
                   ROUND(SUM(c.cost)::numeric, 2) AS cost_30d,
                   (SELECT ROUND(AVG(u.cpu_avg)::numeric, 1) FROM usage_metrics u
                     WHERE u.resource_id = r.id) AS cpu_avg
            FROM resources r
            JOIN cost_records c ON c.resource_id = r.id AND {WINDOW}
            WHERE (CAST(:type AS TEXT) IS NULL OR r.type = :type)
              AND (CAST(:team AS TEXT) IS NULL OR r.team = :team)
            GROUP BY r.id ORDER BY cost_30d DESC
            """
        ),
        engine,
        params={"type": type, "team": team},
    )
    df["cost_30d"] = df["cost_30d"].astype(float)
    df["cpu_avg"] = df["cpu_avg"].astype(float)
    return records(df)


@app.get("/api/recommendations")
def list_recommendations(rule: str | None = None):
    df = pd.read_sql(
        text(
            """
            SELECT rec.id, rec.resource_id, r.name, r.type, r.team, r.region,
                   rec.rule, rec.severity, rec.monthly_savings, rec.reason
            FROM recommendations rec JOIN resources r ON r.id = rec.resource_id
            WHERE (CAST(:rule AS TEXT) IS NULL OR rec.rule = :rule)
            ORDER BY rec.monthly_savings DESC, rec.id
            """
        ),
        engine,
        params={"rule": rule},
    )
    return records(df)


@app.post("/api/analyze")
def analyze_now():
    return run_analysis(engine)


@app.post("/api/seed")
def reseed():
    try:
        result = seed()
        result.update(run_analysis(engine))
        return result
    except Exception as exc:  # surface DB errors to the UI
        raise HTTPException(status_code=500, detail=str(exc))

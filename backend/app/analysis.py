"""Rule-based optimisation engine built on Pandas.

`analyze()` is a pure function (DataFrames in, DataFrame out) so it can be
unit-tested without a database. `run_analysis()` wires it to PostgreSQL.
"""
import numpy as np
import pandas as pd
from sqlalchemy import text

LOOKBACK_DAYS = 14
IDLE_CPU_PCT = 5.0          # avg CPU below this ...
IDLE_NETWORK_MB = 50.0      # ... and avg daily network below this => idle
UNDER_CPU_AVG_PCT = 20.0    # avg CPU below this ...
UNDER_CPU_PEAK_PCT = 45.0   # ... and peak below this => downsize candidate
RIGHTSIZE_SAVINGS = 0.5     # downsizing one size roughly halves the bill
SPIKE_RATIO = 1.5           # last 7d avg cost / previous 7d avg cost
MIN_DAYS_OF_DATA = 7

COLUMNS = ["resource_id", "rule", "severity", "monthly_savings", "reason"]
COMPUTE_TYPES = ["EC2", "RDS"]


def _severity(monthly_savings: float) -> str:
    if monthly_savings >= 200:
        return "high"
    if monthly_savings >= 75:
        return "medium"
    return "low"


def analyze(resources: pd.DataFrame, usage: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    if costs.empty:
        return pd.DataFrame(columns=COLUMNS)

    res = resources.set_index("id").copy()
    last_day = costs["date"].max()

    # --- monthly cost estimate: mean daily cost over the lookback window x 30 ---
    recent_costs = costs[costs["date"] > last_day - pd.Timedelta(days=LOOKBACK_DAYS)]
    res["monthly_cost"] = recent_costs.groupby("resource_id")["cost"].mean() * 30
    res["monthly_cost"] = res["monthly_cost"].fillna(0.0)

    # --- usage statistics per resource ---
    if not usage.empty:
        recent_usage = usage[usage["date"] > usage["date"].max() - pd.Timedelta(days=LOOKBACK_DAYS)]
        stats = recent_usage.groupby("resource_id").agg(
            cpu_avg=("cpu_avg", "mean"),
            cpu_peak=("cpu_avg", "max"),
            net_avg=("network_mb", "mean"),
            days=("date", "nunique"),
        )
        res = res.join(stats)
    for col in ("cpu_avg", "cpu_peak", "net_avg", "days"):
        if col not in res:
            res[col] = np.nan

    # --- vectorised rule masks ---
    is_compute = res["type"].isin(COMPUTE_TYPES) & (res["days"] >= MIN_DAYS_OF_DATA)
    idle = is_compute & (res["cpu_avg"] < IDLE_CPU_PCT) & (res["net_avg"] < IDLE_NETWORK_MB)
    under = (
        is_compute
        & ~idle
        & (res["cpu_avg"] < UNDER_CPU_AVG_PCT)
        & (res["cpu_peak"] < UNDER_CPU_PEAK_PCT)
    )
    orphaned = (res["type"] == "EBS") & res["attached"].eq(False)

    rows = []
    for rid, r in res[idle].iterrows():
        rows.append(dict(
            resource_id=rid, rule="idle", monthly_savings=r.monthly_cost,
            reason=f"Avg CPU {r.cpu_avg:.1f}% and {r.net_avg:.0f} MB/day network over "
                   f"{LOOKBACK_DAYS} days. Stop or terminate.",
        ))
    for rid, r in res[under].iterrows():
        rows.append(dict(
            resource_id=rid, rule="rightsize", monthly_savings=r.monthly_cost * RIGHTSIZE_SAVINGS,
            reason=f"Avg CPU {r.cpu_avg:.1f}%, peak {r.cpu_peak:.1f}%. "
                   f"Move down one instance size.",
        ))
    for rid, r in res[orphaned].iterrows():
        rows.append(dict(
            resource_id=rid, rule="orphaned", monthly_savings=r.monthly_cost,
            reason="Volume is not attached to any instance. Snapshot and delete.",
        ))

    # --- cost spikes: last 7 days vs the 7 days before ---
    window = costs[costs["date"] > last_day - pd.Timedelta(days=14)].copy()
    window["period"] = np.where(window["date"] > last_day - pd.Timedelta(days=7), "now", "before")
    pivot = window.pivot_table(index="resource_id", columns="period", values="cost", aggfunc="mean")
    if {"now", "before"} <= set(pivot.columns):
        pivot = pivot[pivot["before"] > 0]
        spikes = pivot[pivot["now"] / pivot["before"] >= SPIKE_RATIO]
        for rid, r in spikes.iterrows():
            extra = (r["now"] - r["before"]) * 30
            rows.append(dict(
                resource_id=rid, rule="spike", monthly_savings=0.0,
                reason=f"Daily cost rose {r['now'] / r['before']:.1f}x week over week "
                       f"(about ${extra:,.0f}/month extra). Investigate.",
            ))

    out = pd.DataFrame(rows, columns=[c for c in COLUMNS if c != "severity"])
    out["monthly_savings"] = out["monthly_savings"].round(2)
    out["severity"] = out["monthly_savings"].map(_severity)
    out.loc[out["rule"] == "spike", "severity"] = "medium"   # spikes carry no savings but need attention
    return out[COLUMNS].sort_values("monthly_savings", ascending=False).reset_index(drop=True)


def run_analysis(engine) -> dict:
    resources = pd.read_sql("SELECT * FROM resources", engine)
    usage = pd.read_sql("SELECT * FROM usage_metrics", engine, parse_dates=["date"])
    costs = pd.read_sql("SELECT * FROM cost_records", engine, parse_dates=["date"])

    recs = analyze(resources, usage, costs)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM recommendations"))
        if not recs.empty:
            recs.to_sql("recommendations", conn, if_exists="append", index=False)

    return {
        "recommendations": int(len(recs)),
        "potential_monthly_savings": float(recs["monthly_savings"].sum()) if len(recs) else 0.0,
    }

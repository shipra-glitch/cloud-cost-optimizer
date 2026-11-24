"""Generates realistic synthetic cloud usage + cost data."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import text

from .database import Base, engine

TEAMS = ["platform", "data", "payments", "growth", "ml-research"]
REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-south-1"]
EC2 = {"t3.medium": 30, "m5.large": 70, "m5.xlarge": 140, "c5.2xlarge": 250, "r5.2xlarge": 365}
RDS = {"db.t3.medium": 55, "db.m5.large": 125, "db.r5.xlarge": 350}

# profile -> (cpu mean range %, daily network MB range)
PROFILES = {
    "busy": ((40, 75), (800, 3000)),
    "under": ((8, 17), (150, 500)),
    "idle": ((0.5, 3), (1, 20)),
}


def seed(days: int = 30, n: int = 70, rng_seed: int = 42) -> dict:
    Base.metadata.create_all(engine)
    rng = np.random.default_rng(rng_seed)
    dates = [date.today() - timedelta(days=i) for i in range(days - 1, -1, -1)]

    resources, usage, costs = [], [], []
    busy_compute = []

    for i in range(n):
        rtype = str(rng.choice(["EC2", "RDS", "EBS", "S3"], p=[0.45, 0.15, 0.28, 0.12]))
        team = str(rng.choice(TEAMS))
        region = str(rng.choice(REGIONS))
        attached = None

        if rtype in ("EC2", "RDS"):
            sizes = EC2 if rtype == "EC2" else RDS
            size = str(rng.choice(list(sizes)))
            monthly = sizes[size]
            rid = ("i-" if rtype == "EC2" else "db-") + f"{rng.integers(16**8):08x}"
            profile = str(rng.choice(list(PROFILES), p=[0.55, 0.25, 0.20]))
            (cpu_lo, cpu_hi), (net_lo, net_hi) = PROFILES[profile]
            cpu_mean = rng.uniform(cpu_lo, cpu_hi)
            net_mean = rng.uniform(net_lo, net_hi)
            if profile == "busy":
                busy_compute.append(rid)
            for d in dates:
                usage.append(dict(
                    resource_id=rid, date=d,
                    cpu_avg=float(np.clip(rng.normal(cpu_mean, cpu_mean * 0.15 + 0.5), 0, 100)),
                    network_mb=float(max(0, rng.normal(net_mean, net_mean * 0.2))),
                ))
        elif rtype == "EBS":
            gb = int(rng.choice([100, 250, 500, 1000, 2000]))
            size, monthly = f"{gb} GB", gb * 0.08
            rid = f"vol-{rng.integers(16**8):08x}"
            attached = bool(rng.random() > 0.3)
        else:
            size, monthly = "standard", float(rng.uniform(20, 400))
            rid = f"s3-{team}-{rng.integers(16**4):04x}"

        resources.append(dict(id=rid, name=f"{team}-{rtype.lower()}-{i:02d}", type=rtype,
                              size=size, region=region, team=team, attached=attached))
        for d in dates:
            costs.append(dict(resource_id=rid, date=d,
                              cost=float(monthly / 30 * rng.normal(1, 0.03))))

    costs_df = pd.DataFrame(costs)
    # inject cost spikes on three busy resources (last 5 days cost 2.4x)
    spike_ids = set(busy_compute[:3])
    recent = costs_df["date"] > dates[-6]
    costs_df.loc[costs_df["resource_id"].isin(spike_ids) & recent, "cost"] *= 2.4

    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE recommendations, usage_metrics, cost_records, resources RESTART IDENTITY CASCADE"
        ))
        pd.DataFrame(resources).to_sql("resources", conn, if_exists="append", index=False)
        pd.DataFrame(usage).to_sql("usage_metrics", conn, if_exists="append", index=False)
        costs_df.to_sql("cost_records", conn, if_exists="append", index=False)

    return {"resources": len(resources), "usage_rows": len(usage), "cost_rows": len(costs_df)}


if __name__ == "__main__":
    from .analysis import run_analysis

    print(seed())
    print(run_analysis(engine))

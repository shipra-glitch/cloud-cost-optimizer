import pandas as pd

from app.analysis import analyze

DAYS = pd.date_range("2025-01-01", periods=14)


def frames(profiles):
    """profiles: {id: (type, cpu, net, daily_cost, attached)}"""
    res, usage, costs = [], [], []
    for rid, (rtype, cpu, net, cost, attached) in profiles.items():
        res.append(dict(id=rid, name=rid, type=rtype, size="x", region="r", team="t", attached=attached))
        for d in DAYS:
            if cpu is not None:
                usage.append(dict(resource_id=rid, date=d, cpu_avg=cpu, network_mb=net))
            costs.append(dict(resource_id=rid, date=d, cost=cost))
    usage_df = pd.DataFrame(usage, columns=["resource_id", "date", "cpu_avg", "network_mb"])
    return pd.DataFrame(res), usage_df, pd.DataFrame(costs)


def test_idle_instance_flagged_with_full_cost():
    out = analyze(*frames({"i-idle": ("EC2", 1.0, 5.0, 10.0, None)}))
    row = out.iloc[0]
    assert row.rule == "idle"
    assert row.monthly_savings == 300.0


def test_underused_instance_saves_half():
    out = analyze(*frames({"i-low": ("EC2", 12.0, 300.0, 10.0, None)}))
    assert out.iloc[0].rule == "rightsize"
    assert out.iloc[0].monthly_savings == 150.0


def test_busy_instance_not_flagged():
    out = analyze(*frames({"i-busy": ("EC2", 60.0, 2000.0, 10.0, None)}))
    assert out.empty


def test_unattached_volume_flagged():
    out = analyze(*frames({"vol-a": ("EBS", None, None, 2.0, False),
                           "vol-b": ("EBS", None, None, 2.0, True)}))
    assert list(out.resource_id) == ["vol-a"]
    assert out.iloc[0].rule == "orphaned"


def test_cost_spike_detected():
    res, usage, costs = frames({"i-spike": ("EC2", 60.0, 2000.0, 10.0, None)})
    costs.loc[costs["date"] > DAYS[-8], "cost"] = 30.0
    out = analyze(res, usage, costs)
    assert "spike" in set(out.rule)

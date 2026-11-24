from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, func

from .database import Base


class Resource(Base):
    __tablename__ = "resources"

    id = Column(String(40), primary_key=True)          # e.g. i-0a1b2c3d
    name = Column(String(120), nullable=False)
    type = Column(String(16), nullable=False, index=True)   # EC2 | RDS | EBS | S3
    size = Column(String(32))                          # instance class or volume size
    region = Column(String(32), nullable=False)
    team = Column(String(48), nullable=False, index=True)
    attached = Column(Boolean)                         # only meaningful for EBS


class UsageMetric(Base):
    __tablename__ = "usage_metrics"
    __table_args__ = (Index("ix_usage_resource_date", "resource_id", "date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_id = Column(String(40), ForeignKey("resources.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    cpu_avg = Column(Float, nullable=False)            # percent
    network_mb = Column(Float, nullable=False)         # MB transferred that day


class CostRecord(Base):
    __tablename__ = "cost_records"
    __table_args__ = (Index("ix_cost_resource_date", "resource_id", "date"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_id = Column(String(40), ForeignKey("resources.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    cost = Column(Float, nullable=False)               # USD per day


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_id = Column(String(40), ForeignKey("resources.id", ondelete="CASCADE"), nullable=False)
    rule = Column(String(24), nullable=False, index=True)   # idle | rightsize | orphaned | spike
    severity = Column(String(8), nullable=False)            # high | medium | low
    monthly_savings = Column(Float, nullable=False, default=0)
    reason = Column(String(300), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

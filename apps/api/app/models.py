import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (String, Numeric, Float, DateTime, ForeignKey, Boolean, # type: ignore
                        Text, Index, func)
from sqlalchemy.dialects.postgresql import UUID, JSONB # type: ignore
from sqlalchemy.orm import Mapped, mapped_column # type: ignore
from app.core.db import Base

def pk(): return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
def fk(t): return mapped_column(UUID(as_uuid=True), ForeignKey(f"{t}.id"))
def ts(**kw): return mapped_column(DateTime(timezone=True), **kw)

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk()
    username: Mapped[str] = mapped_column(String(60), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(30))  # analyst|senior_investigator|compliance_officer|administrator|auditor
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[uuid.UUID] = pk()
    customer_ref: Mapped[str] = mapped_column(String(64), unique=True)
    customer_type: Mapped[str] = mapped_column(String(20))
    onboarding_date: Mapped[datetime] = ts()
    occupation_or_business: Mapped[str | None] = mapped_column(String(120))
    expected_monthly_max: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    risk_rating: Mapped[str] = mapped_column(String(10), default="low")
    kyc_status: Mapped[str] = mapped_column(String(20), default="verified")

class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[uuid.UUID] = pk()
    customer_id: Mapped[uuid.UUID] = fk("customers")
    account_ref: Mapped[str] = mapped_column(String(64), unique=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    opened_at: Mapped[datetime] = ts()
    status: Mapped[str] = mapped_column(String(20), default="active")

class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[uuid.UUID] = pk()
    event_id: Mapped[str] = mapped_column(String(64), unique=True)
    source_account_id: Mapped[uuid.UUID] = fk("accounts")
    destination_account_id: Mapped[uuid.UUID] = fk("accounts")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    channel: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime] = ts()
    ingested_at: Mapped[datetime] = ts(server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="processed")
    __table_args__ = (
        Index("ix_tx_src_time", "source_account_id", "occurred_at"),
        Index("ix_tx_dst_time", "destination_account_id", "occurred_at"),
    )

class FeatureSnapshot(Base):
    __tablename__ = "features_snapshots"
    id: Mapped[uuid.UUID] = pk()
    account_id: Mapped[uuid.UUID] = fk("accounts")
    window_start: Mapped[datetime] = ts()
    window_end: Mapped[datetime] = ts()
    feature_json: Mapped[dict] = mapped_column(JSONB)
    computed_at: Mapped[datetime] = ts(server_default=func.now())

class RuleDefinition(Base):
    __tablename__ = "rule_definitions"
    id: Mapped[uuid.UUID] = pk()
    rule_key: Mapped[str] = mapped_column(String(60), index=True)
    version: Mapped[int] = mapped_column(default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    parameters_json: Mapped[dict] = mapped_column(JSONB)
    effective_from: Mapped[datetime] = ts()
    approved_by: Mapped[str | None] = mapped_column(String(60))

class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[uuid.UUID] = pk()
    alert_ref: Mapped[str] = mapped_column(String(20), unique=True)
    account_id: Mapped[uuid.UUID] = fk("accounts")
    transaction_id: Mapped[uuid.UUID] = fk("transactions")
    scenario_key: Mapped[str] = mapped_column(String(60), index=True)
    severity: Mapped[str] = mapped_column(String(10))
    score: Mapped[float] = mapped_column(Float)
    reasons_json: Mapped[dict] = mapped_column(JSONB)
    feature_snapshot_id: Mapped[uuid.UUID | None] = fk("features_snapshots")
    assigned_to: Mapped[uuid.UUID | None] = fk("users")
    created_at: Mapped[datetime] = ts(server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)

class Case(Base):
    __tablename__ = "cases"
    id: Mapped[uuid.UUID] = pk()
    case_ref: Mapped[str] = mapped_column(String(20), unique=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    owner_id: Mapped[uuid.UUID] = fk("users")
    status: Mapped[str] = mapped_column(String(25), default="open")
    opened_at: Mapped[datetime] = ts(server_default=func.now())
    closed_at: Mapped[datetime | None] = ts(nullable=True)
    disposition: Mapped[str | None] = mapped_column(String(40))

class CaseAlert(Base):
    __tablename__ = "case_alerts"
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("alerts.id"), primary_key=True)

class CaseNote(Base):
    __tablename__ = "case_notes"
    id: Mapped[uuid.UUID] = pk()
    case_id: Mapped[uuid.UUID] = fk("cases")
    author_id: Mapped[uuid.UUID] = fk("users")
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = ts(server_default=func.now())

class EvidenceItem(Base):
    __tablename__ = "evidence_items"
    id: Mapped[uuid.UUID] = pk()
    case_id: Mapped[uuid.UUID] = fk("cases")
    evidence_type: Mapped[str] = mapped_column(String(30))
    reference: Mapped[str] = mapped_column(String(200))
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = ts(server_default=func.now())

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = pk()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))
    before_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = ts(server_default=func.now())
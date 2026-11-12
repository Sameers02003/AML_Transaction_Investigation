import os
os.environ["DATABASE_URL"] = "postgresql+psycopg://aml:aml@localhost:5432/aml_test"

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.db import Base, engine, SessionLocal
from app.core.security import make_token
from app.main import app
from app.models import Customer, Account, RuleDefinition, User
from app.modules.rules.engine import DEFAULT_PARAMS


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as s:
        now = datetime.now(timezone.utc)
        for key, params in DEFAULT_PARAMS.items():
            s.add(RuleDefinition(rule_key=key, version=1, parameters_json=params,
                                 effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc)))
        for i in range(3):
            c = Customer(customer_ref=f"c{i}", customer_type="individual", onboarding_date=now - timedelta(days=300),
                         expected_monthly_max=Decimal("100000"))
            s.add(c)
            s.flush()
            s.add(Account(customer_id=c.id, account_ref=f"acct_t_{i}", opened_at=now - timedelta(days=300)))
        for role in ["analyst", "senior_investigator", "compliance_officer", "administrator", "auditor"]:
            s.add(User(username=role + "_t", password_hash="x", role=role))
        s.commit()
        yield s


@pytest.fixture()
def tokens(db):
    users = db.scalars(select(User)).all()
    return {u.role: {"Authorization": f"Bearer {make_token(u)}"} for u in users}


@pytest.fixture()
def client(db):
    return TestClient(app)


@pytest.fixture()
def low_threshold(monkeypatch):
    monkeypatch.setattr(settings, "alert_threshold", 0.2)


class _NoModel:
    def score(self, feats):
        return 0.0, [], None


@pytest.fixture()
def no_ml(monkeypatch):
    monkeypatch.setattr("app.modules.monitoring.service.anomaly_scorer", _NoModel())
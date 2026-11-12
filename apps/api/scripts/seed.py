import bcrypt
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.core.db import SessionLocal
from app.models import User, Customer, Account

def hp(p): return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

with SessionLocal() as db:
    for name, role in [("analyst1", "analyst"), ("senior1", "senior_investigator"),
                       ("compliance1", "compliance_officer"), ("admin1", "administrator"),
                       ("auditor1", "auditor")]:
        if not db.scalar(select(User).where(User.username == name)):
            db.add(User(username=name, password_hash=hp(name + "-demo"), role=role))
    now = datetime.now(timezone.utc)
    for i, ref in [(101, "acct_demo_101"), (907, "acct_demo_907")]:
        if not db.scalar(select(Account).where(Account.account_ref == ref)):
            c = Customer(customer_ref=f"cust_{i}", customer_type="individual",
                         onboarding_date=now - timedelta(days=400), occupation_or_business="Salaried",
                         expected_monthly_max=100000, risk_rating="low")
            db.add(c); db.flush()
            db.add(Account(customer_id=c.id, account_ref=ref, opened_at=now - timedelta(days=400)))
    db.commit()
from app.models import RuleDefinition
from app.modules.rules.engine import DEFAULT_PARAMS
with SessionLocal() as db:
    for key, params in DEFAULT_PARAMS.items():
        if not db.scalar(select(RuleDefinition).where(RuleDefinition.rule_key == key)):
            db.add(RuleDefinition(rule_key=key, version=1, enabled=True, parameters_json=params,
                                  effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc), approved_by="seed"))
    db.commit()
print("seeded")

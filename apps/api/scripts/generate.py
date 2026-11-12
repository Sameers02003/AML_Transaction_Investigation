import argparse, csv, random, uuid, time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import select
from app.core.db import SessionLocal
from app.core.kafka import publish
from app.models import Customer, Account, Transaction

random.seed(7)
N = 200
REFS = [f"acct_demo_{i:03d}" for i in range(N)]
HUBS = ["acct_hub_employer", "acct_hub_utility", "acct_hub_telecom"]
MULES = ["acct_mule_01", "acct_mule_02"]
now = lambda: datetime.now(timezone.utc)

def seed():
    with SessionLocal() as db:
        if db.scalar(select(Account).where(Account.account_ref == REFS[0])):
            print("already seeded"); return
        def mk(ref, kind, age_days, exp, risk="low", occ="Salaried"):
            if db.scalar(select(Account).where(Account.account_ref == ref)): return
            c = Customer(customer_ref="cust_" + ref, customer_type=kind, onboarding_date=now() - timedelta(days=age_days),
                         occupation_or_business=occ, expected_monthly_max=exp, risk_rating=risk)
            db.add(c); db.flush()
            db.add(Account(customer_id=c.id, account_ref=ref, opened_at=now() - timedelta(days=age_days)))
        for r in HUBS: mk(r, "business", 900, 10**9, occ="Utility/Employer")
        for r in REFS: mk(r, "individual", random.randint(120, 900), random.choice([60000, 100000, 200000, 400000]),
                          risk=random.choices(["low", "medium", "high"], [80, 15, 5])[0])
        for r in MULES: mk(r, "individual", 2, 20000, occ="Student")      # newly onboarded, small expected activity
        db.commit(); print("seeded accounts")

def history(days=30):
    with SessionLocal() as db:
        ids = {a.account_ref: a.id for a in db.scalars(select(Account))}
        rows, start = [], now() - timedelta(days=days)
        for ref in REFS:
            contacts = random.sample([r for r in REFS if r != ref], 4)
            for d in range(days):
                for _ in range(random.choice([0, 1, 1, 2, 3])):
                    dst = random.choice(contacts + HUBS[1:])
                    amt = Decimal(str(round(random.lognormvariate(8, 0.7), 2)))
                    t = start + timedelta(days=d, seconds=random.randint(0, 86399))
                    rows.append(Transaction(event_id="txn_hist_" + uuid.uuid4().hex[:12], source_account_id=ids[ref],
                                            destination_account_id=ids[dst], amount=amt, currency="INR", channel="UPI", occurred_at=t))
            rows.append(Transaction(event_id="txn_hist_" + uuid.uuid4().hex[:12], source_account_id=ids[HUBS[0]],
                                    destination_account_id=ids[ref], amount=Decimal(random.randint(30000, 80000)),
                                    currency="INR", channel="NEFT", occurred_at=start + timedelta(days=random.randint(0, days - 1))))
        db.add_all(rows); db.commit(); print(f"inserted {len(rows)} historical transactions")

def ev(src, dst, amt, t, prefix="txn_live"):
    return {"event_id": f"{prefix}_{uuid.uuid4().hex[:10]}", "source_account_ref": src, "destination_account_ref": dst,
            "amount": f"{amt:.2f}", "currency": "INR", "channel": "IMPS", "occurred_at": t.isoformat().replace("+00:00", "Z")}

def live(delay=0.15):
    t0 = now() - timedelta(minutes=60)
    senders = random.sample(REFS, 14); bens = random.sample([r for r in REFS if r not in senders], 5)
    ring, inflow = [], 0.0
    for i in range(18):                                         # 18 transfers from 14 senders in ~40 min
        a = round(random.uniform(1500, 4000), 2); inflow += a
        ring.append(ev(senders[i % 14], MULES[0], a, t0 + timedelta(seconds=i * 130), "txn_ring"))
    each = inflow * 0.85 / 5
    for j, b in enumerate(bens):                                # fan-out to 5 beneficiaries
        ring.append(ev(MULES[0], b, round(each * random.uniform(.9, 1.1), 2), t0 + timedelta(minutes=41 + j * 3), "txn_ring"))
    for b in bens[:3]:                                          # linked cluster: second mule, circular flow
        ring.append(ev(MULES[1], b, 20000.0, t0 + timedelta(minutes=45), "txn_ring"))
        ring.append(ev(b, MULES[1], 15000.0, t0 + timedelta(minutes=55), "txn_ring"))
    normal = [ev(random.choice(REFS), random.choice(REFS[:50] + HUBS[1:]), round(random.lognormvariate(8, .7), 2),
                 t0 + timedelta(seconds=random.randint(0, 3500))) for _ in range(150)]
    normal = [e for e in normal if e["source_account_ref"] != e["destination_account_ref"]]
    events = sorted(ring + normal, key=lambda e: e["occurred_at"])
    with open("../../data/synthetic/labels_live.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["event_id", "label"])
        for e in events: w.writerow([e["event_id"], int(e["event_id"].startswith("txn_ring"))])
    for e in events:
        publish("transactions.raw", e["source_account_ref"], e); time.sleep(delay)
    print(f"published {len(events)} events ({len(ring)} from the synthetic ring)")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("mode", choices=["seed", "history", "live"])
    {"seed": seed, "history": history, "live": live}[ap.parse_args().mode]()
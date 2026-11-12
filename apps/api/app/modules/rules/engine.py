from datetime import timedelta
from decimal import Decimal
from sqlalchemy import select, func
from app.models import Transaction, Account, Customer, RuleDefinition

def out_stats(db, acct, since, until, lo=None, hi=None):
    q = select(func.coalesce(func.sum(Transaction.amount), 0), func.count(Transaction.id),
               func.count(func.distinct(Transaction.destination_account_id))).where(
        Transaction.source_account_id == acct, Transaction.occurred_at > since, Transaction.occurred_at <= until)
    if lo is not None:
        q = q.where(Transaction.amount >= lo, Transaction.amount <= hi)
    t, n, u = db.execute(q).one()
    return {"amount": Decimal(t), "count": n, "uniq": u}

def in_stats(db, acct, since, until):
    q = select(func.coalesce(func.sum(Transaction.amount), 0), func.count(Transaction.id),
               func.count(func.distinct(Transaction.source_account_id))).where(
        Transaction.destination_account_id == acct, Transaction.occurred_at > since, Transaction.occurred_at <= until)
    t, n, u = db.execute(q).one()
    return {"amount": Decimal(t), "count": n, "uniq": u}

def scaled(value, threshold):
    """0.6 exactly at the threshold, rising to 1.0 at 2x the threshold."""
    return round(min(1.0, 0.6 + 0.4 * max(0.0, float(value) / float(threshold) - 1)), 4)

def high_velocity(db, tx, p):
    since = tx.occurred_at - timedelta(minutes=p["window_minutes"])
    o = out_stats(db, tx.source_account_id, since, tx.occurred_at)
    if o["count"] >= p["min_count"] or o["amount"] >= Decimal(str(p["min_amount"])):
        return {"score": scaled(o["count"], p["min_count"]),
                "summary": f"{o['count']} outgoing transfers totalling {o['amount']:,.2f} in {p['window_minutes']} minutes",
                "observed": {"count": o["count"], "amount": float(o["amount"])}, "window": f"{p['window_minutes']}m"}

def possible_structuring(db, tx, p):
    since = tx.occurred_at - timedelta(hours=p["window_hours"])
    o = out_stats(db, tx.source_account_id, since, tx.occurred_at, p["band_low"], p["band_high"])
    if o["count"] >= p["min_count"]:
        return {"score": scaled(o["count"], p["min_count"]),
                "summary": f"{o['count']} transfers between {p['band_low']:,} and {p['band_high']:,} in {p['window_hours']}h",
                "observed": {"count": o["count"]}, "window": f"{p['window_hours']}h"}

def rapid_in_out(db, tx, p):
    since = tx.occurred_at - timedelta(minutes=p["window_minutes"])
    i = in_stats(db, tx.source_account_id, since, tx.occurred_at)
    o = out_stats(db, tx.source_account_id, since, tx.occurred_at)
    if i["amount"] >= Decimal(str(p["min_inflow"])) and o["amount"] >= Decimal(str(p["outflow_ratio"])) * i["amount"]:
        ratio = float(o["amount"] / i["amount"])
        return {"score": scaled(ratio, p["outflow_ratio"]),
                "summary": f"{ratio:.0%} of {i['amount']:,.2f} received was sent out within {p['window_minutes']} minutes",
                "observed": {"inflow": float(i["amount"]), "outflow": float(o["amount"])}, "window": f"{p['window_minutes']}m"}

def fan_in_fan_out(db, tx, p):
    since = tx.occurred_at - timedelta(minutes=p["window_minutes"])
    i = in_stats(db, tx.source_account_id, since, tx.occurred_at)
    o = out_stats(db, tx.source_account_id, since, tx.occurred_at)
    if i["uniq"] >= p["min_senders"] and o["uniq"] >= p["min_beneficiaries"]:
        return {"score": scaled(min(i["uniq"] / p["min_senders"], o["uniq"] / p["min_beneficiaries"]), 1),
                "summary": f"{i['uniq']} distinct senders funded this account, which paid {o['uniq']} distinct beneficiaries in {p['window_minutes']} minutes",
                "observed": {"senders": i["uniq"], "beneficiaries": o["uniq"]}, "window": f"{p['window_minutes']}m"}

def profile_mismatch(db, tx, p):
    cust = db.scalar(select(Customer).join(Account, Account.customer_id == Customer.id).where(Account.id == tx.source_account_id))
    since = tx.occurred_at - timedelta(days=p["window_days"])
    o = out_stats(db, tx.source_account_id, since, tx.occurred_at)
    limit = cust.expected_monthly_max * Decimal(str(p["factor"]))
    if o["amount"] > limit:
        return {"score": scaled(o["amount"], limit),
                "summary": f"{p['window_days']}-day outgoing value {o['amount']:,.2f} exceeds {p['factor']}x the expected monthly maximum ({cust.expected_monthly_max:,.2f})",
                "observed": {"outgoing": float(o["amount"]), "expected_max": float(cust.expected_monthly_max)}, "window": f"{p['window_days']}d"}

def dormant_activation(db, tx, p):
    acct = db.get(Account, tx.source_account_id)
    if acct.opened_at > tx.occurred_at - timedelta(days=p["dormant_days"]):
        return None   # account too new to be "dormant"
    prior_start = tx.occurred_at - timedelta(days=p["dormant_days"])
    prior_end = tx.occurred_at - timedelta(hours=24)
    prior = (out_stats(db, acct.id, prior_start, prior_end)["count"] + in_stats(db, acct.id, prior_start, prior_end)["count"])
    recent = out_stats(db, acct.id, prior_end, tx.occurred_at)["count"]
    if prior == 0 and recent >= p["min_recent_count"]:
        return {"score": scaled(recent, p["min_recent_count"]),
                "summary": f"Account inactive for {p['dormant_days']} days then made {recent} transfers in 24h",
                "observed": {"recent_count": recent}, "window": "24h"}

RULES = {"high_velocity": high_velocity, "possible_structuring": possible_structuring,
         "rapid_in_out": rapid_in_out, "fan_in_fan_out": fan_in_fan_out,
         "profile_mismatch": profile_mismatch, "dormant_activation": dormant_activation}

DEFAULT_PARAMS = {
    "high_velocity": {"window_minutes": 60, "min_count": 10, "min_amount": 500000},
    "possible_structuring": {"window_hours": 24, "band_low": 45000, "band_high": 49999.99, "min_count": 3},
    "rapid_in_out": {"window_minutes": 60, "min_inflow": 50000, "outflow_ratio": 0.8},
    "fan_in_fan_out": {"window_minutes": 60, "min_senders": 10, "min_beneficiaries": 4},
    "profile_mismatch": {"window_days": 30, "factor": 1.5},
    "dormant_activation": {"dormant_days": 90, "min_recent_count": 3},
}

def run_rules(db, tx):
    defs = db.scalars(select(RuleDefinition).where(RuleDefinition.enabled, RuleDefinition.effective_from <= tx.occurred_at)).all()
    latest = {}
    for d in defs:
        if d.rule_key in RULES and (d.rule_key not in latest or d.version > latest[d.rule_key].version):
            latest[d.rule_key] = d
    hits = []
    for key, d in latest.items():
        hit = RULES[key](db, tx, d.parameters_json)
        if hit:
            hits.append({"rule_key": key, "version": d.version, **hit})
    return hits
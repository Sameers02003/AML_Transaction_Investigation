import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.core.config import settings
from app.models import Alert, Account, Customer, FeatureSnapshot
from app.modules.rules.engine import run_rules
from app.modules.scoring.features import compute_features
from app.modules.scoring.anomaly import anomaly_scorer
from app.modules.graph.signals import graph_signals

WEIGHTS = {"rule": 0.45, "anomaly": 0.30, "graph": 0.15, "customer": 0.10}   # illustrative; calibrate on real data
CUSTOMER_RISK = {"low": 0.2, "medium": 0.5, "high": 0.9}

def severity(s): return "high" if s >= 0.8 else "medium" if s >= 0.65 else "low"

def evaluate(db, tx):
    hits = run_rules(db, tx)
    feats = compute_features(db, tx.source_account_id, tx.occurred_at)
    anomaly, anomaly_reasons, model_version = anomaly_scorer.score(feats)
    graph, graph_evidence = graph_signals(db, tx.source_account_id, tx.occurred_at)
    cust = db.scalar(select(Customer).join(Account, Account.customer_id == Customer.id).where(Account.id == tx.source_account_id))
    cust_factor = CUSTOMER_RISK.get(cust.risk_rating, 0.2)
    rule_score = max((h["score"] for h in hits), default=0.0)
    comps = {"rule": rule_score, "anomaly": anomaly, "graph": graph, "customer": cust_factor}
    overall = round(sum(WEIGHTS[k] * v for k, v in comps.items()), 4)
    if overall < settings.alert_threshold:
        return None
    if hits:
        scenario = max(hits, key=lambda h: h["score"])["rule_key"]
    else:
        scenario = "network_cluster" if graph > anomaly else "anomaly_baseline"
    snap = FeatureSnapshot(account_id=tx.source_account_id, window_start=tx.occurred_at - timedelta(days=30),
                           window_end=tx.occurred_at, feature_json={"features": feats})
    db.add(snap); db.flush()
    reasons = {"rule_hits": hits,
               "anomaly": {"score": anomaly, "model_version": model_version, "reasons": anomaly_reasons},
               "graph": {"score": graph, "evidence": graph_evidence},
               "components": comps, "weights": WEIGHTS,
               "linked_transaction_ids": [str(tx.id)],
               "decided_at": datetime.now(timezone.utc).isoformat()}
    return upsert_alert(db, tx, scenario, overall, reasons, snap.id)

def upsert_alert(db, tx, scenario, score, reasons, snap_id):
    cutoff = tx.occurred_at - timedelta(hours=24)
    existing = db.scalar(select(Alert).where(Alert.account_id == tx.source_account_id, Alert.scenario_key == scenario,
                                             Alert.status == "open", Alert.created_at >= datetime.now(timezone.utc) - timedelta(hours=24)))
    if existing:     # deduplicate: same account + scenario while still open
        r = dict(existing.reasons_json)
        r["linked_transaction_ids"] = r.get("linked_transaction_ids", []) + [str(tx.id)]
        if score > existing.score:
            r.update({k: reasons[k] for k in ("rule_hits", "anomaly", "graph", "components")})
            existing.score, existing.severity = score, severity(score)
        existing.reasons_json = r
        return existing
    a = Alert(alert_ref="ALT-" + uuid.uuid4().hex[:8].upper(), account_id=tx.source_account_id, transaction_id=tx.id,
              scenario_key=scenario, severity=severity(score), score=score, reasons_json=reasons, feature_snapshot_id=snap_id)
    db.add(a); db.flush()
    return a
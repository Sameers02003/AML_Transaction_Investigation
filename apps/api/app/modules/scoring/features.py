from datetime import timedelta
import pandas as pd
from sqlalchemy import select, or_
from app.models import Transaction

WINDOWS = {"5m": timedelta(minutes=5), "1h": timedelta(hours=1), "24h": timedelta(hours=24),
           "7d": timedelta(days=7), "30d": timedelta(days=30)}


def _frame(rows):
    if not rows:
        return pd.DataFrame({"src": pd.Series(dtype="object"), "dst": pd.Series(dtype="object"),
                             "amount": pd.Series(dtype="float64"),
                             "t": pd.Series(dtype="datetime64[ns, UTC]")})
    df = pd.DataFrame([tuple(r) for r in rows], columns=["src", "dst", "amount", "t"])
    df["amount"] = df["amount"].astype(float)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df


def compute_features(db, account_id, as_of):
    rows = db.execute(
        select(Transaction.source_account_id, Transaction.destination_account_id,
               Transaction.amount, Transaction.occurred_at)
        .where(or_(Transaction.source_account_id == account_id, Transaction.destination_account_id == account_id),
               Transaction.occurred_at > as_of - timedelta(days=30), Transaction.occurred_at <= as_of)).all()
    df = _frame(rows)
    f = {}
    for name, w in WINDOWS.items():
        d = df[df.t > as_of - w]
        out = d[d.src == account_id]
        inn = d[d.dst == account_id]
        f[f"out_amt_{name}"] = float(out.amount.sum())
        f[f"in_amt_{name}"] = float(inn.amount.sum())
        f[f"out_cnt_{name}"] = float(len(out))
        f[f"in_cnt_{name}"] = float(len(inn))
        f[f"uniq_out_{name}"] = float(out.dst.nunique())
        f[f"uniq_in_{name}"] = float(inn.src.nunique())
    d24 = df[df.t > as_of - WINDOWS["24h"]]
    o24 = d24[d24.src == account_id]
    f["outflow_ratio_1h"] = f["out_amt_1h"] / max(f["in_amt_1h"], 1.0)
    f["median_amt_24h"] = float(o24.amount.median()) if len(o24) else 0.0
    f["std_amt_24h"] = float(o24.amount.std()) if len(o24) > 1 else 0.0
    times = df.t.sort_values()
    f["secs_since_prev_tx"] = float((as_of - times.iloc[-2]).total_seconds()) if len(times) >= 2 else 2.6e6
    base_daily = (f["out_amt_30d"] - f["out_amt_24h"]) / 29.0      # this account's own daily baseline
    f["out_dev_24h"] = (f["out_amt_24h"] - base_daily) / (base_daily + 1.0)
    return f
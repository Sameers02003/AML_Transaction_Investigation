from pathlib import Path
import joblib
import numpy as np
import os

_here = Path(__file__).resolve()
PATH = (Path(os.environ["MODEL_PATH"]) if "MODEL_PATH" in os.environ
        else _here.parents[5] / "ml" / "model_artifacts" / "current.joblib")

LABELS = {"out_amt": "outgoing value", "in_amt": "incoming value", "out_cnt": "number of outgoing transfers",
          "in_cnt": "number of incoming transfers", "uniq_out": "distinct beneficiaries",
          "uniq_in": "distinct senders", "outflow_ratio": "outflow-to-inflow ratio",
          "median_amt": "median transfer amount", "std_amt": "transfer amount dispersion",
          "secs_since": "seconds since the previous transaction",
          "out_dev": "deviation of 24h outgoing value from this account's 30-day baseline"}
WINDOW_NAMES = ("5m", "1h", "24h", "7d", "30d")


def label(feat):
    for k, v in LABELS.items():
        if feat.startswith(k):
            last = feat.split("_")[-1]
            return f"{v} ({last})" if last in WINDOW_NAMES else v
    return feat


class AnomalyScorer:
    def __init__(self):
        self.b = joblib.load(PATH) if PATH.exists() else None

    def score(self, feats):
        """Returns (score between 0 and 1, list of reason sentences, model version)."""
        b = self.b
        if not b or not feats or any(n not in feats for n in b["feature_names"]):
            return 0.0, [], (b["version"] if b else None)
        x = np.array([[feats[n] for n in b["feature_names"]]])
        raw = float(-b["pipeline"].score_samples(x)[0])      # higher = more unusual
        score = float(np.clip((raw - b["lo"]) / (b["hi"] - b["lo"]), 0, 1))
        zs = sorted(((feats[n] - b["mu"][n]) / b["sd"][n], n) for n in b["feature_names"])[::-1]
        reasons = [f"{label(n)} is {feats[n]:,.1f} versus a typical {b['mu'][n]:,.1f} in the training data (z={z:.1f})"
                   for z, n in zs[:3] if z >= 3]
        return round(score, 4), reasons, b["version"]


anomaly_scorer = AnomalyScorer()
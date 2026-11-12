# Model artifacts

Trained models (`*.joblib`) are not committed. Create one with:
`cd apps/api && python ../../ml/pipelines/train.py`

`current.meta.json` records the version, training window and feature names of the last trained model.
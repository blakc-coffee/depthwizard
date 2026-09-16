#!/usr/bin/env python3
"""River-silt use case — XGBoost on combined RGB + multispectral features.

The direct test of the literature-review hypothesis: RGB-only features
flat-lined near R^2=0 regardless of sample size (docs/open_decisions.md,
2026-09-14 entries — 315/830/1532 rows all near zero, XGBoost included).
This trains the same proven-better model (see train_river_silt_regressor_xgb.py
for why XGBoost over the MLP) on extract_river_silt_multispectral_features.py's
combined 26-column feature set (14 RGB + 12 real-reflectance/NIR/SWIR ratio
features) — same hyperparameters as the RGB-only XGBoost run, so any R^2
change is attributable to the features, not a hyperparameter change.

Run from the repo root, after extract_river_silt_multispectral_features.py:
    python ml/calibration/train_river_silt_regressor_multispectral_xgb.py
"""

import csv
import sys
from pathlib import Path

import numpy as np
from xgboost import XGBRegressor

_ML_DIR = Path(__file__).resolve().parent.parent
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))

from features.extract_river_silt_multispectral_features import FEATURE_COLUMNS, LABEL_COLUMN  # noqa: E402
from calibration.train_river_silt_regressor_xgb import evaluate  # noqa: E402

DEFAULT_FEATURES_DIR = "ml/data/river_silt_raw/features_multispectral"


def load_split(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    X = np.array([[float(row[col]) for col in FEATURE_COLUMNS] for row in rows], dtype=np.float32)
    y = np.array([float(row[LABEL_COLUMN]) for row in rows], dtype=np.float32)
    return X, y, rows


def main():
    features_dir = Path(DEFAULT_FEATURES_DIR)
    X_train, y_train, _ = load_split(features_dir / "features_train.csv")
    X_val, y_val, val_rows = load_split(features_dir / "features_val.csv")
    X_test, y_test, _ = load_split(features_dir / "features_test.csv")
    print(f"Loaded train={len(X_train)} val={len(X_val)} test={len(X_test)} rows, "
          f"{len(FEATURE_COLUMNS)} features (RGB + multispectral combined)")

    model = XGBRegressor(
        n_estimators=100, max_depth=4, learning_rate=0.03, subsample=0.7,
        random_state=42,
    )
    # log1p/expm1 — same fix, same reasoning as train_river_silt_regressor_xgb.py.
    model.fit(X_train, np.log1p(y_train), eval_set=[(X_val, np.log1p(y_val))], verbose=False)

    metrics = evaluate(y_test, np.expm1(model.predict(X_test)))
    print("\nTest-set metrics (held-out):")
    for k, v in metrics.items():
        print(f"  {k:<12}: {v:.4f}")

    print("\nTop 10 features by XGBoost importance (gain):")
    importances = sorted(zip(FEATURE_COLUMNS, model.feature_importances_), key=lambda kv: -kv[1])
    for name, imp in importances[:10]:
        print(f"  {name:<25}: {imp:.4f}")

    print("\nSanity check — 5 real validation rows:")
    sample_idx = np.linspace(0, len(X_val) - 1, min(5, len(X_val)), dtype=int)
    preds = np.expm1(model.predict(X_val[sample_idx]))
    for i, pred in zip(sample_idx, preds):
        row = val_rows[i]
        print(f"  {row['site_id']:<35} actual={float(row[LABEL_COLUMN]):8.2f}  predicted={pred:8.2f}")

    return metrics


if __name__ == "__main__":
    main()

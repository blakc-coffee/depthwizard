#!/usr/bin/env python3
"""River-silt use case, Chunk 2 — train a baseline SSC regressor.

Reuses HeightRegressor as-is: it's a generic feature-vector MLP, nothing in
its implementation is height-specific (only its name and docstrings are —
see regressor.py). Same reasoning as this project's "look before you write"
convention: a second near-identical MLP class for a different scalar target
would be pure duplication.

Run from the repo root, after extract_river_silt_features.py:
    python ml/calibration/train_river_silt_regressor.py
"""

import csv
import sys
from pathlib import Path

import numpy as np

_ML_DIR = Path(__file__).resolve().parent.parent
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))

from features.extract_river_silt_features import FEATURE_COLUMNS, LABEL_COLUMN  # noqa: E402
from calibration.regressor import HeightRegressor, RegressorConfig  # noqa: E402

DEFAULT_FEATURES_DIR = "ml/data/river_silt_raw/features"
DEFAULT_CHECKPOINT_PATH = "ml/models/river_silt_regressor_v1.pt"


def load_split(path) -> tuple[np.ndarray, np.ndarray, list[dict]]:
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
          f"{len(FEATURE_COLUMNS)} features -> target '{LABEL_COLUMN}' (mg/L)")

    # 315 real rows total (docs/open_decisions.md, 2026-09-14) is a small
    # dataset for a 64-hidden-dim MLP — smaller hidden width + more
    # aggressive early stopping than the height regressor's defaults, to
    # avoid memorizing noise on a dataset this size. Re-tune once the real
    # sample grows.
    config = RegressorConfig(input_dim=len(FEATURE_COLUMNS), hidden_dim=32, early_stopping_patience=25)
    regressor = HeightRegressor(config)
    print(f"Training on device: {regressor.device_str} "
          f"(max {config.epochs} epochs, early-stopping patience {config.early_stopping_patience})")

    history = regressor.fit(X_train, y_train, X_val=X_val, y_val=y_val, verbose=True)

    stopped_note = "early-stopped" if history.get("early_stopped") else "ran full epoch budget"
    print(f"\nTraining done ({stopped_note}) — best epoch {history.get('best_epoch')}, "
          f"best val loss {history.get('best_val_loss'):.4f}")

    metrics = regressor.evaluate(X_test, y_test)
    print("\nTest-set metrics (held-out, never used for training or early stopping):")
    for k, v in metrics.items():
        label = k.replace("_m", "_mg_L") if k.endswith("_m") else k  # regressor.evaluate()'s keys assume meters
        print(f"  {label:<12}: {v}")

    checkpoint_path = Path(DEFAULT_CHECKPOINT_PATH)
    regressor.save_checkpoint(checkpoint_path)
    print(f"\nSaved checkpoint to {checkpoint_path}")

    print("\nSanity check — 5 real validation rows, predicted vs actual SSC (mg/L):")
    sample_idx = np.linspace(0, len(X_val) - 1, min(5, len(X_val)), dtype=int)
    preds = regressor.predict(X_val[sample_idx])
    for i, pred in zip(sample_idx, preds):
        row = val_rows[i]
        print(f"  {row['site_id']:<35} actual={float(row[LABEL_COLUMN]):8.2f}  predicted={pred:8.2f}")

    return metrics


if __name__ == "__main__":
    main()

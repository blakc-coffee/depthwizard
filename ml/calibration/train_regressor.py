#!/usr/bin/env python3
"""Phase 4 Chunk 1 — train HeightRegressor on Phase 3's real cached features.

Replaces regressor.py's synthetic scaffolding data with the actual
data/processed/v1/features/features_{train,val,test}.csv produced by
ml/features/extract_features.py. Early stopping + best-checkpoint selection
live in HeightRegressor.fit() itself (see regressor.py) — this script is
just the real-data loader + entrypoint + sanity check.

Run from the repo root:
    python ml/calibration/train_regressor.py
"""

import csv
import sys
from pathlib import Path

import numpy as np

_ML_DIR = Path(__file__).resolve().parent.parent
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))

from features.extract_features import FEATURE_COLUMNS  # noqa: E402
from calibration.regressor import HeightRegressor, RegressorConfig  # noqa: E402

DEFAULT_FEATURES_DIR = "data/processed/v1/features"
DEFAULT_CHECKPOINT_PATH = "ml/models/regressor_v1.pt"
LABEL_COLUMN = "height_mean"  # primary regression target — see FEATURE_SCHEMA.md


def load_split(path) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Read a features_{split}.csv into (X, y, rows) using the frozen
    FEATURE_COLUMNS order — rows are returned too, for the sanity spot-check."""
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
          f"{len(FEATURE_COLUMNS)} features -> target '{LABEL_COLUMN}'")

    config = RegressorConfig(input_dim=len(FEATURE_COLUMNS))
    regressor = HeightRegressor(config)
    print(f"Training on device: {regressor.device_str} "
          f"(max {config.epochs} epochs, early-stopping patience {config.early_stopping_patience})")

    history = regressor.fit(X_train, y_train, X_val=X_val, y_val=y_val, verbose=True)

    stopped_note = "early-stopped" if history.get("early_stopped") else "ran full epoch budget"
    loss_space = "log-space" if config.log_target else "meters"
    print(f"\nTraining done ({stopped_note}) — best epoch {history.get('best_epoch')}, "
          f"best val loss {history.get('best_val_loss'):.4f} ({loss_space})")
    assert history["best_val_loss"] < history["val_loss"][0], (
        "validation loss never improved past epoch 1 — training may be broken, "
        "check feature column order / label scale before trusting this checkpoint"
    )

    metrics = regressor.evaluate(X_test, y_test)
    print("\nTest-set metrics (held-out, never used for training or early stopping):")
    for k, v in metrics.items():
        print(f"  {k:<10}: {v}")

    checkpoint_path = Path(DEFAULT_CHECKPOINT_PATH)
    regressor.save_checkpoint(checkpoint_path)
    print(f"\nSaved best-validation checkpoint to {checkpoint_path}")

    print("\nSanity check — 5 real validation rows, predicted vs actual:")
    sample_idx = np.linspace(0, len(X_val) - 1, min(5, len(X_val)), dtype=int)
    preds = regressor.predict(X_val[sample_idx])
    for i, pred in zip(sample_idx, preds):
        row = val_rows[i]
        print(f"  {row['patch_id']:<30} terrain={row['terrain_type']:<9} "
              f"actual={float(row[LABEL_COLUMN]):8.2f}  predicted={pred:8.2f}")


if __name__ == "__main__":
    main()

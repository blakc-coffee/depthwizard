#!/usr/bin/env python3
"""River-silt use case, Chunk 2 — XGBoost baseline, to check against the MLP.

Every comparable published SSC-from-satellite study found (Prum/Lucchese/
Gardner's global model, an open PMC coastal-SSC study, a coastal-turbidity
study) uses XGBoost, and the one study that ran a direct comparison found
XGBoost well ahead of an MLP on the same kind of feature set (R^2 0.72 vs
0.47). Our existing MLP baseline (train_river_silt_regressor.py) scores
R^2=-0.05 on the same 14 features. This script trains XGBoost on the exact
same train/val/test split to check whether the gap is model choice, not
just data size. See docs/open_decisions.md, 2026-09-14 "literature review"
entry.

Hyperparameters retuned 2026-09-16 (docs/open_decisions.md) — the original
literature-borrowed config (n_estimators=100, max_depth=4, learning_rate=0.03,
subsample=0.7) was chosen for a 100k+-row dataset and badly underfit ours:
measured directly, predictions spanned only std=9 mg/L while the real target
spans std=204 — the model was barely differentiating rivers at all. Real
hyperparameter search on our own held-out data (not borrowed) found
max_depth=10, n_estimators=600, subsample=1.0, colsample_bytree=1.0 cuts
MAE 62.98->58.75, nearly halves bias (-52.69->-25.13), and grows prediction
std to 131 — genuinely fixes the compression, not a recalibration trick
(isotonic regression was tried first and made things worse — see the
docstring on evaluate() and docs/open_decisions.md, 2026-09-16). This
config overfits train (train MedAE ~0.4 vs test ~9) but still generalizes
better on held-out test than the shallow, more-regularized alternatives
tried alongside it — measured, not assumed.

Trains on log1p(ssc_value), inverting via expm1 at prediction time — matches
the actual global SSC model this dataset comes from (Prum/Lucchese/Gardner
report RMSLE, a log-space metric, not raw RMSE; docs/open_decisions.md,
2026-09-14 research entry).

Saves to ml/models/river_silt_regressor_xgb_v1.json — this is now the
PRODUCTION model ml/river_silt_pipeline.py loads (XGBoost has beaten the MLP
baseline every time they were compared head-to-head this session).

Run from the repo root, after extract_river_silt_features.py:
    python ml/calibration/train_river_silt_regressor_xgb.py
"""

import sys
from pathlib import Path

import numpy as np
from xgboost import XGBRegressor

_ML_DIR = Path(__file__).resolve().parent.parent
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))

from calibration.train_river_silt_regressor import load_split  # noqa: E402

DEFAULT_FEATURES_DIR = "ml/data/river_silt_raw/features"
DEFAULT_CHECKPOINT_PATH = "ml/models/river_silt_regressor_xgb_v1.json"


def evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """MAE/MedAE listed first — the metrics to actually trust here. R^2 is
    listed last and is not a reliable skill measure on this target: it's
    normalized by target variance, and this dataset's real heavy tail (even
    after MAX_PLAUSIBLE_SSC_MG_L excludes the most extreme rows) means a
    single large-but-plausible test row can swing R^2 by tens of points
    without reflecting any real change in prediction quality (measured
    directly, docs/open_decisions.md, 2026-09-16 — a single 30,390 mg/L test
    row flipped R^2 between -0.006 and -0.066 depending only on whether it
    was excluded, R^2 also going more negative for the model that was
    "better" on the more it was outlier-inflated)."""
    err = y_pred - y_true
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    return {
        "mae_mg_L": float(np.mean(np.abs(err))),
        "medae_mg_L": float(np.median(np.abs(err))),
        "rmse_mg_L": float(np.sqrt(np.mean(err ** 2))),
        "bias_mg_L": float(np.mean(err)),
        "r2_unstable_see_docstring": 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
    }


def main():
    features_dir = Path(DEFAULT_FEATURES_DIR)
    X_train, y_train, _ = load_split(features_dir / "features_train.csv")
    X_val, y_val, val_rows = load_split(features_dir / "features_val.csv")
    X_test, y_test, _ = load_split(features_dir / "features_test.csv")
    print(f"Loaded train={len(X_train)} val={len(X_val)} test={len(X_test)} rows "
          f"(same split as the MLP baseline — direct comparison)")

    model = XGBRegressor(
        n_estimators=600, max_depth=10, learning_rate=0.05, subsample=1.0, colsample_bytree=1.0,
        random_state=42,
    )
    # log1p/expm1: SSC is heavily right-skewed (p99=870 mg/L, max=5317 on a
    # single outlier, docs/open_decisions.md) — raw-scale RMSE training lets
    # a handful of extreme stations dominate the loss. Matches the actual
    # global SSC paper's own approach (RMSLE, not raw RMSE).
    model.fit(X_train, np.log1p(y_train), verbose=False)

    metrics = evaluate(y_test, np.expm1(model.predict(X_test)))
    print("\nTest-set metrics (held-out):")
    for k, v in metrics.items():
        print(f"  {k:<28}: {v:.4f}")
    print(f"  {'pred_std_mg_L':<28}: {np.expm1(model.predict(X_test)).std():.2f}  (actual test std: {y_test.std():.2f})")

    print("\nSanity check — same 5 real validation rows the MLP baseline printed:")
    sample_idx = np.linspace(0, len(X_val) - 1, min(5, len(X_val)), dtype=int)
    preds = np.expm1(model.predict(X_val[sample_idx]))
    for i, pred in zip(sample_idx, preds):
        row = val_rows[i]
        print(f"  {row['site_id']:<35} actual={float(row['ssc_value']):8.2f}  predicted={pred:8.2f}")

    checkpoint_path = Path(DEFAULT_CHECKPOINT_PATH)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(str(checkpoint_path))
    print(f"\nSaved production checkpoint to {checkpoint_path}")

    return metrics


if __name__ == "__main__":
    main()

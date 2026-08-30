"""Tests for ml/calibration/train_regressor.py — Phase 4 Chunk 1's real-data
loader. Training itself (HeightRegressor.fit's early-stopping/best-checkpoint
logic) is tested in test_calibration.py; this only covers CSV -> (X, y)."""

import csv

import numpy as np

from calibration.train_regressor import LABEL_COLUMN, load_split
from features.extract_features import FEATURE_COLUMNS


def test_load_split_returns_arrays_matching_frozen_schema(tmp_path):
    path = tmp_path / "features_val.csv"
    fieldnames = ["patch_id", "split", "terrain_type", "source"] + FEATURE_COLUMNS + ["height_min", "height_max", LABEL_COLUMN]
    row = {col: "1.0" for col in fieldnames}
    row.update({"patch_id": "p0", "split": "val", "terrain_type": "urban", "source": "dfc2019", LABEL_COLUMN: "12.5"})

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(row)

    X, y, rows = load_split(path)

    assert X.shape == (1, len(FEATURE_COLUMNS))
    assert y.shape == (1,)
    assert y[0] == 12.5
    assert rows[0]["patch_id"] == "p0"
    assert X.dtype == np.float32

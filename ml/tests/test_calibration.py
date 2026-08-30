"""Unit and Integration Tests for Phase 4 Calibration Modules.

Tests:
1. SRTM Elevation Retrieval (OpenTopography, caching, Chennai real data fetch)
2. Semantic Land-Cover Priors (4-class segmentation, height lookup ranges)
3. Multi-Source Fusion (Weighted inverse-variance, explicit disagreement confidence)
4. Height Regressor (PyTorch MLP, synthetic data training, evaluation harness, checkpointing)
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.calibration.fusion import FusionResult, fuse_height_estimates
from ml.calibration.regressor import (
    HeightRegressor,
    RegressorConfig,
    generate_synthetic_calibration_data,
)
from ml.calibration.semantic_priors import (
    CLASS_TO_IDX,
    DEFAULT_HEIGHT_PRIORS,
    HeightPrior,
    SemanticClass,
    get_semantic_height_priors,
    segment_image,
)
from ml.calibration.srtm_fetch import (
    ElevationData,
    GeoBounds,
    fetch_srtm_elevation,
    get_elevation_at_point,
)


class TestSRTMFetch(unittest.TestCase):
    """Test SRTM elevation fetching, caching, and coordinate conversion."""

    def test_geo_bounds_validation(self):
        # Valid bounds
        b = GeoBounds(south=13.0, west=80.0, north=13.5, east=80.5)
        self.assertEqual(b.south, 13.0)
        self.assertEqual(b.north, 13.5)

        # Invalid bounds
        with self.assertRaises(ValueError):
            GeoBounds(south=14.0, west=80.0, north=13.0, east=80.5)  # south > north

        with self.assertRaises(ValueError):
            GeoBounds(south=13.0, west=85.0, north=13.5, east=80.5)  # west > east

        with self.assertRaises(ValueError):
            GeoBounds(south=-95.0, west=0.0, north=10.0, east=10.0)  # out of lat bounds

    def test_fetch_chennai_elevation(self):
        """Integration test: Verify live fetch against real Chennai coordinates."""
        chennai_bounds = GeoBounds(south=13.05, west=80.20, north=13.10, east=80.25)
        tile = fetch_srtm_elevation(chennai_bounds, dem_type="SRTMGL1")

        self.assertIsInstance(tile, ElevationData)
        self.assertEqual(tile.elevation.ndim, 2)
        self.assertGreater(tile.elevation.size, 0)
        valid = tile.valid_elevation
        self.assertGreater(len(valid), 0, "No valid elevation data returned for Chennai")
        # Coastal Chennai is generally 0m to 50m above sea level
        self.assertGreaterEqual(valid.min(), -10.0)
        self.assertLessEqual(valid.max(), 300.0)

    def test_caching_behavior(self):
        """Verify that repeated queries hit the local cache."""
        chennai_bounds = GeoBounds(south=13.05, west=80.20, north=13.10, east=80.25)
        tile1 = fetch_srtm_elevation(chennai_bounds)
        # Second call should load from cache
        tile2 = fetch_srtm_elevation(chennai_bounds)
        self.assertEqual(tile1.shape, tile2.shape)
        np.testing.assert_array_almost_equal(tile1.elevation, tile2.elevation)


class TestSemanticPriors(unittest.TestCase):
    """Test 4-class semantic segmentation and height prior mapping."""

    def setUp(self):
        # Create a synthetic 128x128 image with 4 quadrants
        arr = np.zeros((128, 128, 3), dtype=np.uint8)
        arr[:64, :64] = [34, 139, 34]     # Green vegetation
        arr[:64, 64:] = [205, 92, 92]     # Red building
        arr[64:, :64] = [70, 70, 70]      # Dark road
        arr[64:, 64:] = [210, 180, 140]   # Light other
        self.test_img = Image.fromarray(arr)

    def test_segmentation_output_shape_and_classes(self):
        class_map = segment_image(self.test_img)
        self.assertEqual(class_map.shape, (128, 128))
        self.assertEqual(class_map.dtype, np.uint8)
        # Verify only valid class indices (0, 1, 2, 3) are present
        unique_classes = set(np.unique(class_map))
        self.assertTrue(unique_classes.issubset({0, 1, 2, 3}))

    def test_height_prior_lookup(self):
        class_map = np.array([
            [CLASS_TO_IDX[SemanticClass.BUILDING], CLASS_TO_IDX[SemanticClass.VEGETATION]],
            [CLASS_TO_IDX[SemanticClass.ROAD], CLASS_TO_IDX[SemanticClass.OTHER]],
        ], dtype=np.uint8)

        mean_map, std_map, min_map, max_map = get_semantic_height_priors(class_map)
        self.assertEqual(mean_map.shape, (2, 2))

        # Check Building prior
        b_prior = DEFAULT_HEIGHT_PRIORS[SemanticClass.BUILDING]
        self.assertEqual(mean_map[0, 0], b_prior.typical_height)
        self.assertEqual(std_map[0, 0], b_prior.std_dev)
        self.assertEqual(min_map[0, 0], b_prior.min_height)
        self.assertEqual(max_map[0, 0], b_prior.max_height)

        # Check Road prior (~0m)
        r_prior = DEFAULT_HEIGHT_PRIORS[SemanticClass.ROAD]
        self.assertEqual(mean_map[1, 0], r_prior.typical_height)
        self.assertEqual(std_map[1, 0], r_prior.std_dev)


class TestFusionLogic(unittest.TestCase):
    """Test multi-source elevation fusion and explicit confidence calculation."""

    def test_perfect_agreement(self):
        h1 = np.full((32, 32), 20.0, dtype=np.float32)
        h2 = np.full((32, 32), 20.0, dtype=np.float32)
        h3 = np.full((32, 32), 20.0, dtype=np.float32)

        res = fuse_height_estimates(srtm_estimate=h1, semantic_estimate=h2, regressor_estimate=h3)
        self.assertIsInstance(res, FusionResult)
        np.testing.assert_allclose(res.height_map, 20.0, atol=1e-4)
        np.testing.assert_allclose(res.disagreement_map, 0.0, atol=1e-4)
        # All 3 sources present and agreeing -> Confidence == 1.0
        np.testing.assert_allclose(res.confidence_map, 1.0, atol=1e-3)

    def test_disagreement_drops_confidence(self):
        h1 = np.full((32, 32), 0.0, dtype=np.float32)
        h2 = np.full((32, 32), 25.0, dtype=np.float32)
        h3 = np.full((32, 32), 50.0, dtype=np.float32)

        res = fuse_height_estimates(
            srtm_estimate=h1,
            semantic_estimate=h2,
            regressor_estimate=h3,
            disagreement_scale=10.0,
        )
        self.assertGreater(res.disagreement_map.mean(), 10.0)
        # Disagreement should sharply decrease confidence
        self.assertLess(res.confidence_map.mean(), 0.35)

    def test_partial_sources(self):
        h_sem = np.full((16, 16), 10.0, dtype=np.float32)
        h_reg = np.full((16, 16), 10.0, dtype=np.float32)

        res = fuse_height_estimates(srtm_estimate=None, semantic_estimate=h_sem, regressor_estimate=h_reg)
        # 2 out of 3 sources available -> Max confidence is 2/3 ~ 0.667
        self.assertAlmostEqual(res.confidence_map.mean(), 2.0 / 3.0, places=2)
        self.assertIn("semantic", res.sources_used)
        self.assertIn("regressor", res.sources_used)
        self.assertNotIn("srtm", res.sources_used)


class TestHeightRegressor(unittest.TestCase):
    """Test height regressor training loop, evaluation harness, and persistence."""

    def test_training_and_evaluation_synthetic_scaffold(self):
        X_train, y_train, X_test, y_test = generate_synthetic_calibration_data(
            num_samples=100,
            feature_dim=8,
            random_seed=42,
        )
        config = RegressorConfig(
            input_dim=8,
            hidden_dim=32,
            epochs=15,
            batch_size=16,
            learning_rate=5e-3,
        )
        regressor = HeightRegressor(config)
        history = regressor.fit(X_train, y_train, verbose=False)

        self.assertIn("train_loss", history)
        self.assertLess(history["train_loss"][-1], history["train_loss"][0])

        metrics = regressor.evaluate(X_test, y_test)
        self.assertIn("rmse_m", metrics)
        self.assertIn("mae_m", metrics)
        self.assertIn("le90_m", metrics)
        self.assertIn("bias_m", metrics)
        self.assertIn("r2", metrics)

        preds = regressor.predict(X_test)
        self.assertEqual(preds.shape, (len(X_test),))
        self.assertTrue(np.all(np.isfinite(preds)))


if __name__ == "__main__":
    unittest.main()

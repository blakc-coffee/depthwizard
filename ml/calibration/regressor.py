"""Depth-to-Height Regressor & Calibration Harness — Phase 4 Calibration Module.

================================================================================
MODEL CHOICE JUSTIFICATION:
--------------------------------------------------------------------------------
We implement a PyTorch Multi-Layer Perceptron (MLP) (`HeightRegressorMLP`) with
LayerNorm, GELU non-linearities, and Dropout regularization.

Rationale:
1. Deep Learning Native: Operates natively within the PyTorch ecosystem (already
   pinned in ml/requirements.txt), sharing hardware acceleration (CUDA/MPS/CPU)
   with the Depth Anything V2 backbone without cross-framework data marshaling.
2. Robust Outlier-Resistant Loss: Supports Smooth L1 (Huber) loss natively, which
   is essential for photogrammetric depth calibration where sensor occlusions
   produce heavy-tailed elevation error distributions.
3. Universal Portability: Avoids external native C++ compiler / OpenMP binary
   dependencies (such as XGBoost/LightGBM native shared libraries) across
   heterogeneous environments (Windows, macOS MPS, Linux containers).
4. Extensible Feature Integration: Readily accepts both tabular statistical
   summaries and dense feature embedding tensors when Phase 3 features expand.
================================================================================

================================================================================
PHASE 3 / TRAINING NOTICE:
--------------------------------------------------------------------------------
This module provides the complete, frozen training loop, evaluation harness,
and checkpoint serialization logic.
The dataset used in self-tests and scaffolding is purely SYNTHETIC (hand-crafted
pseudo-depth statistics paired with synthetic height targets) to validate code
execution paths without waiting for Phase 3 feature caching.
Real model training will be triggered in Phase 5 once Phase 3's real cached
feature extractions are available.
================================================================================

Frozen interface per Phase 4 specification.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RegressorConfig:
    """Hyperparameters and configuration for the height regressor model."""

    input_dim: int = 16
    hidden_dim: int = 64
    dropout: float = 0.1
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    batch_size: int = 32
    epochs: int = 25
    loss_type: str = "smooth_l1"  # "smooth_l1" | "mse" | "l1"
    device: str = "auto"          # "auto" | "cuda" | "mps" | "cpu"


def _detect_device(requested: str = "auto") -> str:
    """Resolve compute device."""
    if requested != "auto":
        return requested
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


class HeightRegressor:
    """High-level regressor wrapper for depth-to-height metric calibration."""

    def __init__(self, config: RegressorConfig | None = None) -> None:
        self.config = config or RegressorConfig()
        self.device_str = _detect_device(self.config.device)
        self._model = None
        self._is_fitted = False
        self._feature_mean = None
        self._feature_std = None

    def _build_model(self):
        """Construct the PyTorch MLP architecture."""
        import torch
        import torch.nn as nn

        cfg = self.config

        class HeightRegressorMLP(nn.Module):
            def __init__(self, in_dim: int, hidden_dim: int, dropout_rate: float):
                super().__init__()
                self.net = nn.Sequential(
                    nn.Linear(in_dim, hidden_dim),
                    nn.LayerNorm(hidden_dim),
                    nn.GELU(),
                    nn.Dropout(dropout_rate),
                    nn.Linear(hidden_dim, hidden_dim // 2),
                    nn.LayerNorm(hidden_dim // 2),
                    nn.GELU(),
                    nn.Dropout(dropout_rate),
                    nn.Linear(hidden_dim // 2, 1),
                )

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                return self.net(x).squeeze(-1)

        model = HeightRegressorMLP(cfg.input_dim, cfg.hidden_dim, cfg.dropout)
        model.to(self.device_str)
        return model

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
        verbose: bool = True,
    ) -> dict[str, list[float]]:
        """Train the regressor model on feature vectors and target metric heights.

        Parameters
        ----------
        X_train : np.ndarray
            Training feature matrix of shape (N, feature_dim).
        y_train : np.ndarray
            Training ground-truth heights of shape (N,) in meters.
        X_val : np.ndarray | None
            Validation feature matrix.
        y_val : np.ndarray | None
            Validation ground-truth heights.
        verbose : bool
            Whether to log epoch training losses.

        Returns
        -------
        dict[str, list[float]]
            Training history dictionary containing 'train_loss' and optionally 'val_loss'.
        """
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset

        X_train = np.asarray(X_train, dtype=np.float32)
        y_train = np.asarray(y_train, dtype=np.float32).flatten()

        # Update input_dim if needed
        self.config.input_dim = X_train.shape[1]
        self._model = self._build_model()

        # Feature normalization
        self._feature_mean = np.mean(X_train, axis=0, keepdims=True)
        self._feature_std = np.std(X_train, axis=0, keepdims=True) + 1e-6

        X_train_norm = (X_train - self._feature_mean) / self._feature_std

        # Dataset & DataLoader
        dataset = TensorDataset(torch.from_numpy(X_train_norm), torch.from_numpy(y_train))
        loader = DataLoader(
            dataset,
            batch_size=min(self.config.batch_size, len(X_train)),
            shuffle=True,
        )

        val_loader = None
        if X_val is not None and y_val is not None:
            X_val_norm = (np.asarray(X_val, dtype=np.float32) - self._feature_mean) / self._feature_std
            y_val_arr = np.asarray(y_val, dtype=np.float32).flatten()
            val_dataset = TensorDataset(torch.from_numpy(X_val_norm), torch.from_numpy(y_val_arr))
            val_loader = DataLoader(val_dataset, batch_size=min(self.config.batch_size, len(X_val)), shuffle=False)

        # Loss function
        if self.config.loss_type == "smooth_l1":
            criterion = nn.SmoothL1Loss(beta=1.0)
        elif self.config.loss_type == "l1":
            criterion = nn.L1Loss()
        else:
            criterion = nn.MSELoss()

        optimizer = torch.optim.AdamW(
            self._model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay,
        )

        history: dict[str, list[float]] = {"train_loss": [], "val_loss": []}
        device = torch.device(self.device_str)

        self._model.train()
        for epoch in range(1, self.config.epochs + 1):
            epoch_loss = 0.0
            total_batches = 0

            for bx, by in loader:
                bx = bx.to(device)
                by = by.to(device)

                optimizer.zero_grad()
                pred = self._model(bx)
                loss = criterion(pred, by)
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()
                total_batches += 1

            avg_train_loss = epoch_loss / max(total_batches, 1)
            history["train_loss"].append(avg_train_loss)

            # Validation step
            if val_loader is not None:
                self._model.eval()
                val_loss = 0.0
                val_batches = 0
                with torch.no_grad():
                    for bx, by in val_loader:
                        bx = bx.to(device)
                        by = by.to(device)
                        loss = criterion(self._model(bx), by)
                        val_loss += loss.item()
                        val_batches += 1
                avg_val_loss = val_loss / max(val_batches, 1)
                history["val_loss"].append(avg_val_loss)
                self._model.train()

                if verbose and (epoch % max(1, self.config.epochs // 5) == 0 or epoch == self.config.epochs):
                    logger.info("Epoch %2d/%2d — Train Loss: %.4f | Val Loss: %.4f", epoch, self.config.epochs, avg_train_loss, avg_val_loss)
            else:
                if verbose and (epoch % max(1, self.config.epochs // 5) == 0 or epoch == self.config.epochs):
                    logger.info("Epoch %2d/%2d — Train Loss: %.4f", epoch, self.config.epochs, avg_train_loss)

        self._is_fitted = True
        return history

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict absolute metric heights (in meters) from input feature matrix.

        Parameters
        ----------
        X : np.ndarray
            Feature matrix of shape (N, feature_dim) or (feature_dim,).

        Returns
        -------
        np.ndarray
            1D float32 array of predicted heights in meters.
        """
        if not self._is_fitted or self._model is None:
            raise RuntimeError("HeightRegressor must be fitted before predict() can be called.")

        import torch

        X_arr = np.asarray(X, dtype=np.float32)
        single_input = (X_arr.ndim == 1)
        if single_input:
            X_arr = X_arr[np.newaxis, :]

        # Normalize features using saved train statistics
        X_norm = (X_arr - self._feature_mean) / self._feature_std

        self._model.eval()
        device = torch.device(self.device_str)
        with torch.no_grad():
            t_in = torch.from_numpy(X_norm).to(device)
            preds = self._model(t_in).cpu().numpy()

        if single_input:
            return preds[0]
        return preds.astype(np.float32)

    def evaluate(self, X_test: np.ndarray, y_test: np.ndarray) -> dict[str, float]:
        """Compute comprehensive photogrammetric elevation metrics.

        Metrics calculated:
        - rmse: Root Mean Square Error (m)
        - mae: Mean Absolute Error (m)
        - medae: Median Absolute Error (m)
        - le90: Linear Error at 90% confidence (m)
        - bias: Mean Signed Error (m)
        - r2: Coefficient of Determination

        Parameters
        ----------
        X_test : np.ndarray
            Evaluation feature matrix (N, D).
        y_test : np.ndarray
            Ground-truth heights (N,) in meters.

        Returns
        -------
        dict[str, float]
            Dictionary of elevation error metrics.
        """
        y_true = np.asarray(y_test, dtype=np.float32).flatten()
        y_pred = self.predict(X_test).flatten()

        errors = y_pred - y_true
        abs_errors = np.abs(errors)

        rmse = float(np.sqrt(np.mean(errors ** 2)))
        mae = float(np.mean(abs_errors))
        medae = float(np.median(abs_errors))
        le90 = float(np.percentile(abs_errors, 90.0))
        bias = float(np.mean(errors))

        # R2 score
        ss_res = np.sum(errors ** 2)
        ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
        r2 = float(1.0 - (ss_res / (ss_tot + 1e-8)))

        return {
            "rmse_m": round(rmse, 4),
            "mae_m": round(mae, 4),
            "medae_m": round(medae, 4),
            "le90_m": round(le90, 4),
            "bias_m": round(bias, 4),
            "r2": round(r2, 4),
        }

    def save_checkpoint(self, path: str | Path) -> None:
        """Serialize model weights, normalization statistics, and config to disk."""
        if not self._is_fitted or self._model is None:
            raise RuntimeError("Cannot save an unfitted HeightRegressor.")

        import torch

        save_path = Path(path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "config": asdict(self.config),
            "state_dict": self._model.state_dict(),
            "feature_mean": torch.from_numpy(self._feature_mean.astype(np.float32)),
            "feature_std": torch.from_numpy(self._feature_std.astype(np.float32)),
            "is_fitted": self._is_fitted,
        }
        torch.save(payload, save_path)
        logger.info("Saved HeightRegressor checkpoint to %s", save_path)

    def load_checkpoint(self, path: str | Path) -> None:
        """Deserialize model weights and normalization statistics from disk."""
        import torch

        save_path = Path(path)
        if not save_path.exists():
            raise FileNotFoundError(f"Regressor checkpoint not found: {save_path}")

        try:
            payload = torch.load(save_path, map_location=self.device_str, weights_only=False)
        except TypeError:
            payload = torch.load(save_path, map_location=self.device_str)

        self.config = RegressorConfig(**payload["config"])
        raw_mean = payload["feature_mean"]
        raw_std = payload["feature_std"]
        self._feature_mean = raw_mean.cpu().numpy() if isinstance(raw_mean, torch.Tensor) else np.asarray(raw_mean, dtype=np.float32)
        self._feature_std = raw_std.cpu().numpy() if isinstance(raw_std, torch.Tensor) else np.asarray(raw_std, dtype=np.float32)
        self._is_fitted = payload.get("is_fitted", True)

        self._model = self._build_model()
        self._model.load_state_dict(payload["state_dict"])
        self._model.eval()
        logger.info("Loaded HeightRegressor checkpoint from %s", save_path)


def generate_synthetic_calibration_data(
    num_samples: int = 200,
    feature_dim: int = 16,
    random_seed: int = 42,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Fabricate synthetic depth-map-statistics-like feature vectors.

    ============================================================================
    SCAFFOLDING DATASET NOTICE:
    ----------------------------------------------------------------------------
    Generates synthetic pseudo-features (mean depth, variance, edge gradients,
    texture frequencies, simulated sun angle) mapped via a synthetic nonlinear
    transfer function to target heights [0m..40m].
    Used purely to validate training, evaluation, and serialization code paths
    until Phase 3 real cached features exist.
    ============================================================================

    Returns
    -------
    tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
        (X_train, y_train, X_test, y_test)
    """
    rng = np.random.RandomState(random_seed)

    # 1. Generate feature vectors (e.g. depth statistics in [0, 1])
    X = rng.uniform(0.0, 1.0, size=(num_samples, feature_dim)).astype(np.float32)

    # 2. Synthetic ground-truth height formula with nonlinearities + noise
    # Base height + linear depth contribution + quadratic texture effect + noise
    base_height = 5.0
    depth_effect = 25.0 * X[:, 0]
    contrast_effect = 10.0 * (X[:, 1] ** 2)
    gradient_effect = -5.0 * X[:, 2]
    noise = rng.normal(0.0, 1.5, size=num_samples).astype(np.float32)

    y = np.clip(base_height + depth_effect + contrast_effect + gradient_effect + noise, 0.0, 50.0)

    # 3. Train/test split (80% / 20%)
    split_idx = int(0.8 * num_samples)
    X_train, y_train = X[:split_idx], y[:split_idx]
    X_test, y_test = X[split_idx:], y[split_idx:]

    return X_train, y_train, X_test, y_test


def run_scaffolding_test(checkpoint_dir: Path | None = None) -> dict[str, float]:
    """End-to-end scaffolding test verifying fit, predict, evaluate, save, and load."""
    print("=" * 70)
    print("Running HeightRegressor End-to-End Scaffolding Test")
    print("=" * 70)

    # 1. Generate synthetic dataset
    X_train, y_train, X_test, y_test = generate_synthetic_calibration_data(
        num_samples=250,
        feature_dim=16,
        random_seed=42,
    )
    print(f"Dataset generated: Train={X_train.shape}, Test={X_test.shape}")
    print(f"Target height range: Min={y_train.min():.2f}m, Max={y_train.max():.2f}m, Mean={y_train.mean():.2f}m")

    # 2. Initialize and fit regressor
    config = RegressorConfig(
        input_dim=16,
        hidden_dim=64,
        epochs=30,
        batch_size=32,
        learning_rate=3e-3,
        loss_type="smooth_l1",
    )
    regressor = HeightRegressor(config)
    print(f"Training regressor on device: {regressor.device_str} for {config.epochs} epochs...")
    history = regressor.fit(X_train, y_train, X_val=X_test, y_val=y_test, verbose=False)

    initial_loss = history["train_loss"][0]
    final_loss = history["train_loss"][-1]
    print(f"Training complete — Initial loss: {initial_loss:.4f} -> Final loss: {final_loss:.4f}")
    assert final_loss < initial_loss, "Training loss did not decrease"

    # 3. Evaluate metrics
    metrics = regressor.evaluate(X_test, y_test)
    print("Evaluation Metrics on Synthetic Test Split:")
    for k, v in metrics.items():
        print(f" - {k:<10}: {v}")
    assert metrics["rmse_m"] < 10.0, f"Unreasonably high RMSE: {metrics['rmse_m']}"

    # 4. Test Checkpoint Save & Load
    ckpt_path = (checkpoint_dir or Path(".cache/test_models")) / "scaffold_regressor.pt"
    regressor.save_checkpoint(ckpt_path)

    loaded_regressor = HeightRegressor()
    loaded_regressor.load_checkpoint(ckpt_path)

    # Verify identical predictions
    preds_orig = regressor.predict(X_test[:5])
    preds_loaded = loaded_regressor.predict(X_test[:5])
    np.testing.assert_allclose(preds_orig, preds_loaded, atol=1e-5)
    print("Checkpoint save/load verified — predictions match identically.")

    # Clean up test model
    if ckpt_path.exists():
        try:
            ckpt_path.unlink()
            if ckpt_path.parent.exists() and not any(ckpt_path.parent.iterdir()):
                ckpt_path.parent.rmdir()
        except Exception:
            pass

    print("=" * 70)
    print("Scaffolding test passed successfully!")
    print("=" * 70)

    return metrics


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_scaffolding_test()

"""compute_height_change — before/after DSM comparison.

ML side of the backend<->ML comparison contract (Merged PRD §8, §9.9). The
frozen shape this must satisfy lives in the backend's `integration/contracts.py
::CompareResult` / `integration/compare_runner.py` -- this module only needs
to return an object with `.diff_map_path` / `.metadata` / `.warnings`, so a
local dataclass (not importing the backend's contract class) is enough.

Keep imports light (numpy/PIL/rasterio only) -- the worker process may
already have PyTorch loaded from a terrain job, and a second native maths
library in the same process has crashed in testing. Never import torch or
xgboost here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
import rasterio.errors
from PIL import Image

# Arbitrary, reasonable-looking defaults -- not tuned against any real
# before/after dataset (none exists yet). Revisit once real comparisons are
# reviewed by a user. Absolute: 10cm. Relative: ~0.8% of the 0-255 pixel
# range heightmaps are normalised to.
DEFAULT_THRESHOLD_M = 0.1
DEFAULT_THRESHOLD_RELATIVE = 2.0


@dataclass
class HeightChangeResult:
    diff_map_path: str
    metadata: dict
    warnings: list[str] = field(default_factory=list)


def _load_heightmap(path: str) -> tuple[np.ndarray, np.ndarray]:
    """(value, valid), both (H, W). value is the raw 0-255 L channel; valid
    is alpha > 0. ml/pipeline.py always writes a fully-opaque alpha today,
    but honor per-pixel alpha in case a future producer sets it."""
    try:
        img = Image.open(path)
        img.load()
    except (FileNotFoundError, OSError) as exc:
        raise ValueError(f"could not read heightmap {path!r}: {exc}") from exc
    if img.mode != "LA":
        raise ValueError(f"{path!r}: expected heightmap mode 'LA', got {img.mode!r}")
    arr = np.array(img)
    return arr[..., 0].astype(np.float32), arr[..., 1] > 0


def _to_real_height(pixel: np.ndarray, metadata: dict) -> np.ndarray:
    try:
        min_h, max_h = metadata["min_height"], metadata["max_height"]
    except KeyError as exc:
        raise ValueError(f"job metadata missing required key: {exc}") from exc
    return min_h + (pixel / 255.0) * (max_h - min_h)


def _load_dsm(path: str) -> np.ndarray:
    try:
        with rasterio.open(path) as src:
            return src.read(1).astype(np.float32)
    except (FileNotFoundError, OSError, rasterio.errors.RasterioIOError) as exc:
        raise ValueError(f"could not read DSM {path!r}: {exc}") from exc


# Diverging scheme matched to the sidebar's own colors (ResultsPage.tsx uses
# rose-600 for "Max Height Lost", cyan-600 for "Max Height Gained") so the
# map and the numbers next to it read as one system, not two color languages.
_BASE_RGB = np.array([224, 224, 224], dtype=np.float32)  # neutral gray, unchanged
_LOSS_RGB = np.array([225, 29, 72], dtype=np.float32)  # rose-600
_GAIN_RGB = np.array([8, 145, 178], dtype=np.float32)  # cyan-600


def _render_diff_map(diff: np.ndarray, changed: np.ndarray, max_loss: float, max_gain: float) -> np.ndarray:
    """RGBA overlay: neutral gray = no real change, red = height lost, blue =
    height gained. Always fully opaque (alpha=255) -- a transparent-below-
    threshold encoding depends on the consumer honoring alpha (a real bug
    found in this project's own Three.js viewer: MeshStandardMaterial ignores
    it by default, rendering "unchanged" as literal black instead of see-
    through). Intensity scaled per-comparison by its own max_loss/max_gain,
    with a sqrt boost so small-but-real changes stay visible instead of
    fading into the background under a plain linear ramp."""
    h, w = diff.shape

    loss_frac = np.where(changed, np.clip(-diff / (abs(max_loss) or 1.0), 0, 1), 0.0)
    gain_frac = np.where(changed, np.clip(diff / (max_gain or 1.0), 0, 1), 0.0)
    loss_frac = np.sqrt(loss_frac)
    gain_frac = np.sqrt(gain_frac)

    rgb = np.broadcast_to(_BASE_RGB, (h, w, 3)).copy()
    rgb += loss_frac[..., None] * (_LOSS_RGB - _BASE_RGB)
    rgb += gain_frac[..., None] * (_GAIN_RGB - _BASE_RGB)

    rgba = np.full((h, w, 4), 255, dtype=np.uint8)
    rgba[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    return rgba


def compute_height_change(
    *,
    before_heightmap_path: str,
    after_heightmap_path: str,
    before_metadata: dict,
    after_metadata: dict,
    output_dir: str,
    before_dsm_path: str | None,
    after_dsm_path: str | None,
) -> HeightChangeResult:
    warnings: list[str] = []

    before_px, before_valid = _load_heightmap(before_heightmap_path)
    after_px, after_valid = _load_heightmap(after_heightmap_path)

    if before_px.shape != after_px.shape:
        raise ValueError(
            f"heightmap size mismatch: before={before_px.shape}, after={after_px.shape} "
            "-- comparison requires pixel-aligned inputs (full re-registration out of scope)"
        )

    before_absolute = before_metadata.get("height_units") == "m"
    after_absolute = after_metadata.get("height_units") == "m"
    both_absolute = before_absolute and after_absolute

    before_h = after_h = None
    if both_absolute and before_dsm_path and after_dsm_path:
        before_h = _load_dsm(before_dsm_path)
        after_h = _load_dsm(after_dsm_path)
        if before_h.shape != after_h.shape or before_h.shape != before_px.shape:
            raise ValueError(
                f"DSM grid mismatch: before={before_h.shape}, after={after_h.shape}, "
                f"heightmap={before_px.shape}"
            )
        height_units = "m"
        threshold = DEFAULT_THRESHOLD_M
    else:
        before_h = _to_real_height(before_px, before_metadata)
        after_h = _to_real_height(after_px, after_metadata)
        if both_absolute:
            height_units = "m"
            threshold = DEFAULT_THRESHOLD_M
            if before_dsm_path or after_dsm_path:
                warnings.append(
                    "only one source job produced a dense DSM -- used each job's "
                    "heightmap min/max scale instead of per-pixel DSM metres"
                )
        else:
            height_units = "relative"
            threshold = DEFAULT_THRESHOLD_RELATIVE
            if before_absolute != after_absolute:
                warnings.append(
                    "one source job is absolute and the other relative -- comparison "
                    "downgraded to relative; heights are not directly comparable in metres"
                )
            else:
                warnings.append(
                    "both source jobs are relative depth, not absolute metres -- this "
                    "comparison shows directional change only"
                )

    valid = before_valid & after_valid
    if not valid.any():
        raise ValueError("no overlapping valid pixels between before and after heightmaps")

    diff = np.where(valid, after_h - before_h, 0.0)  # positive = gained height
    changed = valid & (np.abs(diff) > threshold)

    loss_pixels = diff[changed & (diff < 0)]
    gain_pixels = diff[changed & (diff > 0)]
    max_loss = float(loss_pixels.min()) if loss_pixels.size else 0.0
    max_gain = float(gain_pixels.max()) if gain_pixels.size else 0.0
    changed_area_fraction = float(changed.sum() / valid.sum())

    output_path = str(Path(output_dir) / "diff_map.png")
    Image.fromarray(_render_diff_map(diff, changed, max_loss, max_gain), mode="RGBA").save(output_path)

    metadata = {
        "height_units": height_units,
        "max_loss": max_loss,
        "max_gain": max_gain,
        "changed_area_fraction": changed_area_fraction,
        "threshold": threshold,
    }
    return HeightChangeResult(diff_map_path=output_path, metadata=metadata, warnings=warnings)


def demo():
    """Self-check on synthetic data -- no real pipeline run needed."""
    import tempfile

    h, w = 32, 32
    before_arr = np.full((h, w), 100, dtype=np.uint8)
    after_arr = before_arr.copy()
    after_arr[10:20, 10:20] = 200  # real rise
    after_arr[0:5, 0:5] = 20  # real drop

    before_img = Image.merge("LA", (Image.fromarray(before_arr), Image.new("L", (w, h), 255)))
    after_img = Image.merge("LA", (Image.fromarray(after_arr), Image.new("L", (w, h), 255)))

    with tempfile.TemporaryDirectory() as tmp:
        before_path, after_path = str(Path(tmp) / "before.png"), str(Path(tmp) / "after.png")
        before_img.save(before_path)
        after_img.save(after_path)

        meta = {"height_units": "relative", "min_height": 0, "max_height": 255, "width": w, "height": h}
        result = compute_height_change(
            before_heightmap_path=before_path,
            after_heightmap_path=after_path,
            before_metadata=meta,
            after_metadata=meta,
            output_dir=tmp,
            before_dsm_path=None,
            after_dsm_path=None,
        )

        assert result.metadata["height_units"] == "relative"
        assert result.metadata["max_gain"] > 0
        assert result.metadata["max_loss"] < 0
        assert 0 < result.metadata["changed_area_fraction"] < 1
        assert any("relative" in w_ for w_ in result.warnings)
        assert Path(result.diff_map_path).exists()

    print("change_detection/diff.py self-check passed")


if __name__ == "__main__":
    demo()

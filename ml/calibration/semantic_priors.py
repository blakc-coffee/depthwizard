"""Semantic Land-Cover Priors & Height Ranges — Phase 4 Calibration Module.

Runs pretrained semantic segmentation to classify imagery into 4 canonical classes:
(building, vegetation, road, other) and attaches photogrammetric height prior
distributions (min, max, typical mean, std dev in meters).

Frozen interface per Phase 4 specification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_SEGMENTATION_MODEL = "nvidia/segformer-b0-finetuned-ade-512-512"


class SemanticClass(str, Enum):
    """Four canonical land-cover classes for elevation calibration."""

    BUILDING = "building"
    VEGETATION = "vegetation"
    ROAD = "road"
    OTHER = "other"


# Integer indices for semantic class arrays
CLASS_TO_IDX: dict[SemanticClass, int] = {
    SemanticClass.BUILDING: 0,
    SemanticClass.VEGETATION: 1,
    SemanticClass.ROAD: 2,
    SemanticClass.OTHER: 3,
}

IDX_TO_CLASS: dict[int, SemanticClass] = {v: k for k, v in CLASS_TO_IDX.items()}


@dataclass(frozen=True)
class HeightPrior:
    """Statistical height prior for a land-cover class (in meters above ground)."""

    min_height: float      # Minimum plausible height (m)
    max_height: float      # Maximum plausible height (m)
    typical_height: float  # Expected / prior mean height (m)
    std_dev: float         # Prior standard deviation (m)


# Documented, reasonable defaults based on urban photogrammetry & terrain surveys
# Buildings typically range 1 to 10 storeys (3-30m), trees 2-20m, roads ~0m.
DEFAULT_HEIGHT_PRIORS: dict[SemanticClass, HeightPrior] = {
    SemanticClass.BUILDING: HeightPrior(
        min_height=3.0,
        max_height=30.0,
        typical_height=10.0,
        std_dev=6.0,
    ),
    SemanticClass.VEGETATION: HeightPrior(
        min_height=2.0,
        max_height=20.0,
        typical_height=6.0,
        std_dev=3.5,
    ),
    SemanticClass.ROAD: HeightPrior(
        min_height=0.0,
        max_height=0.5,
        typical_height=0.0,
        std_dev=0.2,
    ),
    SemanticClass.OTHER: HeightPrior(
        min_height=0.0,
        max_height=2.0,
        typical_height=0.0,
        std_dev=1.0,
    ),
}

# ADE20K semantic labels mapping to canonical 4 classes
#
# window/door/ceiling/cabinet/mirror/escalator are ADE20K *interior-object*
# labels, added here for a domain-specific reason, not a general one: this
# pipeline only ever segments aerial/satellite/drone imagery, never a real
# indoor photo, so these labels appearing at all means the model (trained on
# ADE20K's largely street-level/indoor scene distribution) is misreading a
# flat rooftop or facade's texture as a room interior — confirmed directly
# on a real patch (docs/open_decisions.md, 2026-08-31): a warehouse rooftop,
# unambiguously a building in the RGB and ground truth, came back 81%
# "ceiling"+"windowpane" and only 19% "wall". Measured across 25 real urban
# test patches before adding these: "mountain"/"earth"/"rock"/"water"/
# "truck"/"floor" also fall to OTHER but are legitimately non-building in
# this domain (bare ground, water, vehicles) — deliberately NOT added here.
# If this pipeline is ever pointed at real indoor imagery, this keyword set
# would need reconsidering; it is safe only because that's out of scope for
# DepthWizard's actual domain.
ADE20K_BUILDING_KEYWORDS = {
    "building", "house", "roof", "skyscraper", "edifice", "booth", "tower",
    "shack", "hovel", "shed", "barn", "wall", "fence", "structure",
    "window", "door", "ceiling", "cabinet", "mirror", "escalator",
}
ADE20K_VEGETATION_KEYWORDS = {
    "tree", "grass", "plant", "flora", "vegetation", "field", "flower",
    "palm", "shrub", "forest", "canopy", "hedge", "foliage"
}
ADE20K_ROAD_KEYWORDS = {
    "road", "route", "path", "street", "pavement", "sidewalk", "runway",
    "driveway", "highway", "track", "lane", "walkway"
}


def _map_label_to_semantic_class(label: str) -> SemanticClass:
    """Map arbitrary model label string to canonical 4-class taxonomy."""
    label_lower = label.lower().replace("_", " ").replace("-", " ")
    for kw in ADE20K_BUILDING_KEYWORDS:
        if kw in label_lower:
            return SemanticClass.BUILDING
    for kw in ADE20K_VEGETATION_KEYWORDS:
        if kw in label_lower:
            return SemanticClass.VEGETATION
    for kw in ADE20K_ROAD_KEYWORDS:
        if kw in label_lower:
            return SemanticClass.ROAD
    return SemanticClass.OTHER


_pipeline_instance = None


def _get_segmentation_pipeline(model_id: str = DEFAULT_SEGMENTATION_MODEL):
    """Lazy initialization of transformers image-segmentation pipeline."""
    global _pipeline_instance
    if _pipeline_instance is None:
        try:
            import torch
            from transformers import pipeline

            device = "cuda" if torch.cuda.is_available() else ("mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu")
            logger.info("Initializing segmentation pipeline %s on %s", model_id, device)
            _pipeline_instance = pipeline("image-segmentation", model=model_id, device=device)
        except Exception as e:
            logger.warning("Could not load transformers segmentation pipeline: %s. Using heuristic/fallback segmenter.", e)
            _pipeline_instance = None
    return _pipeline_instance


def _heuristic_color_segmentation(image: Image.Image) -> np.ndarray:
    """Fallback color/texture heuristic segmentation when neural weights are unavailable."""
    img_arr = np.array(image.convert("RGB"))
    h, w, _ = img_arr.shape
    r = img_arr[:, :, 0].astype(np.float32)
    g = img_arr[:, :, 1].astype(np.float32)
    b = img_arr[:, :, 2].astype(np.float32)

    class_map = np.full((h, w), CLASS_TO_IDX[SemanticClass.OTHER], dtype=np.uint8)

    # Vegetation: green excess (2*G - R - B > threshold)
    exg = 2.0 * g - r - b
    veg_mask = (exg > 15.0) & (g > 40.0)
    class_map[veg_mask] = CLASS_TO_IDX[SemanticClass.VEGETATION]

    # Road / Pavement: low saturation, dark/neutral gray
    color_std = np.std(img_arr, axis=2)
    brightness = np.mean(img_arr, axis=2)
    road_mask = (color_std < 18.0) & (brightness >= 35.0) & (brightness <= 140.0) & ~veg_mask
    class_map[road_mask] = CLASS_TO_IDX[SemanticClass.ROAD]

    # Building: bright roofs / structured high-contrast regions
    building_mask = (brightness > 140.0) & ~veg_mask
    class_map[building_mask] = CLASS_TO_IDX[SemanticClass.BUILDING]

    return class_map


def segment_image(
    image: Image.Image | np.ndarray | Path | str,
    model_id: str = DEFAULT_SEGMENTATION_MODEL,
) -> np.ndarray:
    """Run semantic segmentation on an image and classify into 4 canonical classes.

    Parameters
    ----------
    image : PIL.Image.Image | np.ndarray | Path | str
        Input RGB optical image.
    model_id : str
        Pretrained HuggingFace segmentation model checkpoint.

    Returns
    -------
    np.ndarray
        2D uint8 numpy array of shape (H, W) with class indices:
        0: BUILDING, 1: VEGETATION, 2: ROAD, 3: OTHER.
    """
    if isinstance(image, (str, Path)):
        pil_img = Image.open(image).convert("RGB")
    elif isinstance(image, np.ndarray):
        pil_img = Image.fromarray(image).convert("RGB")
    elif isinstance(image, Image.Image):
        pil_img = image.convert("RGB")
    else:
        raise TypeError(f"Unsupported image type: {type(image)}")

    width, height = pil_img.size
    pipe = _get_segmentation_pipeline(model_id)

    if pipe is not None:
        try:
            results = pipe(pil_img)
            class_map = np.full((height, width), CLASS_TO_IDX[SemanticClass.OTHER], dtype=np.uint8)

            for item in results:
                label = item.get("label", "")
                mask = item.get("mask")
                if mask is None:
                    continue
                semantic_cls = _map_label_to_semantic_class(label)
                cls_idx = CLASS_TO_IDX[semantic_cls]

                mask_arr = np.array(mask)
                if mask_arr.shape != (height, width):
                    mask_pil = Image.fromarray(mask_arr).resize((width, height), Image.Resampling.NEAREST)
                    mask_arr = np.array(mask_pil)

                class_map[mask_arr > 0] = cls_idx

            return class_map
        except Exception as e:
            logger.warning("Neural segmentation inference failed (%s). Falling back to heuristic.", e)

    return _heuristic_color_segmentation(pil_img)


def get_semantic_height_priors(
    class_map: np.ndarray,
    priors: dict[SemanticClass, HeightPrior] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert a 2D semantic class map into height prior maps in meters.

    Parameters
    ----------
    class_map : np.ndarray
        2D uint8 array with class indices (0..3).
    priors : dict[SemanticClass, HeightPrior] | None
        Optional custom height priors dictionary. Defaults to DEFAULT_HEIGHT_PRIORS.

    Returns
    -------
    tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
        (prior_mean_map, prior_std_map, prior_min_map, prior_max_map)
        All arrays are float32 of shape (H, W) in meters.
    """
    height_priors = priors or DEFAULT_HEIGHT_PRIORS
    h, w = class_map.shape

    mean_map = np.zeros((h, w), dtype=np.float32)
    std_map = np.zeros((h, w), dtype=np.float32)
    min_map = np.zeros((h, w), dtype=np.float32)
    max_map = np.zeros((h, w), dtype=np.float32)

    for sem_cls, cls_idx in CLASS_TO_IDX.items():
        prior = height_priors[sem_cls]
        mask = (class_map == cls_idx)
        if np.any(mask):
            mean_map[mask] = prior.typical_height
            std_map[mask] = prior.std_dev
            min_map[mask] = prior.min_height
            max_map[mask] = prior.max_height

    return mean_map, std_map, min_map, max_map


def _label_components(mask: np.ndarray) -> list[np.ndarray]:
    """4-connected connected-component labeling, pure numpy/Python — no
    scipy/cv2/skimage in ml/requirements.txt (same constraint documented in
    ml/features/extract_features.py). Returns one boolean mask per component.
    Patches are 256x256 max, so a plain BFS is fast enough (no need for a
    proper union-find)."""
    h, w = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    components = []
    for start_y in range(h):
        for start_x in range(w):
            if not mask[start_y, start_x] or visited[start_y, start_x]:
                continue
            stack = [(start_y, start_x)]
            visited[start_y, start_x] = True
            coords = []
            while stack:
                cy, cx = stack.pop()
                coords.append((cy, cx))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
            ys, xs = zip(*coords)
            comp_mask = np.zeros_like(mask, dtype=bool)
            comp_mask[list(ys), list(xs)] = True
            components.append(comp_mask)
    return components


def correct_missed_structures(
    depth: np.ndarray,
    class_map: np.ndarray,
    target_class: SemanticClass = SemanticClass.BUILDING,
    min_component_size: int = 25,
    boost_sigma: float = 1.0,
) -> tuple[np.ndarray, int]:
    """Rendering-time fix for a real, measured failure mode (docs/
    open_decisions.md, 2026-08-31 structure-diff finding): relative depth
    under-detects large, uniform, low-contrast flat structures (e.g.
    warehouse rooftops) because monocular depth needs internal edges/shadows
    to infer relief from, and a uniform-albedo roof has none. A real
    building has almost no reason to sit at or below the scene's own average
    depth — roads, ground, and most vegetation are the baseline a building
    should read above. Where semantic segmentation says a connected region
    IS `target_class` but the relative-depth model didn't elevate it above
    that baseline, shift the whole region up toward a plausible level
    (scene mean + `boost_sigma` * scene std) while preserving its internal
    relative shape — not flattening it to a single constant block, which
    would look worse, not better, once rendered.

    This intentionally does NOT touch the scalar calibration path (the
    feature vector fed to the regressor/fusion/SRTM-gate machinery) — only
    the depth array that becomes the frontend-facing heightmap. Every
    constant already measured and validated this session (texture-adaptive
    variance, fusion variances, the scale-anchor grounding gate) was fit
    against the *uncorrected* depth statistics; blending this into the
    calibration input would silently invalidate all of them.

    Only as good as the segmentation call it's given — a region segmentation
    mislabels as `other` instead of `building` (a real, separately-tracked
    bug, docs/open_decisions.md) is invisible to this function by
    construction; it can only correct within regions segmentation already
    identified correctly.

    Returns (corrected_depth, n_pixels_corrected) — the count lets the
    caller decide whether a warning is worth surfacing.
    """
    depth = depth.astype(np.float32).copy()
    scene_mean = float(depth.mean())
    scene_std = float(depth.std())
    target_value = float(np.clip(scene_mean + boost_sigma * scene_std, 0.0, 255.0))

    mask = class_map == CLASS_TO_IDX[target_class]
    n_corrected = 0
    for component in _label_components(mask):
        if component.sum() < min_component_size:
            continue
        component_mean = float(depth[component].mean())
        if component_mean > scene_mean:
            continue  # already elevated above baseline — not a missed detection
        shift = target_value - component_mean
        depth[component] = np.clip(depth[component] + shift, 0.0, 255.0)
        n_corrected += int(component.sum())

    return depth, n_corrected


def test_semantic_segmentation(sample_image: Image.Image | None = None) -> dict[str, np.ndarray]:
    """Unit & sanity test for semantic segmentation and height prior generation."""
    if sample_image is None:
        # Synthesize a realistic 256x256 test image with 4 distinct visual quadrants
        img_arr = np.zeros((256, 256, 3), dtype=np.uint8)
        # Top-left: Vegetation (Green forest)
        img_arr[:128, :128] = [34, 139, 34]
        # Top-right: Building (Red/orange rooftop)
        img_arr[:128, 128:] = [205, 92, 92]
        # Bottom-left: Road (Dark asphalt)
        img_arr[128:, :128] = [70, 70, 70]
        # Bottom-right: Other (Light sand/water)
        img_arr[128:, 128:] = [210, 180, 140]
        sample_image = Image.fromarray(img_arr)

    print(f"Running semantic segmentation on sample image (size={sample_image.size})...")
    class_map = segment_image(sample_image)
    mean_map, std_map, min_map, max_map = get_semantic_height_priors(class_map)

    print(f"Class map shape: {class_map.shape}, dtype: {class_map.dtype}")
    for sem_cls, idx in CLASS_TO_IDX.items():
        pixel_count = int(np.sum(class_map == idx))
        pct = (pixel_count / class_map.size) * 100.0
        prior = DEFAULT_HEIGHT_PRIORS[sem_cls]
        print(f" - {sem_cls.value.upper():<12}: {pixel_count:>6} px ({pct:>5.1f}%) | Prior height: {prior.typical_height:.1f}m ± {prior.std_dev:.1f}m [range {prior.min_height}-{prior.max_height}m]")

    assert class_map.shape == (sample_image.height, sample_image.width)
    assert mean_map.shape == class_map.shape
    assert std_map.shape == class_map.shape
    assert np.all(mean_map >= 0.0), "Negative heights detected in prior mean map"
    assert np.all(std_map > 0.0), "Non-positive standard deviations in prior std map"
    print("Semantic segmentation test passed successfully!")

    return {
        "class_map": class_map,
        "mean_map": mean_map,
        "std_map": std_map,
        "min_map": min_map,
        "max_map": max_map,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_semantic_segmentation()

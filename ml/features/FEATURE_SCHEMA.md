# Feature Schema — Phase 3 Chunk 3

Frozen. Phase 4's calibration regressor builds directly against this column order (`ml/features/extract_features.py::METADATA_COLUMNS + FEATURE_COLUMNS + LABEL_COLUMNS`). Changing it means redoing Phase 4 work, not just Phase 3 — per docs/phase3.md's own framing of this chunk.

Output: `data/processed/v1/features/features_v1.csv`, one row per patch.

## Metadata columns (not model inputs — joins/filtering only)

| Column | Meaning |
|---|---|
| `patch_id` | Matches `manifest.json`'s `patch_id` |
| `split` | `train` / `val` / `test` |
| `terrain_type` | `urban` / `sparse` / `hilly` / `forested` |
| `source` | `dfc2019`, `copernicus_dem`, `usgs_3dep` — provenance |

## Feature columns (regressor input — Chunk 3, Phase 1's depth output)

Computed over **every pixel** of the cached relative-depth map (`depth_cache/{split}/{terrain}/{patch_id}_depth.png`), unmasked — Phase 1's frozen interface (`ml/depth/PHASE1_NOTES.md`) guarantees a dense, fully-valid uint8 output for any input size. Depth maps carry no NoData concept of their own, unlike the ground-truth patch.

| Column | Meaning |
|---|---|
| `depth_min`, `depth_max`, `depth_mean`, `depth_std` | Basic distribution shape |
| `depth_p10`, `depth_p25`, `depth_p50`, `depth_p75`, `depth_p90` | Distribution percentiles — more robust to outlier pixels than min/max alone |
| `depth_grad_mean`, `depth_grad_std` | Mean/std of absolute pixel-to-pixel gradient magnitude (both axes, matches the roughness-style computation already used in `ml/data/preprocess.py::classify_terrain`) — structural/edge signal. Per `ml/depth/PHASE1_NOTES.md`'s failure-mode findings, this is what's expected to separate "clean object-level edges" (isolated structures, mountain ridgelines) from "blobby texture noise" (forest canopy) even when mean/std alone look similar. |
| `depth_edge_density` | Added 2026-08-31 (deferred optimization pass, `docs/open_decisions.md`). Fraction of pixels whose Sobel gradient magnitude exceeds that scene's own mean+std. Unlike `depth_grad_std` (magnitude), this is scale-relative — meant to separate "few strong isolated edges" from "same aggregate roughness spread diffusely" (canopy noise), i.e. pattern, not just magnitude. Pure numpy (no scipy/cv2 in `ml/requirements.txt`). |
| `depth_freq_high_ratio` | Added 2026-08-31, same motivation as above via the frequency domain instead of the spatial one. Fraction of 2D FFT magnitude energy in the outer 75% of the frequency radius — canopy-noise texture is high-frequency dominant with no coherent structure; clean terrain/ridgelines are low-frequency dominant. |
| `depth_local_entropy` | Added 2026-08-31, third view of the same pattern-vs-magnitude axis. Mean Shannon entropy of the pixel-value histogram over a 4x4 grid of blocks — a block spent on uniform noise reads higher entropy than a block of the same std spent on one clean edge. |

## Semantic feature columns (regressor input — Task 2, `docs/phase_optimization.md`)

Computed from the patch's **RGB image**, not the depth map — a separate code path from the depth features above. Per-patch pixel fractions of `ml/calibration/semantic_priors.py::segment_image()`'s 4 canonical classes, cached as `semantic_cache/{split}/{terrain}/{patch_id}_classmap.png`. Fractions sum to 1.

This is a legitimate, inference-available terrain proxy: the real `terrain_type` metadata column is derived from ground-truth height and is target leakage (never available at real inference, see `docs/open_decisions.md`'s 2026-08-31 leakage finding), but this segmentation call is one `ml/pipeline.py::run_pipeline()` already makes at real inference time to build the semantic height prior — so a feature derived from the same call is genuinely available, not leakage.

| Column | Meaning |
|---|---|
| `semantic_building_frac`, `semantic_vegetation_frac`, `semantic_road_frac`, `semantic_other_frac` | Fraction of patch pixels classified as each class by the segmentation model. |

## Label column (regression target — Phase 2's ground truth)

Computed only over the truth patch's **valid** pixels (`src.nodata`-excluded, or the explicit `-9999.0` sentinel `ml/data/ingest_supplementary.py` writes for its DEM-derived patches) — a NoData/padded pixel is not real height data and must not corrupt the label.

| Column | Meaning |
|---|---|
| `height_mean` | **Primary regression target.** Mean ground-truth height over the patch's valid pixels. |
| `height_min`, `height_max` | Auxiliary — not used as Phase 4's primary target, kept for later use (e.g. range-aware loss weighting) without needing to recompute from the raw patches. |

Patches with a cached depth map but zero valid ground-truth pixels are skipped entirely (reported, not silently dropped — see `build_feature_table()`'s `skipped` return value). This happens on some heavily-padded edge patches.

## Known limitation

`height_mean`'s scale is **not consistent across sources** in the same sense DFC2019's AGL patches are consistent with each other: DFC2019 patches are building-height-above-ground (0-50m); `ingest_supplementary.py`'s DEM-derived patches were deliberately normalized to height-relative-to-local-minimum (see `docs/open_decisions.md`, 2026-08-30 entry) specifically so they'd sit on a comparable scale — but "comparable" isn't "identical distribution." Phase 4 should be aware terrain-relief-derived labels and building-height-derived labels come from different physical processes, even after normalization.

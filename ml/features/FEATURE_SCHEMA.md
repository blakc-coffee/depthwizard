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

## Label column (regression target — Phase 2's ground truth)

Computed only over the truth patch's **valid** pixels (`src.nodata`-excluded, or the explicit `-9999.0` sentinel `ml/data/ingest_supplementary.py` writes for its DEM-derived patches) — a NoData/padded pixel is not real height data and must not corrupt the label.

| Column | Meaning |
|---|---|
| `height_mean` | **Primary regression target.** Mean ground-truth height over the patch's valid pixels. |
| `height_min`, `height_max` | Auxiliary — not used as Phase 4's primary target, kept for later use (e.g. range-aware loss weighting) without needing to recompute from the raw patches. |

Patches with a cached depth map but zero valid ground-truth pixels are skipped entirely (reported, not silently dropped — see `build_feature_table()`'s `skipped` return value). This happens on some heavily-padded edge patches.

## Known limitation

`height_mean`'s scale is **not consistent across sources** in the same sense DFC2019's AGL patches are consistent with each other: DFC2019 patches are building-height-above-ground (0-50m); `ingest_supplementary.py`'s DEM-derived patches were deliberately normalized to height-relative-to-local-minimum (see `docs/open_decisions.md`, 2026-08-30 entry) specifically so they'd sit on a comparable scale — but "comparable" isn't "identical distribution." Phase 4 should be aware terrain-relief-derived labels and building-height-derived labels come from different physical processes, even after normalization.

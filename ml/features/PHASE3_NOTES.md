# Phase 3 Notes — Relative Depth Feature Extraction (Batch)

Written at the end of Phase 3 (Chunks 1-4). Informs Phase 4 (calibration/fusion) and Phase 5 (validation). Frozen interface: `ml/features/FEATURE_SCHEMA.md` — read that first for the actual column contract.

## Final patch counts

| terrain | train | val | test | total |
|---|---|---|---|---|
| urban | 6728 | 2244 | 2245 | 11217 |
| forested | 5210 | 1735 | 1736 | 8681 |
| sparse | 1668 | 557 | 555 | 2780 |
| hilly | 137 | 47 | 47 | 231 |
| **total** | **13743** | **4583** | **4583** | **22909** |

`hilly` is 100% supplementary-sourced (`ml/data/ingest_supplementary.py` — Nepal, Tuscany, Appalachians, Sierra Nevada, West Virginia, Scotland). DFC2019 (Jacksonville FL + Omaha NE) has zero genuine hilly terrain — see the bug note below for why it originally looked otherwise.

## Skipped patches

**Zero.** `build_feature_table()` skips (and reports) patches with no cached depth map or no valid ground-truth pixel; the final run against the full manifest skipped none — all 22,909 trainable patches from Phase 2's manifest produced a feature row.

## A real bug found and fixed mid-phase

`ml/data/preprocess.py::classify_terrain()` silently defaulted every patch with a stray NaN pixel to `hilly` (NaN propagates through `np.std`/`np.mean`, and every numeric threshold comparison against NaN is `False`, so the patch fell through to the function's final `else`). All 33 of DFC2019's original "hilly" patches turned out to be this bug, not real hilly terrain — recomputed correctly, they're 23 urban / 6 forested / 4 sparse / **0 hilly**. Fixed in `classify_terrain()` and independently hardened in this module's `_height_label()`. Full writeup: `docs/open_decisions.md` (2026-08-31 entry). The counts table above already reflects the fix.

## Run time

- Chunk 2 (full batch depth inference, 22,909 patches, fresh cache): ~1h41m (6068.6s), 3.78 patches/s average, CPU/MPS (no GPU on this machine).
- Chunk 3 (feature extraction over cached depth maps, no model re-run): ~70s.
- Re-running `python ml/features/extract_features.py` today costs ~70s total — Chunk 2's depth pass resumes into a no-op (everything cached), only feature extraction does new work.

## Sanity checks (docs/phase3.md's own acceptance criteria)

- **NaN/missing values in the final feature table: 0.**
- **corr(depth_mean, height_mean) = 0.124** — weak but non-zero and positive. Expected, not concerning: raw uncalibrated relative depth isn't supposed to strongly predict absolute height on its own (no SRTM/semantic-prior scale correction yet) — that correction is Phase 4's entire job. A near-zero or negative correlation would have meant a bug; a weak positive one is the honest baseline Phase 4 has to beat.
- **Chunk 4's loadability check** — a trivial mean-value baseline predictor, fit on `features_train.csv` and evaluated on `features_val.csv`/`features_test.csv`, loads and runs without error:
  - Global mean baseline: MAE 5.71 on test.
  - Per-terrain mean baseline: MAE 2.74 on test — terrain_type alone roughly halves the error, a good sign the feature/label pairing is real and not noise.

## Known limitation carried into Phase 4

Per-terrain train-mean `height_mean` values: urban 5.48, forested 1.47, sparse 0.37, **hilly 221.15**. `hilly`'s scale is an order of magnitude larger than the others — DFC2019's building-AGL patches and the DEM-derived, relative-per-patch-normalized supplementary patches are "comparable" in that both represent height-above-local-baseline, but they come from physically different processes (building height vs. topographic relief) and aren't the same distribution. Phase 4 should be aware of this before assuming one calibration curve fits all terrain types equally. See `ml/features/FEATURE_SCHEMA.md`'s "Known limitation" section.

## Frozen for Phase 4

- `ml/features/FEATURE_SCHEMA.md` — column contract, do not change without redoing Phase 4 work.
- `data/processed/v1/features/features_{train,val,test}.csv` — the actual cache Phase 4 loads.
- `data/processed/v1/features/features_v1.csv` — same data, unsplit, kept for convenience (e.g. the correlation sanity check above).

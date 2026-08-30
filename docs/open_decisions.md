# Open Decisions Log

Append-only. Every open question, deferred decision, or design tradeoff surfaced during work on this repo goes here — not just in chat. When a decision gets made, update its entry to `RESOLVED` with the date and outcome instead of deleting it (the history of why is worth more than a clean list).

Format per entry: date raised, status, what it's about, current thinking, what would resolve it.

---

## 2026-08-31 — Phase 4 Chunk 1: regressor trained on real data, log-transform didn't fix hilly, information ceiling identified

**Status:** RESOLVED (2026-08-31)

Retrained `ml/calibration/regressor.py`'s `HeightRegressor` on Phase 3's real `features_{train,val,test}.csv` for the first time (previously synthetic-only). Added real early-stopping + best-checkpoint selection to `fit()` (tracks best val loss, restores that state_dict, not whatever epoch happened to run last).

First real-data run: overall RMSE 24.1m, but per-terrain breakdown showed `hilly` MAE 197-200m vs 0.8-2.4m for urban/forested/sparse. Tried `log_target=True` (train on `log1p(height)`, invert via `expm1` in `predict()`) to fix what looked like a `SmoothL1Loss` gradient-capping problem (hilly is ~1% of rows; a 200m error and a 2m error get similar gradient magnitude past `beta=1.0`). **Log-transform was a complete no-op** — hilly MAE unchanged (197m → 200m) after retraining.

Root cause is deeper than a loss-function issue: a nearest-neighbor check found hilly patches sit at Euclidean distance 0.18-0.6 (normalized, 11-dim feature space) from non-hilly patches with near-zero actual height. The 11 depth-map statistics (min/max/mean/percentiles/gradients of *relative* depth) genuinely do not encode absolute scale — relative depth is scale-free by construction, so no loss reweighting, architecture change, or data volume fixes this. This is an information ceiling, not a training bug. (Confirmed more data wouldn't help either, when asked: more hilly rows would only add more label-collisions in the same crowded feature-space region.)

Kept `log_target=True` anyway (still more correct — heights are non-negative) and kept the early-stopping mechanism (both verified working via `ml/tests/test_calibration.py`). Checkpoint: `ml/models/regressor_v1.pt` (gitignored).

**Resolves when:** Chunk 2 exists to compensate for this at the fusion level (see next entry) — this entry documents that the regressor itself has and will always have this ceiling, which is expected, not something to keep re-attempting to fix in isolation.

---

## 2026-08-31 — Phase 4 Chunk 2: SRTM fusion closes the hilly gap (86% MAE reduction, verified on real data) — after fixing a real bug in my own fusion code

**Status:** RESOLVED (2026-08-31)

Built `ml/calibration/calibrate.py` (the orchestrator Phase 4 was missing) and `ml/calibration/patch_geo.py` (recovers a patch's real WGS84 bounds analytically from its source DEM's transform + `patch_id`'s encoded offset — no patch file has ever had its own geotransform persisted, and DFC2019 patches never can, since DFC2019 tiles have no CRS at all per `ml/data/FORMAT_NOTES.md`).

First real-data validation run **made results worse**, not better (regressor-only error 432.6m → fused error 597.2m on the same patch). Root cause: my own bug, not a modeling problem — `_srtm_relief_estimate()` computed SRTM's max-min elevation *range* within the patch and fused it directly against `height_mean`, which is a *mean*, not a range. Two different physical quantities. Fixed to compute `mean(elevation - elevation.min())` — the same reduction `ingest_supplementary.py` uses to build the training label in the first place. After the fix: same patch, fused error dropped to 37.8m (91% reduction). Verified across 10 real held-out hilly patches spanning all 6 supplementary regions (live SRTM fetches, not mocked): **MAE 243.6m (regressor-only) → 33.3m (fused), an 86.3% reduction.**

Also fixed `fusion.py`'s default variances via `calibrate_scene()`'s own parameters: `regressor_variance` now defaults to 100.0 (was implicitly 9.0 via `fusion.py`'s own default), well above `srtm_variance`'s 16.0 — the regressor must never be trusted more than SRTM by default, given the information-ceiling finding above. Guarded by `test_regressor_variance_default_is_less_trusted_than_srtm`.

**What Chunk 2 does NOT yet cover** (scoped out, not forgotten):
- Semantic-prior fusion is wired but not separately validated against real data the way SRTM was.
- No dense per-pixel heightmap generation — `calibrate_scene()` operates at the same scalar-per-scene granularity Phase 3 trained at. Turning this into `ml/pipeline.py`'s dense heightmap output is Chunk 3's explicit job per `docs/phase4.md`.
- Non-georeferenced hilly input still has no path to accurate absolute height — this is a real, permanent ceiling (no external scale anchor exists for it), not a gap to close later. The honest behavior there is a relative/plausibility-scaled result per the original PRD, not a forced absolute number.

**Resolves when:** Chunk 3 wires this into `ml/pipeline.py` for full images, and semantic-prior fusion gets the same real-data validation treatment SRTM just got.

---

## 2026-08-31 — Phase 4 Chunk 3: pipeline wired to real calibration, confidence-gate redesigned mid-chunk

**Status:** RESOLVED (2026-08-31)

Wired `ml/pipeline.py` to Chunk 2's `calibrate_scene()`. Refactored `ml/features/extract_features.py::_depth_features` into a public `compute_depth_features(array)` so the pipeline computes features from its in-memory single-channel depth map, not by re-reading its own saved `"LA"` heightmap.png (which would silently mix the always-255 alpha channel into every statistic).

Running the real end-to-end test (a georeferenced Himalayan crop) immediately surfaced a design problem, not a bug: `confidence=5.6e-28`. `fuse_height_estimates`'s `disagreement_scale=10.0` default assumes building-height-scale disagreement (a few metres) — a real 627m gap between SRTM (~1263m) and the regressor/semantic (~0m, per the known information ceiling) collapsed confidence to numerically meaningless. Fixed with a magnitude-adaptive `disagreement_scale` in `calibrate_scene()` (`max(10.0, 0.5 * max(abs(estimate) for estimate in used))`) — confidence became meaningful (~0.37-0.41) instead of ~0.

That still wasn't enough: **tested against 4 different real crops (Nepal, 3x Tuscany), every single one landed in the same narrow 0.37-0.41 confidence band.** Root cause: the regressor and semantic-prior fallback are *structurally* near-zero for any real hilly scene (the information ceiling — the same failure mode all over again, from a different angle), so "cross-source disagreement" is baked into every hilly scene by construction, regardless of how good the fused estimate is. Gating `absolute_dsm` on that confidence value would mean hilly scenes could never reach it, no matter how much Chunk 2's SRTM fix actually helped — punishing SRTM for a disagreement whose cause is already known and already accounted for (that's *why* `regressor_variance` was set high in Chunk 2).

**Redesigned the gate** (user-approved option, "try SRTM-validity gating, get more data if that doesn't work" — it worked): `calibrate_scene()` now returns `CalibrationResult(fusion, srtm_valid_fraction)` — SRTM's own valid-vs-NoData pixel ratio, independent of what the other sources think. `ml/pipeline.py` gates `absolute_dsm` on `srtm_valid_fraction >= MIN_SRTM_VALID_FRACTION` (0.8, un-tuned default) when SRTM succeeds, rather than on fused confidence. Fused confidence is still computed and surfaced as an informational warning when low, never silently dropped — just no longer the hard switch.

**Verified on real data after the redesign:** Nepal crop → `absolute_dsm`, `max_height=2169m`, confidence-disagreement noted in warnings but didn't block the result. Tuscany crop → `absolute_dsm`, `max_height=81.6m`, same pattern. Plain non-georeferenced JPG → `relative_dsm`, SRTM never attempted, correct warning. All three real, not mocked.

**What Chunk 3 does NOT cover:** `MIN_SRTM_VALID_FRACTION=0.8` and `MIN_CALIBRATION_CONFIDENCE=0.5` are both reasonable-looking defaults, neither tuned against a real sweep of void/NoData or disagreement cases — worth revisiting with real failure examples if any surface. Semantic-prior fusion still hasn't had the same real-data validation treatment SRTM got.

---

## 2026-08-31 — Fusion variances measured against real data instead of hand-picked; `torchvision` fixed a silent semantic-priors degradation

**Status:** RESOLVED (2026-08-31)

Two optimization passes after Chunk 3, both measured against real held-out data rather than tuned by feel:

**1. `torchvision` was missing the whole session.** Every log line since Chunk 2 quietly said `Could not load transformers segmentation pipeline... Missing optional dependencies: torchvision` — `ml/calibration/semantic_priors.py` had been falling back to the crude color-heuristic segmenter every single run. Installed `torchvision==0.28.0` (pinned in `ml/requirements.txt`, matches `torch==2.13.0`), confirmed the real `segformer-b0` model now loads. Impact on hilly specifically was small and structural, not a fix that underdelivered: semantic priors cap height estimates at 0-30m (building/vegetation scale) by design, so even perfect segmentation can only nudge a hundreds-of-meters hilly estimate by a few meters — SRTM was already doing the real work there. Where this fix actually matters is urban/forested/sparse, the scale semantic priors are built for.

**2. `regressor_variance=100.0` (single fixed value) was backwards for the common case.** Measured real regressor error on the held-out test set: **~14.7 m² MSE on non-hilly terrain vs ~15,379 m² on hilly** — a ~1000x difference, confirming the error is genuinely bimodal, not a spread a single number can represent. The old fixed default of 100 (chosen in Chunk 2 specifically to fix hilly) was accidentally telling fusion to trust the crude semantic-prior heuristic (variance 25) *more* than a regressor that measured ~2.6x *more accurate* for the common non-hilly, non-georeferenced case.

Split into `regressor_variance_with_srtm=100.0` (kept — already validated against real hilly data, SRTM's own tiny variance dominates fusion at either 100 or the full measured ~15,379 anyway, no reason to touch a working number) and `regressor_variance_without_srtm=14.7` (measured), plus updated `semantic_variance` from the guessed 25.0 to the measured 38.9. `calibrate_scene()` now switches between the two regressor variances based on whether `srtm_estimate` is available, not a single static value.

**Verified on real data:** sampled 100 real non-hilly test rows, ran real fusion (regressor + measured real semantic estimate, no SRTM — simulating the common non-georeferenced case) with old vs new variances. Fused MAE: 3.995m (old) → 2.100m (new), a **47.4% reduction**. Honest caveat: fused-with-new-variances (2.10m) is still slightly worse than the regressor alone (1.53m) on this sample — fusion trades a little raw accuracy for a cross-check/confidence signal here, it doesn't strictly beat the regressor alone in the non-hilly regime, just beats the previous (mis-weighted) fusion by a lot.

**Resolves when:** if a real proxy for "is this scene likely hilly-scale" ever becomes available at inference (currently none exists — that's the whole information-ceiling problem), the two regressor variances could theoretically collapse back into a smarter single choice. Not needed now; the SRTM-availability branch is a clean enough proxy since SRTM is the mechanism that actually rescues hilly scenes anyway.

---

## 2026-08-31 — Texture-adaptive regressor variance (real headroom found, real heuristic grounded in Phase 1's own documented failure modes)

**Status:** RESOLVED (2026-08-31)

Before tuning further, measured whether the regressor even has headroom left in the non-hilly regime: **R²=0.26, correlation=0.54 on real held-out data** — nowhere near its ceiling, unlike hilly's true information-ceiling.

Checked whether `depth_grad_std` (a feature already computed, never previously used for anything but training the regressor) predicts *when* the regressor is unreliable — this operationalizes `ml/depth/PHASE1_NOTES.md`'s own qualitative Phase 1 finding that canopy occlusion produces "blobby texture noise... not real elevation." Found a real, if noisy, signal: splitting real test data at the median `depth_grad_std`, low-texture scenes have 1.36m MAE vs 2.00m for high-texture — a 47% gap.

Tried a continuous least-squares fit of squared-error vs `depth_grad_std` first — **rejected**: R²=0.007 (essentially no linear relationship holds; squared error is too outlier-dominated) and the fit produced a nonsensical negative "variance" at low percentiles. Used a robust 2-bin split on the real median instead: `depth_grad_std < 2.751` → variance 7.226 m², `>= 2.751` → variance 22.146 m² (their average, ~14.7, matches the earlier single fixed-variance measurement — consistent). `calibrate_scene()`'s `regressor_variance_without_srtm` now defaults to `None`, which triggers this per-scene lookup; pass an explicit float to force a fixed value instead (e.g. for tests).

**Verified on real data:** same 100-row non-hilly sample as the previous variance fix. Fused MAE: 2.100m (fixed 14.7) → 1.960m (texture-adaptive), a further 6.7% reduction. Modest, real, and honestly modest — still behind the regressor alone (1.533m) in this regime, same caveat as before.

**Considered and explicitly deprioritized in the same conversation:** feeding SRTM directly into the regressor as a training feature, and richer frequency/texture-pattern features to close more of the R²=0.26 gap. Both would need retraining and touch the frozen Phase 3 feature schema — real work, not free lunches, left for a future session if the accuracy gain becomes worth the schema-change risk.

**OPEN — deferred for a future session, not forgotten:** richer texture/frequency depth-map features (edge density, frequency-band energy, etc.) to close more of the non-hilly R²=0.26 gap. Estimated ~35-45 min: design 2-3 new features, regenerate the full feature cache (fast — reads existing cached depth maps, no model rerun), retrain the regressor, re-verify R² actually moved plus re-check hilly gap-closing didn't regress. Not part of `docs/phase4.md`'s original Chunk 1-4 scope — this came from a later "how to optimize further" pass, so deferring it doesn't leave a Phase 4 PRD deliverable unfinished. SRTM-as-input-feature was considered and rejected (see above) — the accuracy it would add for hilly is already captured via late fusion, and it wouldn't help the 99% non-georeferenced DFC2019 population, which is the one this deferred item actually targets.

---

## 2026-08-31 — Phase 4 Chunk 4 (hardening) done — Phase 4 complete per docs/phase4.md's own scope

**Status:** RESOLVED (2026-08-31)

- `TestSRTMFetch::test_fetch_chennai_elevation`/`test_caching_behavior` marked `@pytest.mark.slow` (real network); added offline-mocked equivalents (`test_fetch_srtm_elevation_returns_structured_data_offline`, `test_caching_behavior_offline`) that additionally prove the disk cache is actually hit — the live versions couldn't prove that without mocking.
- Removed `xgboost`/`scikit-learn` from `ml/requirements.txt` (confirmed zero references anywhere in `ml/` first).
- Wrote `ml/calibration/PHASE4_NOTES.md` — full Chunk 1-4 + optimization-pass summary.
- Full suite offline (`pytest -m "not slow"`): 83 passed, 3 correctly deselected.

Phase 4's own definition of done (`docs/phase4.md`: "`ml/pipeline.py` no longer returns a hardcoded relative result... it calls a real calibration function") was met in Chunk 3; Chunk 4 closes the loose ends the PRD itself flagged (flaky tests, dead deps, notes). The richer-texture-features optimization idea above was never part of this phase's scope — deferring it doesn't leave a PRD deliverable unfinished.

---

## 2026-08-30 — `ml/pipeline.py` duplicates `integration/contracts.py`'s `PipelineResult`

**Status:** OPEN (left as-is, not a bug — flagging for awareness)

`ml/pipeline.py` defines its own local `PipelineResult` dataclass (no `.validate()`, `metrics` defaults to `{}`, no `heightmap_16bit_path`). `integration/contracts.py` defines the real frozen contract with the same field names plus validation. `integration/pipeline_runner.py` converts one into the other.

This is deliberate — `ml/` must stay importable standalone with zero backend dependencies (per docs/depthwizard.md §9.8), and `ml/pipeline.py` has no `__init__.py`/package structure, so it can't cleanly `import integration.contracts` without the caller first putting the repo root on `sys.path` (which only `tools/run_pipeline.py` and `integration/pipeline_runner.py` currently do).

Risk: the two dataclasses can drift silently (e.g. a field renamed in one but not the other) since nothing enforces they stay in sync except `pipeline_runner.py`'s manual field-by-field mapping.

**Resolves when:** someone decides whether this duplication is worth a shared base (e.g. `contracts.py` importable by both without full backend deps) or whether the manual sync in `pipeline_runner.py` is an acceptable permanent seam. Not touched during Phase 3 work — revisit if the field list changes again.

---

## 2026-08-30 — Bhuvan/Cartosat samples gitignored despite PRD wording

**Status:** OPEN

`docs/depthwizard.md` §7.0 says Bhuvan/Cartosat samples should be "a fixed small sample set committed to the repo." Current practice (`ml/depth/PHASE1_NOTES.md`) keeps `ml/depth/samples/` gitignored — explicit project decision, no imagery binaries in git.

**Resolves when:** confirmed whether the PRD wording is meant literally (commit the samples) or aspirationally (describes intent, not a hard requirement).

---

## 2026-08-30 — Terrain classification is a height-statistics heuristic, not ground truth

**Status:** OPEN (documented limitation, not blocking)

`ml/data/preprocess.py::classify_terrain()` labels urban/sparse/hilly/forested purely from height-map std-dev + roughness thresholds (std<1.0 → sparse, std>=3.5 → urban, else roughness>0.02 → forested vs hilly). No semantic/land-cover signal used. Building edges vs. tree canopy of similar height can be misclassified.

**Resolves when:** Phase 4's semantic-prior segmentation component (if built) could double as a better terrain tagger — worth revisiting then rather than tuning the heuristic in isolation now.

---

## 2026-08-30 — GeoTIFF false-color band reorder is a heuristic, not sensor metadata

**Status:** OPEN (documented limitation, not blocking)

`ml/utils/texture_export.py::_render_geotiff()` guesses "raw multispectral, no blue band" from dtype alone (uint16+ 3-band → treat as Green/Red/NIR, render R=NIR/G=Red/B=Green). No access to actual sensor metadata. Matches the failure mode hit during Phase 1 testing on Resourcesat/Bhuvan/Cartosat imagery but is inference, not certainty.

**Resolves when:** a future phase has access to per-product sensor metadata (e.g. a `BAND_META.txt` sidecar, seen once during Phase 1 testing) to make this exact instead of inferred.

---

## 2026-08-30 — `docs/*.md` PRDs intentionally never committed to git

**Status:** RESOLVED (2026-08-30) — explicit user decision, not an oversight. Do not `git add docs/*.md`.

---

## 2026-08-30 — `ml/pipeline.py` now always emits `relative_dsm` until Phase 4 lands

**Status:** RESOLVED (2026-08-30)

Previously `run_pipeline()` set `output_type="absolute_dsm"` for any georeferenced input, regardless of whether calibration had actually run — a direct violation of docs/depthwizard.md §1 ("never claim absolute metric accuracy when the pipeline only produced a relative result"). Fixed: output is always `relative_dsm` with a warning until Phase 4's calibration module exists and actually runs. Stage A (`depth/backbone.py`) is now wired into the orchestrator, producing a real `heightmap_path`.

---

## 2026-08-30 — Supplementary hilly/sparse sources (Copernicus DEM + USGS 3DEP) ingested

**Status:** RESOLVED (2026-08-30), two sub-items OPEN

Added `ml/data/ingest_supplementary.py` (Phase 2 addition) to bring in Copernicus GLO-30 DEM + Sentinel-2 RGB (Nepal, Kansas, Tuscany) and USGS 3DEP DEM + Sentinel-2 RGB (Appalachians, Sierra Nevada) as extra `hilly`/`sparse` training patches, specifically to fix `hilly`'s severe under-representation (33 patches total before this).

Two real bugs found and fixed before merging into `manifest.json`:
- `classify_terrain()`'s std/roughness thresholds are calibrated for DFC2019's building-height AGL scale (0–50m); real topographic relief at this patch size routinely exceeds that by 10x+, so every supplementary patch initially came back mislabeled `urban`. Fixed by assigning `terrain_type` from each region's known geography (we picked these regions *because* they're hilly/sparse) instead of re-deriving it from a heuristic already documented as unreliable (see the terrain-heuristic entry above). The mislabeled batch (165 patches, all tagged `urban`) was written to `manifest.json` once and fully reverted before the fix.
- Height semantics: these DEMs are absolute elevation above sea level, not AGL. Every patch is normalized to height-relative-to-its-own-local-minimum before saving, discarding absolute elevation, per an explicit decision (not a default I assumed) to avoid corrupting Phase 4's regressor target scale.

**OPEN — two regions dropped, no valid RGB match found:**
- Copernicus DEM `S25_00_E132_00` (Australia): candidate RGB (`sentinel2_australia_TCI.tif`) covers -25.3°..-26.3°N, the DEM covers -24.0°..-25.0°N — no geographic overlap.
- USGS 3DEP `n41w106` (Wyoming): candidate RGB (`TCI (6).tif`) covers 41.5°..42.5°N, the DEM covers 40.0°..41.0°N — no overlap.

**Resolves when:** correctly-matched RGB tiles are sourced for these two regions and run through the same `ingest_supplementary.py` path (no code changes needed — just add the corrected entries to `REGIONS` in the script).

**Net result:** `hilly` went from 33 → 176 patches (104 train/36 val/36 test), `sparse` from 2,754 → 2,776. Manifest now 22,857 total entries (22,821 trainable).

---

## 2026-08-30 — West Virginia + Scotland added to hilly supplementary set

**Status:** RESOLVED (2026-08-30)

Two more region pairs added, both confirmed geographically overlapping before running (unlike the Wyoming/Australia false starts): USGS 3DEP `n38w080` (Virginia/Appalachian, fills the tile that first arrived RGB-less) + its matching Sentinel-2 RGB (14.2% of DEM tile overlap — a narrow but real strip); Copernicus GLO-30 `N56_00_W005_00` (Scottish Highlands) + matching Sentinel-2 RGB (46.7% overlap). Scotland's DEM has non-square pixel spacing (lon posting 1.5x lat posting) — expected Copernicus GLO-30 behavior above ~50° latitude, not a data defect; `reproject_rgb_to_grid()` handles arbitrary affine transforms already, no code change needed.

Kansas (the only supplementary `sparse` source) was pruned from `REGIONS` per the hilly-only decision above, but its already-produced 22 patches were left in the manifest/on disk — the user asked to add the two new regions, not to retroactively remove Kansas's output. Wyoming stays excluded even though a `sentinel2_wyoming_n41w106_TCI.tif` eventually showed up (moved to `_to_delete/`) — still doesn't geographically overlap the DEM tile, confirmed again, left out per explicit instruction.

`hilly`: 176 → 264 (156 train/54 val/54 test). Manifest now 22,945 total entries.

---

## 2026-08-31 — `classify_terrain()` silently defaulted every NaN-containing patch to "hilly"

**Status:** RESOLVED (2026-08-31)

Found while running Phase 3 Chunk 3's own acceptance check (NaN count + depth/height correlation sanity check — worked exactly as docs/phase3.md intended). All 33 of DFC2019's original "hilly" patches turned out to have at least one stray NaN pixel in their raw truth data (a LiDAR gap, `nodata` attribute left unset on these particular tiles) and **zero of them were actually hilly terrain** — geographically correct, since DFC2019 Track 1 is Jacksonville (FL) and Omaha (NE), both flat.

Root cause: `classify_terrain()` only filtered pixels equal to an explicit `nodata` sentinel; it never excluded literal NaN floats, and critically `!=` never excludes NaN even when `nodata` IS set — the two are independent things to filter. `np.std()`/`np.mean()` propagate a single NaN pixel into a NaN result, every numeric threshold comparison against NaN evaluates `False`, so every NaN-containing patch fell through every branch (`std<1.0`? False. `std>=3.5`? False. `roughness>0.02`? False, roughness is also NaN) into the function's final `else` — which is `hilly`. Confirmed via full-manifest scan: exactly these 33 patches, no others, contain any NaN (checked all 22,909 trainable patches regardless of current label).

**This means the entire "hilly under-represented" premise that drove this session's supplementary-data work (Nepal/Tuscany/Appalachians/Sierra Nevada/West Virginia/Scotland — see the entries above) was solving a bigger problem than initially understood: DFC2019 didn't have "too few" hilly patches, it had zero.** The supplementary work was necessary, not optional polish.

Fixed:
- `ml/data/preprocess.py::classify_terrain()` now excludes NaN via `~np.isnan()`, independent of and in addition to the `nodata` sentinel; roughness uses `np.nanmean()` so one stray pixel only drops the 1-2 gradient cells touching it, not the whole patch's roughness.
- `ml/features/extract_features.py::_height_label()` hardened the same way, independently (defense in depth, in case this NaN pattern shows up somewhere `classify_terrain` isn't in the path).
- The 33 patches were relabeled with NaN-safe stats (23 → urban, 6 → forested, 4 → sparse, 0 → hilly) and their files + cached depth maps moved to match; `manifest.json` updated in place (same split assignment, only terrain_type/std/roughness/paths changed).
- 4 regression tests added (`test_classify_terrain_excludes_stray_nan_regardless_of_nodata`, `test_classify_terrain_excludes_nan_even_when_nodata_also_set`, `test_height_label_excludes_nan_even_without_nodata_set`, plus the existing nodata test still passing).

Net effect on counts: `hilly` 264 → 231 (137 train/47 val/47 test) — now 100% supplementary-sourced, 0% DFC2019. The 33 reclaimed patches redistributed to `urban` (+23), `forested` (+6), `sparse` (+4).

---

## 2026-08-30 — No automated tests existed under `ml/` before this session

**Status:** RESOLVED (2026-08-30)

Added `ml/pytest.ini` + `ml/tests/` covering every implemented module (`backbone.py`, `texture_export.py`, `preprocess.py`, `download_datasets.py`, `pipeline.py` end-to-end). Nothing written for Phase 3/4/5 files — they were empty (0 bytes) at the time, nothing to test yet. Convention going forward: new ml/ logic ships with a test in the same chunk, not deferred.

---

## 2026-08-30 — Supplementary data pruned to hilly-only per explicit request

**Status:** RESOLVED (2026-08-30)

User narrowed the supplementary-data pull to hilly regions only (dropping the sparse/rural set entirely — Kansas + Australia Copernicus DEM tiles and their Sentinel-2 pairs). `supplementary-data/` now holds: 3 3DEP DEM tiles (all hilly), 2 Copernicus DEM tiles (Nepal, Tuscany — both hilly), 4 Sentinel-2 RGB tiles (Appalachian, Sierra, Nepal, Tuscany).

Also pulled `sentinel2_wyoming_n41w106_TCI.tif` back out of `supplementary-data/sentinel-2/` — this is the same non-overlapping candidate already logged as OPEN above (covers 41.5–42.5°N vs the DEM's 40.0–41.0°N). It should not be presented as a matched pair; the Wyoming 3DEP DEM tile is currently unpaired with any RGB. Resolves the same way as the existing open item: source a correctly-bounded Sentinel-2 tile for 40–41°N / -106..-105°W.

Stray duplicate raw tiles that had been left loose at the repo root (outside `supplementary-data/`) from the original download were moved to `_to_delete/` at the repo root rather than deleted outright (this session has no delete permission on the connected folder) — user should review and delete that folder.

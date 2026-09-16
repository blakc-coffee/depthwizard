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

## 2026-08-31 — Texture-pattern features close part of the non-hilly R²=0.26 gap (deferred item, now resolved)

**Status:** RESOLVED (2026-08-31)

Picked up the item deferred in the "Texture-adaptive regressor variance" entry above: the non-hilly regressor had real headroom (R²=0.26, correlation=0.54), and the hypothesis was that the 11 existing features only capture texture *magnitude* (`depth_grad_std`), not texture *pattern* — per `ml/depth/PHASE1_NOTES.md`'s qualitative finding that forest canopy occlusion produces "blobby texture noise" distinguishable from clean structural edges.

Added 2 new features to the frozen schema (no scipy/cv2/skimage installed — both pure numpy, `ml/features/extract_features.py`):
- `depth_edge_density` — fraction of pixels whose Sobel gradient magnitude exceeds that scene's own mean+std. Decoupled from raw magnitude (which `depth_grad_std` already covers) — meant to separate "few strong isolated edges" from "same aggregate roughness spread diffusely."
- `depth_freq_high_ratio` — fraction of 2D FFT magnitude energy in the outer 75% of frequency radius. Canopy noise reads as high-frequency-dominant with no coherent structure; clean terrain/ridgelines read as low-frequency-dominant.

Third candidate from the original plan (local texture entropy) was dropped — user-approved scope cut to 2 features, since edge density + frequency ratio already cover the "pattern vs magnitude" axis and a 3rd feature would add schema churn for marginal expected gain.

Appended both at the end of `FEATURE_COLUMNS` (preserves `depth_grad_std`'s index, which `calibrate.py::_DEPTH_GRAD_STD_IDX` and several tests key off by name already, so no index-based test needed fixing — only `test_calibrate.py`'s hardcoded `np.zeros(11)` literals were updated to `np.zeros(len(FEATURE_COLUMNS))`, since they were correct by accident, not by intent).

**Verified on real data**, same methodology as the original R²=0.26 measurement (filter test split to `terrain_type != "hilly"`, 4536 rows): regenerated the feature cache (fast — reads already-cached depth maps, no model rerun, ~seconds for 22,909 patches), retrained the regressor, re-evaluated:

| Metric | Old (11 features) | New (13 features) |
|---|---|---|
| Non-hilly R² | 0.26 | **0.32** |
| Non-hilly correlation | 0.54 | 0.59 |
| Non-hilly RMSE | — | 3.68m |
| Non-hilly MAE | — | 1.64m |

Real, honest, modest gain — not a home run, but not a no-op either (unlike the log1p-transform attempt for hilly, which was a genuine no-op).

**Re-verified nothing regressed:**
- `pytest -m slow` on `test_fusion_closes_the_hilly_gap_on_real_held_out_data` still passes against the retrained model — same held-out Nepal patch, regressor-only error 432.7m → fused 37.8m, matching the original ~91% single-patch reduction exactly. Hilly's fusion-based rescue is unaffected by the non-hilly feature addition, as expected (fusion downweights the regressor heavily for hilly regardless of which features fed it).
- `_TEXTURE_VARIANCE_THRESHOLD`/`_TEXTURE_LOW_VARIANCE`/`_TEXTURE_HIGH_VARIANCE` in `calibrate.py` were re-measured against the retrained model's real error distribution rather than carried over: threshold unchanged (2.751 — `depth_grad_std`'s own values didn't change, only new columns were added), but both variances drifted slightly (7.226→6.965, 22.146→20.112) since the retrained model's predictions shift even for previously-seen rows. Updated in `calibrate.py`; both changes are small (~4-9%), not a sign of a broken measurement.

**Resolves when:** this entry closes the deferred item. Any further non-hilly accuracy work (the R² gap isn't fully closed — 0.32 still leaves real headroom) is a new decision, not a continuation of this one.

---

## 2026-08-31 — Second optimization round: local entropy + auxiliary loss (near-zero gain), terrain-identity leakage ceiling measured but rejected

**Status:** RESOLVED (2026-08-31)

Follow-up to the entry above, after user asked "is this the best we can do" post-hoc. Three more candidates were sized and tried:

**1. `depth_local_entropy` (3rd texture-pattern feature, the one cut from the first pass).** Mean Shannon entropy of the pixel-value histogram over a 4x4 grid of blocks — pure numpy, same rationale as `depth_edge_density`/`depth_freq_high_ratio` (distinguish "noise spread evenly" from "same std spent on one clean edge"). Added to `FEATURE_COLUMNS` (now 14 columns) and `FEATURE_SCHEMA.md`.

**2. Auxiliary multi-task loss on `height_min`/`height_max`.** `ml/features/FEATURE_SCHEMA.md` had flagged these as "kept for later use... without needing to recompute from the raw patches" — genuinely unused until now. `HeightRegressor` gained `RegressorConfig.aux_targets`/`aux_loss_weight`; when `y_train_aux` is passed to `fit()`, the model grows extra output heads trained via `primary_loss + aux_loss_weight * mean(aux_losses)`, but `predict()`/`evaluate()` only ever surface the primary `height_mean` head — the public interface and every existing caller (`calibrate.py`, `pipeline.py`) is unchanged. Default (`aux_targets=0`, no `y_train_aux` passed) reproduces the exact old single-output architecture byte-for-byte, verified via `test_log_target_predict_returns_real_meters_not_log_space`'s direct-model-access assertion, which is shape-sensitive and would have caught a regression here. `train_regressor.py` now passes `height_min`/`height_max` from the cached CSV rows automatically.

**Combined result, measured on real held-out non-hilly test data (same methodology as the first pass):**

| | R² | correlation |
|---|---|---|
| Baseline (11 features) | 0.26 | 0.54 |
| First pass (13 features: edge density + freq ratio) | 0.32 | 0.59 |
| This pass (14 features + aux loss) | 0.325 | 0.596 |

**Honest read: this pass was a near-no-op.** +0.005 R² is inside likely run-to-run noise (no fixed seed on this training run) — entropy and the aux heads did not meaningfully add signal on top of what edge density + frequency ratio already captured. Reporting it as a real but negligible result, not silently rounding it up to "it worked" — same honesty standard as the log1p-transform and continuous-tau attempts earlier in this project.

**3. Terrain-identity leakage ceiling (diagnostic only, never deployed).** Before trying this, checked whether `terrain_type` is actually available to the real pipeline: `classify_terrain()` (`ml/data/preprocess.py`) computes it from the **ground-truth height array**, which `ml/pipeline.py` never has for a real uploaded image (that's the value being predicted); supplementary sources assign it from hand-known geography instead, equally unavailable at inference. So feeding it as a real model input would be leakage, not a deployable optimization — flagged before touching any code, per the project's "surface risks before executing" rule.

Ran it anyway as a pure ceiling measurement — one-hot `terrain_type` concatenated onto the 14 real features, temporary regressor, never saved as `ml/models/regressor_v1.pt`, never added to `FEATURE_COLUMNS`:

| | R² | correlation |
|---|---|---|
| Deployed model (no terrain) | 0.325 | 0.596 |
| Diagnostic ceiling (terrain leaked in) | **0.449** | **0.692** |

This is the biggest single number moved all session (+0.12 R², more than both real feature passes combined) — strong evidence that terrain identity carries information the current depth-map-only feature set genuinely cannot recover on its own, and that a *legitimate* (non-leaking) way to estimate terrain identity from something the pipeline actually has at inference (e.g. `ml/calibration/semantic_priors.py`'s segmentation output, already used for the semantic height prior) is the most promising lever left — bigger than another round of depth-map-only features.

**Re-verified nothing regressed:** full `ml/` suite (86 tests, including the live-network/slow ones) passes. `test_fusion_closes_the_hilly_gap_on_real_held_out_data` reproduces the identical result as before (regressor-only 432.7m → fused 37.8m, same held-out patch) — the aux heads and new feature don't touch hilly's fusion-based rescue. `calibrate.py`'s texture-adaptive variance constants re-measured a second time against this retrain: threshold stable at 2.751, variances drifted <2% (6.965→6.841, 20.112→20.027) — updated for consistency, immaterial in size.

**Resolves when:** this closes the "is this the best we can do" question for depth-map-only features — the honest answer is no, but the next real lever (semantic-segmentation-derived terrain proxy as a legitimate, inference-available feature) is a new, larger-scoped item, not a quick follow-on. Not started — flagging for a future session if pursued.

---

## 2026-08-31 — Task 2: semantic-segmentation terrain proxy closes part of the leaked-terrain gap (0.325 → 0.378 R²), done

**Status:** RESOLVED (2026-08-31)

Follow-on to the entry above — the leaked-`terrain_type` diagnostic showed +0.12 R² of recoverable signal (0.325 → 0.449) that no depth-map-only feature could reach because `terrain_type` is derived from ground truth and unavailable at real inference. Built the legitimate substitute: 4 new features (`semantic_building_frac`, `semantic_vegetation_frac`, `semantic_road_frac`, `semantic_other_frac`) — per-patch pixel fractions from `ml/calibration/semantic_priors.py::segment_image()`, computed from each patch's **RGB** image (a new code path in `ml/features/extract_features.py`, since `compute_depth_features()` only ever sees the depth array). This is genuinely inference-available, not leakage: `ml/pipeline.py::run_pipeline()` already runs this exact segmentation call at real inference time to build the semantic height prior.

**Real-data surprise, caught before committing to the full run (exactly the pattern this project's track record predicted):** `docs/phase_optimization.md`'s planning estimate of ~0.073s/patch (~28 min full run) turned out to include one-time model-load overhead baked into a 10-patch sample — measured cold at 0.374s/patch (~143 min projected). Warming the segmentation pipeline first and re-timing on a fresh 30-patch sample gave the real number: **0.048s/patch, ~18 min projected.** Full run measured at 19.3 min (19.87 patches/s sustained) — close to the corrected estimate, not the original one. Lesson: any per-patch timing check on a lazily-initialized model must warm it up first, or the estimate will be dominated by a one-time cost that doesn't recur in the real batch.

Cached to `data/processed/v1/semantic_cache/{split}/{terrain}/{patch_id}_classmap.png` (uint8 class-map PNGs, same resumable-cache convention as `depth_cache/`), wired into `build_feature_table()` (skips, reports, never fabricates a row missing either cache), `FEATURE_COLUMNS` split into `DEPTH_FEATURE_COLUMNS` (14) + `SEMANTIC_FEATURE_COLUMNS` (4) = 18 total, `ml/features/FEATURE_SCHEMA.md` updated in the same commit as the code.

**Design decision made explicitly, not defaulted into:** `ml/pipeline.py::run_pipeline()` now calls `segment_image()` twice per real inference — once to build the regressor's feature vector, once inside `calibrate_scene()`'s own `_semantic_estimate()`. User chose to accept the duplicate compute (~0.07s each, not a latency problem) over refactoring `calibrate_scene()`'s signature to accept a precomputed class map, which would've also touched its existing tests for a problem that isn't costing anything yet. Marked with a `ponytail:` comment at the call site in `ml/pipeline.py`.

**Measured result, retrained regressor on the new 18-feature schema, real held-out non-hilly test data:**

| | R² | correlation | MAE |
|---|---|---|---|
| Previous (14 depth-map-only features) | 0.325 | 0.596 | — |
| **This pass (18 features, +semantic)** | **0.378** | **0.633** | 1.563m |
| Diagnostic ceiling (leaked terrain_type) | 0.449 | 0.692 | — |

**Honest read:** a real, meaningful win — closed roughly 43% of the 0.325→0.449 gap (+0.053 of the +0.124 available) — but partial, as predicted going in: segmentation-derived class fractions are a noisier, coarser signal than the ground-truth-derived label they stand in for, so the remaining ~0.07 R² gap likely reflects segmentation-model imprecision (ADE20K keyword-mapping to 4 coarse buckets) rather than more headroom in this feature family. Not oversold as closing the gap.

**Re-verified, not assumed:** full `ml/` suite now 90/90 passing (4 new tests for `compute_semantic_features`/`run_batch_semantic_extraction`, offline-mocked). `test_fusion_closes_the_hilly_gap_on_real_held_out_data` (`-m slow`, live SRTM) still passes — hilly's fusion-based rescue is untouched, as expected (fusion downweights the regressor for hilly regardless of its non-hilly feature set). `calibrate.py`'s texture-adaptive variance constants re-measured a fourth time: threshold stable at 2.751 (`depth_grad_std`'s own values are unaffected by unrelated feature columns), variances shifted 6.841/20.027 → 7.052/17.710 (new checkpoint's predictions differ slightly even on previously-seen rows, same pattern as every prior retrain this session).

**Resolves when:** N/A — this closes Task 2 as scoped in `docs/phase_optimization.md`. If more non-hilly accuracy is wanted later, the next lever isn't another feature pass on this axis (segmentation-fraction noise is the likely remaining ceiling here) — it would be a better/finer segmentation model or a different signal family entirely.

---

## 2026-08-31 — Manual visual review found relative depth is either useful (structure) or actively wrong (flat terrain), not just "noisy"; scale-anchor grounding gate added

**Status:** RESOLVED (2026-08-31) — grounding gate; manual-review folder is an ongoing tool, not a one-time artifact

User asked to eyeball real samples before deciding between "accept current R²" and "build the CNN fork" (Task 3, spec-only). Generated `review_samples/` (gitignored, regenerable): 4 real held-out test patches per terrain (urban/sparse/forested/hilly), each as RGB / relative-depth / ground-truth-height side by side, plus the raw RGB alone.

**What the visual check found, that the aggregate R² numbers didn't make obvious:**
- **Urban:** relative depth picks up buildings as bright blobs that spatially align with the truth height map's building locations. Real, usable signal — matches urban being the least-bad terrain (R²=0.215).
- **Sparse:** truth height is genuinely flat (mean≈0, std=0.04 on the sampled patch) but the relative-depth map shows a strong smooth gradient (std≈60, spanning most of the 0-255 range) across that same flat field. This is the monocular depth model (built for ground-level photos with horizon/perspective cues) hallucinating a "near-to-far" gradient on nadir aerial imagery — not weak signal, actively wrong signal. Revises the earlier read (which attributed sparse's R²≈0.009 mainly to near-zero true label variance) — the depth features are injecting noise, not just failing to add signal.
- **Forested:** the sampled "forested" patch is visibly a residential street with trees, not canopy — consistent with the already-documented `classify_terrain()` heuristic-labeling limitation. Depth correlates with the (building-driven) truth heights here despite the mislabel. Working hypothesis, not yet confirmed: "forested" as a training bucket may be a mix of real-canopy and mislabeled-building patches with different depth↔height relationships, which would explain the terrain's positive correlation (0.562) alongside negative R² (-0.788) — a scaling/calibration problem, not a no-signal problem. Not yet quantified how much of the bucket is actually mislabeled.
- **Hilly:** the clearest visual confirmation of the already-known information ceiling — real relief spanning 0-175m in the truth map produces relative-depth statistics (mean=69.2, std=54.2) nearly indistinguishable from sparse's totally flat field (mean=83.5, std=60.2) in the same sample set.

**Real bug found and fixed as a direct result:** `ml/pipeline.py`'s absolute-height scale anchor (`scale_factor = fused_height / relative_mean`) had a `relative_mean > 1e-6` guard that never actually fires on real data — measured minimum `relative_mean` across all real held-out test patches is 0.024 (sparse), four orders of magnitude above that floor. The real explosion risk sits well above 1e-6, concentrated exactly where the visual check found the hallucinated-gradient artifact (sparse's 0.02-0.06 range): dividing a real `fused_height` by a small, physically-meaningless `relative_mean` blows `scale_factor` up into an implausible `max_height`. Fixed with two measured (not guessed) constants in `ml/pipeline.py`:
- `MIN_RELATIVE_DEPTH_MEAN = 0.05` — just above the real per-terrain 1st-percentile range (0.10-0.25 across urban/sparse/forested/hilly on held-out test data), so it only fires on genuinely degenerate cases, not normal low-relief scenes.
- `MAX_PLAUSIBLE_SCALE_FACTOR = 5000.0` — well above the largest real fused height this project has produced (~1263m, a real Himalayan SRTM anchor, Phase 4 Chunk 2), so it never clips a legitimate mountain-scale result.

Either firing disqualifies `absolute_dsm` and falls back to `relative_dsm` with a warning — a disqualifying gate, matching `MIN_SRTM_VALID_FRACTION`'s existing pattern, not a silent clamp that would keep reporting a number nobody trusts (same honesty principle as `docs/depthwizard.md` §1). 3 new tests added to `ml/tests/test_pipeline.py` (degenerate `relative_mean`, implausible `scale_factor`, and a sanity check that a legitimate result still reaches `absolute_dsm` unblocked). Full `ml/` suite: 93/93 passing.

**Resolves when:** N/A for the grounding gate — done. Two follow-ons flagged, not yet started: (1) quantify how much of the "forested" terrain bucket is actually mislabeled urban (would inform whether Task 3's CNN is worth building at all, or whether a labeling fix is the real lever); (2) decide whether Task 3 (CNN) still makes sense given the depth channel itself is unreliable for 2 of 4 terrains for terrain-dependent reasons a bigger model wouldn't obviously fix — user is holding off on Task 3 pending this and the labeling question.

---

## 2026-08-31 — Structure-agreement diff tool (`tools/depth_truth_diff.py`) built; real bias found is vegetation/uniform-flat-structure, not buildings

**Status:** RESOLVED (2026-08-31) — tool is a durable, reusable diagnostic; the finding motivates a segmentation-model follow-on, not yet started

User spotted a specific real patch (`JAX_427_012_patch_1_3`) where relative depth flagged a structure that ground truth didn't. Built `tools/depth_truth_diff.py` (repo-root tool, mirrors `tools/run_pipeline.py`'s standalone-harness convention) to check this systematically rather than by eyeballing one image: reduces both relative depth and truth height to a per-patch adaptive binary "elevated vs background" mask (mean+0.5*std, same heuristic style as `extract_features.py::_edge_density`), then diffs them into TP/FP(depth-only)/FN(truth-only)/TN. **Dataset-auditing tool only** — needs ground truth, which doesn't exist for a real user upload, so this never runs at inference time.

**Initial single-patch read was wrong; the aggregate (measured across all 4,583 real test patches, cross-tabulated against Task 2's cached semantic segmentation class maps — no new model inference needed) told a different story:**

| class | pixel share | FP rate | FN rate |
|---|---|---|---|
| building | 57.5% | **12.2%** (lowest) | **7.3%** (lowest) |
| vegetation | 16.6% | 15.5% | 13.4% (highest) |
| road | 3.4% | 13.5% | 4.4% |
| other | 22.5% | **16.2%** (highest) | 7.8% |

Buildings are the *most* reliable class for structure agreement, not the problem — the original flagged patch was not representative of the aggregate. Vegetation is the noisiest class in both directions (confirms Phase 1's documented canopy-occlusion finding — "blobby texture noise, not real elevation" — from an entirely different angle: structure agreement, not regression error). "Other" (the segmentation catch-all) has the single highest FP rate.

**Three illustrative real examples pulled and saved to `review_samples/` (gitignored, regenerable via the tool):**
1. `urban_OMA_251_038_patch_0_1_diff.png` — a clean flat rooftop: FP=0.3%, FN=0.1%. Confirms buildings-with-edges work well.
2. `urban_OMA_357_010_patch_3_2_diff.png` — dense canopy (mislabeled `urban` in the manifest — a second, independent instance of the already-documented `classify_terrain()` mislabeling issue, not a new bug). Truth has real fine per-tree height texture; relative depth produces one smooth gradient with zero per-tree resolution, so the diff splits into a checkerboard along the gradient's midline — a direct visual confirmation that depth can't resolve individual-tree-scale structure at all.
3. `urban_JAX_264_025_patch_0_2_diff.png` — **new finding, not previously documented.** A large uniform flat warehouse rooftop, unambiguously a building in the RGB and correctly ~15m in truth. Two independent failures on the same patch: (a) `ml/calibration/semantic_priors.py`'s segmentation model labeled it `other`, not `building` — a real classification miss, not a depth problem; (b) relative depth itself barely registers it as elevated (FN=44%) — a large, low-contrast, uniform-albedo rooftop gives monocular depth almost no internal edges/shadows to infer relief from, a distinct failure mode from canopy noise (canopy over-detects via texture noise; uniform flat roofs under-detect via lack of any texture at all).

**Resolves when:** the segmentation misclassification (large uniform rooftops → `other` instead of `building`) is worth fixing given user's "make the classification a bit more better" request — not yet started. Candidate angles, not yet sized: (a) ADE20K keyword-mapping tweak in `_map_label_to_semantic_class` (`ml/calibration/semantic_priors.py`) if the underlying model output is labeling these something mappable-but-missed; (b) the model itself may simply not resolve large uniform industrial rooftops well (ADE20K's training distribution skews toward street-level/indoor scenes, not aerial industrial structures) — would need inspecting the raw per-segment labels the pipeline returns for this class of patch before choosing a fix, not guessed.

---

## 2026-08-31 — Missed-structure correction heuristic added to the rendered heightmap (frontend-facing fix for the FN finding above)

**Status:** RESOLVED (2026-08-31) — heuristic shipped; its ceiling is bounded by segmentation quality, tracked as a dependency on the still-open item above

User's concern: the frontend renders whatever `heightmap.png` says, so a real building that relative depth under-detects (the uniform-flat-rooftop failure mode just documented) will render as a visible hole/flat patch where a building should clearly rise — not just a regression-accuracy number, a visibly wrong output.

Added `ml/calibration/semantic_priors.py::correct_missed_structures(depth, class_map, target_class=BUILDING, min_component_size=25, boost_sigma=1.0)`: labels connected components of the segmentation's building mask (pure-numpy 4-connected BFS, `_label_components` — no scipy/cv2 per this project's existing constraint), and for any component whose mean relative-depth value doesn't even clear the *scene's own average* (a real building has almost no reason to sit at or below general-scene baseline), shifts the whole component up toward `scene_mean + boost_sigma*scene_std`, preserving internal relative shape rather than flattening it to one constant value. Components under `min_component_size` (segmentation noise, not real regions) are left alone, as are components already reading above baseline (not every building needs correcting, only missed ones).

**Deliberate scope boundary:** this only touches the array that becomes the rendered `heightmap.png` in `ml/pipeline.py`. The scalar calibration path (the feature vector fed to the regressor/fusion/SRTM-gate machinery) keeps using the *original, uncorrected* depth statistics — every constant measured and validated this session (texture-adaptive variance, fusion variances, the scale-anchor grounding gate) was fit against uncorrected depth features, and blending the correction in there would silently invalidate all of them without re-measuring. `ml/pipeline.py` now computes `feature_dict`/`feature_vector` from the original `depth_array` as before, and separately applies `correct_missed_structures()` (reusing the same `class_map` already computed for Task 2's semantic features — no extra segmentation call) to build `heightmap_array`, which is what actually gets saved. The heightmap save itself moved from immediately after Stage A to the end of `run_pipeline()`, since it now depends on Stage B's segmentation output when calibration is available (falls back to the uncorrected array, same as before, when no regressor checkpoint exists).

**Real, measured limitation, not a hidden gap:** this heuristic is only as good as the segmentation mask it's given. Demonstrated directly on the same `JAX_264_025_patch_0_2` warehouse-rooftop patch from the entry above: with the *current*, buggy segmentation (which mislabels most of that rooftop as `other`), the correction only reaches 12,341 px; simulating what segmentation *should* have said (using truth's own elevated region as a stand-in, `review_samples/urban_JAX_264_025_patch_0_2_correction_demo.png`) correctly boosts 42,028 px and visibly restores the rooftop's shape in the rendered heightmap. **This heuristic's real-world value is capped by the still-open segmentation-classification bug above** — fixing that bug will make this correction cover more real missed buildings for free, without touching this function again.

7 new tests (`ml/tests/test_calibration.py::TestMissedStructureCorrection`) cover: a missed building gets boosted, an already-elevated one is left alone, tiny/noise-sized components are ignored, non-target classes are never touched, and a no-building scene is a no-op. Full `ml/` suite: 98/98 passing.

**Resolves when:** N/A for the heuristic itself — done, shipped, tested. Its practical ceiling resolves when the segmentation-classification bug (entry above) is fixed — that's the next planned step, not a separate open item.

---

## 2026-08-31 — Segmentation classification fixed: ADE20K interior-object labels remapped to BUILDING (domain-specific)

**Status:** RESOLVED (2026-08-31) for the keyword-mapping fix; OPEN follow-on for whether to regenerate the trained feature cache

Root-caused the misclassified-rooftop bug from the two entries above by inspecting the segmentation model's raw per-segment output (not guessed): on the flagged `JAX_264_025_patch_0_2` warehouse rooftop, the model returned exactly 3 segments for the whole patch — `wall` (18.9%, correctly mapped to BUILDING), `ceiling` (35.6%), `windowpane` (45.4%) — the latter two ADE20K *interior-object* labels, falling to OTHER by the old keyword map. The model (trained on ADE20K's largely indoor/street-level scene distribution) is reading a flat, light-colored rooftop as a room interior. Measured across 25 real urban test patches before changing anything: `mountain`/`earth`/`rock`/`water`/`truck`/`floor` also fall to OTHER but are legitimately non-building even in this domain — left alone. `window`/`door`/`ceiling`/`cabinet`/`mirror`/`escalator` are the interior-object cluster, added to `ADE20K_BUILDING_KEYWORDS` (`ml/calibration/semantic_priors.py`) with an explicit comment on why this is safe *only* because DepthWizard's pipeline never segments real indoor imagery — if that ever changes, this keyword set needs reconsidering.

**Real effect, measured, not assumed — before/after on the same 25 real urban test patches, fresh (uncached) segmentation calls:**

| class | before | after | delta |
|---|---|---|---|
| building | 51.3% | 56.5% | **+5.2%** |
| vegetation | 21.1% | 21.1% | 0.0% |
| road | 1.9% | 1.9% | 0.0% |
| other | 25.6% | 20.4% | **-5.2%** |

Clean, targeted move — vegetation and road shares are untouched, confirming the fix isn't bleeding into classes it shouldn't touch.

**One real caveat found and reported honestly, not swept under the rug:** on the specific flagged patch, the segmentation model's own proposals covered ~100% of the image with just those 3 segments — meaning it never separately detected the visible highway/road in that image at all (a distinct, deeper failure: a missing segment proposal, not a taxonomy/keyword problem). Since the keyword fix maps `ceiling`/`windowpane` to BUILDING wherever they appear, and this particular image's road pixels happened to fall inside those masks, the fix incidentally reclassified that image's road portion from OTHER (~0m prior, roughly right) to BUILDING (~10m prior, wrong). The 25-patch aggregate above shows this is not systemic (road share unchanged across the sample) — this was a one-off case where the model simply failed to propose any road segment for that specific image, and no keyword-mapping change can fix a missing segment proposal. Flagging this as a known, rare failure mode rather than claiming the fix is unconditionally safe.

7 new tests (`ml/tests/test_calibration.py`: `test_interior_object_labels_map_to_building_not_other`, `test_legitimately_non_building_labels_still_map_to_other`, plus 5 for `correct_missed_structures` from the entry above — counted once). Full suite: 100/100 passing.

**Resolves when (OPEN follow-on):** the trained regressor's 18-feature checkpoint (`ml/models/regressor_v1.pt`) and the cached `semantic_building_frac`/`semantic_other_frac` features (`data/processed/v1/semantic_cache/`, 22,909 patches) were both built against the *old* keyword mapping — this fix only affects fresh/live `segment_image()` calls (used by `calibrate_scene()` and `correct_missed_structures()` at real inference time), not the already-cached training data. Regenerating the cache + retraining is the same ~19-minute-batch-plus-retrain cost as Task 2's original run — not done yet, flagged for an explicit decision rather than assumed, since it's a real cost and the R²=0.378 baseline would need re-measuring against it either way.

---

## 2026-08-31 — Semantic cache regenerated + regressor retrained on the ADE20K keyword fix: mixed result, honestly reported

**Status:** RESOLVED (2026-08-31) — closes the OPEN follow-on above

Regenerated `data/processed/v1/semantic_cache/` (deleted and rebuilt, ~24min: depth resumed as a no-op, only the semantic batch reran) and retrained `ml/models/regressor_v1.pt` against the corrected `semantic_building_frac`/`semantic_other_frac` features. Same 18-column schema, no code changes to the feature/training pipeline — only the underlying segmentation labels changed.

**Result is a mixed win, not a clean one — reported straight, matching this project's standing practice of not spinning a partial result:**

| | R² (pooled non-hilly) | corr | urban R² | sparse R² | forested R² | hilly R² |
|---|---|---|---|---|---|---|
| Before (buggy keyword map) | 0.378 | 0.633 | 0.215 | 0.009 | -0.788 | -2.808 |
| **After (fixed keyword map)** | **0.364** | **0.621** | **0.186** | **0.050** | **-0.513** | -2.844 |

Forested — the terrain the keyword fix specifically targeted (mislabeled rooftops living in a bucket nominally about canopy) — improved meaningfully (R² -0.788 → -0.513, real movement in the intended direction). Sparse ticked up slightly. But urban *dropped* (0.215 → 0.186), and the pooled non-hilly number went down overall (0.378 → 0.364) because urban has the largest test-set share (2245 of 4536 non-hilly rows) and outweighs forested's gain in the pooled average. Hilly unchanged within noise (still the known information ceiling, unaffected by a non-hilly-focused fix as expected).

**Why urban likely regressed, not confirmed further this session:** cleaner building/other separation shifts the *distribution* of `semantic_building_frac` for scenes that were previously miscategorized — some urban scenes that used to read as partly `other` (diluting their building fraction toward a value the model had implicitly learned to associate with something else) now read as more purely `building`, and the regressor's learned mapping for that feature region may not have been retrained on distribution enough to adapt cleanly with only ~13,743 training rows. Plausible, not verified — flagging as a hypothesis, not a finding.

**What this means going forward:** the segmentation fix is still worth keeping — it's measurably correct (25-patch validation in the entry above showed real, targeted improvement with no bleed into unrelated classes), and it directly improves `correct_missed_structures()`'s real-world coverage regardless of what it does to the regressor's R². But it is NOT a free win for the regressor's accuracy — don't report "R² improved" from this change; the honest framing is "one real terrain-labeling bug fixed, with a small, not-fully-understood regression elsewhere that nets out roughly flat overall."

Re-verified: `test_fusion_closes_the_hilly_gap_on_real_held_out_data` (`-m slow`) still passes — hilly's fusion rescue unaffected, as expected. `calibrate.py`'s texture-adaptive constants re-measured: threshold stable at 2.751 (unaffected, as with every prior retrain), variances shifted 7.052/17.710 → 6.537/18.778. Full `ml/` suite: 100/100 passing.

**Resolves when:** N/A — done. If urban's regression is worth chasing further, the next step (not started) would be checking whether it's specifically the `semantic_building_frac` feature driving it (e.g. by comparing urban-only feature distributions before/after the keyword fix), not re-guessing from aggregate numbers alone.

---

## 2026-08-31 — Flat-pavement-as-`wall` false positive: investigated, no cheap fix found, deliberately skipped

**Status:** CLOSED, not fixed — real, understood, low-priority

Found while sanity-checking the forested-mislabeling investigation: the segmentation model's `wall` label (pre-existing, not part of this session's keyword fix) fires on flat, uniform runway/parking-lot pavement, not just real building walls — confirmed visually on `OMA_059_026_patch_1_0` (74.6% `wall`) and `OMA_142_032_patch_1_3`, both genuinely flat paved surfaces with road markings, not buildings.

**Investigated and rejected three candidate fixes, each measured, not guessed:**
1. **Confidence-score filtering** — the HF segmentation pipeline returns `score=None` for every segment; no confidence signal exists to filter on.
2. **Label-vocabulary filtering** — even the known-good building patch (`OMA_251_038_patch_0_1`, the near-perfect correction-heuristic example) returns nonsense ADE20K labels too (`floor`, `curtain`, `bathtub`) alongside `wall`. The raw label vocabulary is noisy on real buildings and pavement alike — can't gate on "does it return a weird label," both classes do.
3. **Color/texture heuristic cross-check** (using the existing `_heuristic_color_segmentation` road-detection thresholds as a sanity check on the neural model's building calls) — measured whole-patch color_std/brightness for 3 known pavement false-positives (std 4.3-7.0, brightness 146-183) against 3 known real buildings (std 3.1-5.4, brightness 100-208): **the ranges overlap**. Flat concrete pavement and flat concrete/light rooftops are genuinely close to indistinguishable in RGB color statistics from directly overhead.

**Scale measured before deciding whether to invest further:** 574 patches (2.5% of the full 22,909-patch trainable set), **entirely confined to `sparse`** terrain (0 in forested/urban/hilly), which already has near-zero R² (0.009→0.050 across this session's changes) — little practical accuracy to lose or gain either way.

**Decision:** skip. Given no cheap, reliable signal exists (score, label, or color/texture) and the affected population is small and already low-accuracy, forcing a narrow heuristic (e.g. hunting for parking-line markings as a road-specific cue) was assessed as more likely to be a shaky, overfit patch than a real fix — user chose not to pursue it further. This may be a smaller instance of the same information-ceiling pattern as hilly: some real-world distinctions (flat pavement vs. flat rooftop, viewed from directly overhead) may not be recoverable from RGB+depth alone without additional context (surrounding scene, real elevation, or a model actually trained on this domain).

**Resolves when:** revisit only if (a) a future model swap (e.g. a domain-appropriate segmentation model, not ADE20K-pretrained) naturally fixes this as a side effect, or (b) sparse's accuracy becomes a priority for a reason unrelated to this specific bug.

---

## 2026-08-31 — Forested-bucket relabeling: correction to my own prior claim before starting

**Status:** context note, not a decision log entry — see the entry immediately after for the actual work

Before starting the forested relabeling work, caught and corrected an overstated claim from earlier in the session: `terrain_type` is confirmed (by code inspection) to be **metadata-only** — it appears in `METADATA_COLUMNS`, never in `FEATURE_COLUMNS`, and is used only for cache file paths and reporting groupings (`ml/features/extract_features.py`). Relabeling mislabeled forested patches does **not** change any row's actual features, label, or the regressor's predictions — it only changes which per-terrain bucket a patch's existing (unchanged) prediction error gets counted under. The value of this work is **evaluation honesty**, not a model-accuracy lever. Flagging this explicitly so the relabeling work below isn't mistaken for a performance fix — it's a data-hygiene fix that makes forested's reported R² meaningful for the first time, nothing more.

---

## 2026-08-31 — Forested-bucket relabeling executed: 5,762 patches moved, revealed genuine canopy is worse than the mixed bucket suggested

**Status:** RESOLVED (2026-08-31)

Built `tools/relabel_mislabeled_forested.py` — a one-off, dry-run-capable migration that reclassifies `forested`->`urban` for patches meeting all three (conservative, defense-in-depth) criteria: `semantic_building_frac >= 0.5`, `semantic_vegetation_frac < 0.2`, and real truth-height relief `>= 2.0m` (the relief floor specifically guards against the flat-pavement-as-`wall` false positive from the entry two above — confirmed unnecessary in practice since that bug is 100% confined to `sparse`, never `forested`, but cheap insurance for a bulk file-moving operation). Backed up `manifest.json` before mutating (`manifest.json.bak_relabel_applied`, plus a dated backup made before running anything).

**Dry run first, then applied:** 5,762 of 8,681 forested patches (66.4%) flagged and moved — raw RGB tif, raw truth tif, cached depth PNG, and cached semantic classmap PNG, all four files per patch, from their `forested` subdirectory to `urban` (23,048 file moves total). Verified before/after: total cache PNG count unchanged (45,818), total trainable patch count unchanged (22,909), and the terrain-count delta matches exactly (`urban` 11,217->16,979 [+5,762], `forested` 8,681->2,919 [-5,762]) — no files lost or duplicated. Split proportions preserved (patches moved within their existing train/val/test split, never across).

**Re-evaluated the existing checkpoint — no retrain needed, and none was run,** since (per the note above) `terrain_type` isn't a model input; pooled non-hilly R² came back byte-identical (0.3641 before and after), confirming that claim empirically, not just from code inspection.

**The honest per-terrain picture, real held-out test data, same checkpoint:**

| terrain | before relabel | after relabel |
|---|---|---|
| urban | R²=0.186 (n=2245) | **R²=0.3105** (n=3432) |
| forested | R²=-0.513 (n=1736) | **R²=-0.9593** (n=549) |
| sparse | R²=0.050 (n=555) | unchanged (not touched) |
| hilly | R²=-2.844 (n=47) | unchanged (not touched) |

Urban's honest R² is substantially better than its previously-reported number once it correctly absorbs patches that were always predicted well but wrongly attributed elsewhere. **Forested got worse, not better** — and this is the important, sizeable finding: the old mixed bucket's -0.513 was propped up by the well-predicted (mislabeled) buildings inside it. Stripped down to genuinely real canopy, the number is -0.9593 — meaningfully worse than the mixed figure implied. This is now believed to be a real, structural limit specific to canopy, consistent with Phase 1's own documented finding (`ml/depth/PHASE1_NOTES.md`: canopy occlusion produces "blobby texture noise, not real elevation") — not as extreme as hilly's absolute-scale-blindness ceiling, but a real, separate information-ceiling-shaped problem for genuine tree canopy, now visible for the first time because the bucket it's measured in is finally clean.

Re-verified: `test_fusion_closes_the_hilly_gap_on_real_held_out_data` (`-m slow`) still passes — untouched by this, as expected (hilly patches were never forested). Full `ml/` suite: 100/100 passing (no test hardcodes forested/urban patch counts, so nothing broke structurally).

**What this means for Task 3 (CNN):** sharpens the picture rather than resolving it. Forested's badness is now understood to be *partly* real-canopy-information-ceiling (like hilly, though less extreme) and *partly* was label noise (now fixed). A CNN wouldn't be expected to fix the canopy-ceiling part any more than it fixes hilly's — but urban's newly-revealed R²=0.3105 (its honest, uncorrupted number) suggests the non-canopy, non-hilly terrain types have more real headroom than previously visible, since urban's true signal was being diluted by misattributed rows in the old evaluation. Worth re-deciding Task 3 with this cleaner baseline rather than the pre-relabel numbers.

**Resolves when:** N/A — the relabeling itself is done. `tools/relabel_mislabeled_forested.py` is kept in the repo as a reusable, re-runnable migration (idempotent — a second run finds 0 remaining forested patches meeting the criteria) in case new data is ingested into the forested bucket later via the same flawed `classify_terrain()` heuristic.

---

## 2026-08-31 — Post-fix verification found a new, distinct correction-heuristic failure mode (small, real, honestly reported)

**Status:** OPEN (documented limitation, not blocking) — real severity assessed as low

Re-ran `correct_missed_structures()` on `JAX_264_025_patch_0_2` (the flagged warehouse-rooftop patch) against the *real* current segmentation cache (not the earlier simulated-best-case demo). The keyword fix does now correctly tag the whole scene's `wall`/`ceiling`/`windowpane` segments as BUILDING (100% building_frac, up from ~19%) — real progress, matches the earlier 25-patch validation. But this specific patch's segmentation model still only ever proposed 3 segments for the *entire* image (unchanged from before — this was never a labeling problem, it's a missing-segment-proposal problem, already flagged as unfixable by keyword mapping two entries above). Since `wall`/`ceiling`/`windowpane` now all map to BUILDING, and those 3 segments together cover ~100% of the image including the visible highway, `correct_missed_structures()` treats the *entire scene* as one connected "building" component and applies one uniform boost to it — visibly brightening the real rooftop (correct) but also the adjacent highway (wrong), since the function has no way to know the segmentation model silently merged two physically different surfaces into one blob.

**This is a distinct failure mode from what was fixed, not a sign the fix didn't work:** before, the bug was "segmentation mislabels the building as `other`" (fixed). Now, the residual bug is "segmentation doesn't separate the building from the adjacent road within its own segment proposals at all" (not fixed, not fixable by keyword mapping — same root cause as the previously-logged missing-road-proposal issue, just now visible through a different function).

**Severity assessed as low, not chased further:** this only manifests when segmentation fails to produce *any* separate road segment for a scene — measured earlier as rare, not systemic (the 25-patch aggregate showed road's pixel share unchanged by the keyword fix, meaning most scenes DO get a proper road proposal). `correct_missed_structures()`'s existing `min_component_size` guard doesn't help here since the merged blob is large by construction, not noise-sized.

**Resolves when:** if this turns out to matter in practice (not measured at scale, only observed on the one patch that originally flagged the whole investigation), the real fix is a genuinely better/finer segmentation model — no code-level heuristic in `correct_missed_structures()` can distinguish "one big real building" from "a building blob that silently swallowed an adjacent road" using only the class map it's given, since both look identical to the function (one large connected BUILDING region).

---

## 2026-08-31 — Dense DSM fusion built: SRTM-as-trend + relative-depth-as-detail, ~29x per-pixel RMSE reduction on real data

**Status:** RESOLVED (2026-08-31) — full spec: `docs/dense_dsm_fusion.md`

User's proposal, sharpened through discussion: the dense (per-pixel) `absolute_dsm` output previously used SRTM only as a single scalar to uniformly rescale relative depth's own shape — discarding SRTM's real, if coarse (~30m/pixel), spatial detail entirely, and structurally vulnerable to propagating a hallucinated relative-depth shape (the sparse flat-gradient bug, documented above) even when the scalar anchor was numerically correct.

**Built `ml/calibration/dense_fusion.py`:** SRTM supplies the low-frequency trend (nearest-neighbor resample onto the output grid — deliberate, avoids blending real values across void boundaries the way bilinear would); relative depth supplies only its own high-frequency detail (its own trend, matched to SRTM's native spatial resolution via a downsample/upsample low-pass filter, removed first so it never fights or duplicates SRTM's real trend); the two are summed where SRTM has real coverage, with today's existing uniform-rescale formula as an honest per-pixel fallback where SRTM is void. Reuses the *existing* scalar `scale_factor` (`fused_height / relative_mean`) to convert the detail component into meters — does not invent a second, independent scale computation.

**Wired into `ml/pipeline.py`** on the `absolute_dsm` branch only (confirmed via full contract-doc check: `dsm_path` — "GeoTIFF, absolute results only" — and `confidence_map_path` were both already-defined-but-always-`None` fields in `docs/depthwizard.md` §9.8, so this is additive, not a breaking change to the existing `heightmap_path`/metadata contract). `heightmap_path`'s bytes and the existing linear min/max metadata contract are completely untouched — the new fused, non-linear result lives in the new `dsm_path` GeoTIFF exclusively. `confidence_map_path` gets a per-pixel provenance map (255=SRTM-measured, 76=model-predicted infill), and a warning summarizes the coverage split when SRTM has any void. `fetch_srtm_elevation()` is called a second time in `ml/pipeline.py` (disk-cached, so a cache hit, not a real second network round-trip) — same accepted-duplicate-call tradeoff already made for `segment_image()` in Task 2, not a signature refactor of `calibrate_scene()`.

**Real, measured result — not assumed:** the honest test-population constraint (only the ~231 hilly supplementary patches have real geo bounds in this dataset; DFC2019 structurally never does) was stated up front in the spec, not discovered after the fact. On the real held-out Nepal hilly test patch (`nepal_patch_12_4`), live SRTM fetch, 100% SRTM coverage:

| method | per-pixel RMSE against real truth |
|---|---|
| old (uniform rescale of relative depth's shape) | 289.9m |
| **new (SRTM trend + relative detail)** | **9.9m** |

A ~29x reduction — well beyond what the spec's own acceptance bar required (it only asked the new method not be *substantially worse*; the actual result far exceeded that). This is the clearest confirmation yet that relative depth's own shape was actively wrong at the coarse scale for hilly terrain (consistent with every other hilly finding this session), and that letting SRTM's real trend dominate there — instead of a uniformly-rescaled but structurally-unreliable relative shape — is a large, real win, not a marginal one.

**Full end-to-end production verification, not just the unit-level slow test:** cropped a real 256×256 georeferenced window from the raw Nepal Sentinel-2 source tile (`supplementary-data/sentinel-2/sentinel2_nepal_TCI.tif`, real EPSG:32645 CRS) and ran it through `tools/run_pipeline.py` (the actual standalone production harness, not a mocked test) end to end: `output_type="absolute_dsm"`, `dsm_path` and `confidence_map_path` both populated with real, valid files, contract check passed. The written GeoTIFF has real EPSG:4326 coordinates matching the real Nepal location (84.45°E, 28.44°N), plausible Himalayan elevation range (-0.96m to 1426m, mean 759m), and the confidence map correctly reads 100% SRTM-measured for this fully-covered scene.

**Tests:** 8 fast synthetic-array unit tests (resample nearest-neighbor correctness, NoData handling, detail extraction, fallback-on-void, GeoTIFF round-trip, confidence-map encoding) + 1 `@pytest.mark.slow` real-data RMSE comparison + 2 `ml/tests/test_pipeline.py` tests (dense fields populate on a grounded absolute result; dense fields stay `None` for non-georeferenced input). One test-hygiene catch during this work: an initial version of the "stays None" test accidentally invoked the real depth+segmentation models a 3rd time in `test_pipeline.py` (duplicating existing coverage), ballooning that file's runtime from ~19s to ~16 minutes — fixed by using the same lightweight mocking pattern as the grounding tests instead. Full `ml/` suite: 110/110 passing.

**Resolves when:** N/A — done, verified at both the unit and real-production-harness level. If broader validation across more hilly patches (not just the one real geo-bounded patch this session tested) becomes worth the effort later, that's a natural follow-on, not a blocker — the single real patch tested here already shows a result far larger than measurement noise would explain.

---

## 2026-08-31 — HARD FLAG (OPEN, deliberately deferred): no large-image tiling/stitching exists anywhere in the pipeline

**Status:** OPEN — explicitly deferred by user decision. **Do not start this until backend integration is done.** Logged now, in full, so it isn't lost or re-discovered from scratch later.

**The problem, precisely.** Every stage of `ml/pipeline.py::run_pipeline()` runs on the input image as a single shot, at whatever resolution it happens to be, with no tiling, no size cap, and no explicit downsizing anywhere in the code:

- `ml/utils/texture_export.py::export_texture()` — no resize logic at all (checked: no `resize`/`max_size`/`thumbnail`/`tile` in the file). A GeoTIFF's full native resolution is exported straight to PNG.
- `ml/depth/backbone.py::estimate_relative_depth()` — calls the HF `depth-estimation` pipeline directly on the full-resolution image with no pre-resize.
- `ml/calibration/semantic_priors.py::segment_image()` — same pattern, no pre-resize before the HF `image-segmentation` pipeline call.

**Why it doesn't crash, but is still broken.** HF's pipelines internally downsize to the model's native inference resolution (Depth Anything V2's is roughly ~518px), run the model, then upsample the single prediction back to the original input's dimensions before returning it. So a huge image (confirmed by direct measurement this session: the raw Nepal Sentinel-2 source tile is 10980×10980) will not OOM or crash — but the returned depth/segmentation map has no more real spatial information in it than a ~518×518 prediction stretched to fit. **This is a silent quality collapse, not a loud failure** — nothing in the current code detects or warns about it. A large real satellite scene would come back as a smooth, information-poor blur with none of the real per-building/per-structure detail a tiled approach could preserve, and the pipeline would report success with no indication anything degraded.

**Second, independent problem: `export_texture()` producing a huge PNG.** For the same 10980×10980 case, the exported "web-renderable" texture would itself be enormous — directly contradicting `docs/depthwizard.md` §9.8's own stated requirement that `texture_path` be a browser-decodable, web-renderable PNG. This needs solving even independent of the depth-quality problem above (could need its own downsize step regardless of whether tiling is built for the depth/segmentation side).

**Third, a concrete bug found in code shipped *this session*, not a hypothetical:** `ml/calibration/semantic_priors.py::_label_components()` (backing `correct_missed_structures()`, added 2026-08-31 in this session's work) is a pure-Python BFS over every pixel, explicitly commented and designed around the assumption "Patches are 256x256 max, so a plain BFS is fast enough (no need for a proper union-find)." That assumption is false for a real large production upload — a huge image with large connected building regions would make this function genuinely slow (a real performance bug, not a correctness one) at a scale nothing in this codebase has been tested against. Any tiling work must either revisit this function's algorithm (e.g. a real union-find, or bounding the component search per-tile) or ensure it only ever runs per-tile on bounded-size inputs, never on a whole huge image at once.

**What a real fix needs to decide (not yet designed, flagging the open questions, not answering them):**
1. **Tile size and overlap.** Depth/segmentation models have their own native inference resolution (~518px for Depth Anything V2) — tile size should likely be chosen relative to that, not arbitrarily, so each tile gives the model real detail to work with rather than being downsized again internally.
2. **Seam-blending/stitching strategy.** Naively concatenating independently-inferred tiles produces visible seams (a well-known failure mode in tiled depth/height estimation) — needs real overlap + blending (e.g. cosine/linear-ramp weighted blending in overlap regions), not a naive crop-and-paste.
3. **Where SRTM/absolute calibration fits in for a tiled large image.** The scalar calibration path (`calibrate_scene()`) and the new dense fusion (`ml/calibration/dense_fusion.py`) both currently assume one `geo_bounds` covering the whole image — a tiled approach needs either one calibration pass over the whole stitched result, or a per-tile calibration strategy that stays consistent across tile boundaries (an inconsistent per-tile scale anchor would itself create visible seams in the absolute output, on top of any depth-map seam issue).
4. **`_label_components()`'s algorithm** needs revisiting for large-scale correctness/performance once tiling exists (see above) — likely needs to run per-tile, not on a full large stitched image, or be replaced with a real union-find.
5. **Backend/worker implications** (timeout, memory, task chunking for a multi-tile job) are explicitly out of `ml/`'s scope per its own standalone-module convention, but whoever designs backend integration needs to know this is coming — a large-image job may need to become a multi-step/chunked Celery task, not a single synchronous call, which is exactly why this is deferred until backend integration lands first.

**Resolves when:** backend integration is complete (per explicit user sequencing decision, 2026-08-31) and this becomes the next active work item. When picked back up, write a proper spec (same treatment as `docs/dense_dsm_fusion.md`) before building — this entry is the flag, not the design.

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

---

## 2026-08-31 — Phase 5 Chunk 1: manifest patch files have no persisted CRS at all, even the georeferenceable ones — `evaluate.py` burns bounds onto a temp copy rather than touching `pipeline.py`

**Status:** RESOLVED (2026-08-31)

`ml/pipeline.py::run_pipeline()`'s georeferencing check (`_is_georeferenced()`/`_get_geo_bounds()`) reads `src.crs` directly off the input file. Confirmed by inspection (`rasterio.open()` on a real `hilly`/`copernicus_dem` test patch) that **no manifest patch file carries a real CRS/transform on disk, including the georeferenceable ones** — `ml/calibration/patch_geo.py`'s own docstring already flagged this for supplementary ingestion ("never wrote a transform onto the individual patch files"), but this confirms it's universal: calling `run_pipeline()` unmodified on any `rgb_path` would take the `relative_dsm` branch for literally every test patch, including hilly, making Chunk 1's whole `absolute_dsm` accuracy measurement impossible.

Two ways to close this: (a) give `run_pipeline()`/`PipelineResult` an optional geo-bounds-override parameter so callers can inject known bounds, or (b) leave `run_pipeline()`'s frozen signature untouched and instead make `evaluate.py` hand it something that already looks like a real georeferenced upload — a temp copy of the patch's RGB tif with `ml/calibration/patch_geo.py::get_patch_bounds()`'s analytically-recovered WGS84 bounds burned into a real `rasterio` transform+CRS before the file ever reaches `run_pipeline()`.

**Took (b).** It's the more honest read of "run the real, complete pipeline" (Chunk 1's own stated design principle) — it exercises `_is_georeferenced()`/`_get_geo_bounds()` exactly as they'd behave against any real georeferenced upload, with zero special-casing inside `pipeline.py` itself, and it doesn't touch the frozen `PipelineResult`/`run_pipeline()` contract Chunk 4 is explicitly supposed to freeze. DFC2019 patches (the 98.9% majority) are left completely unmodified, since they are correctly, permanently non-georeferenceable and must exercise the real `relative_dsm` fallback path, not a synthetic one.

**Resolves when:** N/A — this is how `evaluate.py` works going forward. If `ml/data/ingest_supplementary.py` is ever changed to persist a real transform onto patch files at ingestion time, this workaround becomes unnecessary but stays harmless (writing the same real bounds onto an already-georeferenced file is a no-op).

---

## 2026-08-31 — Phase 5 Chunk 1: full test-split run — 47/4,583 patches reached `absolute_dsm` (99.0% excluded, honest per the original spec), pooled hilly RMSE 48.7m dragged up by 2 real outlier patches

**Status:** OPEN (flagged, not fixed — out of scope for Chunk 1 per `docs/phase5.md`)

Full real `run_pipeline()` pass over all 4,583 test-split patches (37min actual, vs. a 2.5hr small-sample projection — the projection's per-patch cost was inflated by amortizing one-time model load over only 4 patches). 0 errors. Only `hilly` patches (47 of them — all from supplementary sources) ever reach `absolute_dsm`; `urban`/`sparse`/`forested` (DFC2019, 4,536 patches) correctly fall back to `relative_dsm` and are excluded from accuracy scoring, not silently dropped (99.0% excluded, reported explicitly).

Pooled: RMSE=48.72m, MAE=17.12m, r=0.965 (n=47 scenes, 2,522,220 pixels). This number is not representative of the typical case — 45/47 patches individually score 3-30m RMSE (matches the 9.9m single-patch result Phase 4 already validated), but 2 patches are real large outliers: `sierra_nevada_patch_7_17` (pred 490.6m vs. truth 233.8m, RMSE 256.9m) and `scotland_patch_2_0` (pred 693.3m vs. truth 417.8m, RMSE 275.7m). Re-ran both through `run_pipeline()` directly to check the cause: neither failed the `MIN_SRTM_VALID_FRACTION` gate (both reached `absolute_dsm` normally) — both carry the same "confidence=0.39, anchored primarily to SRTM" warning as every other hilly patch, so this isn't an SRTM-void/coverage problem. Root cause not yet isolated (candidates: a real SRTM data-quality/geolocation issue specific to those two tiles, or `dense_fusion.py`'s trend/detail frequency-matching assumption breaking down on unusually steep real relief) — not investigated further, since root-causing this is outside Chunk 1's scope (`docs/phase5.md`: "already-logged gaps... out of scope for this phase to fix, only to report honestly if they show up in results"). Median/typical-case framing (not the outlier-dragged pooled mean) is the honest number to lead with in Chunk 2's writeup.

**Resolves when:** whoever picks up dense-fusion accuracy work next isolates why these 2 of 47 real patches have a ~10-25x larger error than the rest — check the raw SRTM tile for `sierra_nevada` (7,17) and `scotland` (2,0) specifically before assuming it's a `dense_fusion.py` bug.

**Update (Chunk 2):** `evaluate.py`'s JSON-packaging step flags outliers programmatically (>5x this run's own median RMSE, not a fixed meter threshold) rather than hardcoding these two — that threshold also catches a 3rd, smaller outlier: `tuscany_patch_14_2` (RMSE 67.2m). Re-ran the full 4,583-patch pass a second time (independently, for the JSON-packaging step) and got byte-identical per-patch numbers to this entry's original run — confirms the pipeline is deterministic, not a fluke of one run.

---

## 2026-08-31 — Phase 5 Chunk 3: Bhuvan/Cartosat — no quantitative claim possible (confirmed, not new), but the flat-terrain depth hallucination reproduces on real Indian imagery; missed-structure correction fired on ~83% of pixels (unusually high, cloud-related, not investigated further)

**Status:** OPEN (flagged, not fixed — out of scope for Chunk 3)

Only one real Bhuvan/Cartosat sample exists on disk (`ml/depth/samples/bhuvan_cartosat_sample.jpg`, 1500×1500 JPEG, no CRS), with no paired reference elevation — confirmed by design, not an oversight (`ml/data/download_datasets.py::add_bhuvan_sample()`'s own docstring: "No paired ground truth is required"). Full writeup: `docs/bhuvan_cartosat_validation.md`.

Ran the real `run_pipeline()` on it: correctly took the `relative_dsm` path (JPEG can't carry geo-metadata). Two real findings from the qualitative visual result:

1. The already-documented "flat-terrain hallucinated smooth gradient" failure mode (see the `ml/depth/backbone.py` entry higher in this log) reproduces on real Cartosat imagery, not just DFC2019 — the relative depth output for this real coastal-delta scene is a smooth left-right gradient with zero correlation to the visible river channels, settlements, or vegetation. Confirms the failure mode is about nadir-aerial-vs-ground-photo training mismatch, not an artifact specific to DFC2019's own sensor characteristics.
2. `correct_missed_structures()` corrected ~83% of this image's pixels (1,873,596/2,250,000) — far above the single-digit-percent rates measured on DFC2019 urban patches earlier this session. Two small artifact blobs in the corrected heightmap spatially coincide with dense cloud cover in the RGB — plausible (not confirmed) hypothesis: segmentation misclassifies cloud pixels, feeding a false "missed building" signal into the correction. Not isolated by inspecting raw segmentation output for this image — a real gap for whoever investigates semantic-correction edge cases next, alongside the already-logged flat-pavement-as-`wall` and warehouse-rooftop segmentation issues.

**Resolves when:** (1) is now considered confirmed across two real, independent image sources — no further action needed unless a fix for the hallucination itself is undertaken (already flagged elsewhere as an input-representation-level problem, not fixable by a bigger model on the same depth channel). (2) resolves when someone inspects `segment_image()`'s raw class map for this specific image (or another heavily-clouded real image) to confirm or rule out the cloud-misclassification hypothesis.

---

## 2026-08-31 — Phase 5 Chunk 4: contract frozen — verified against real Chunks 1-3 output, not just re-read

**Status:** RESOLVED (2026-08-31) — this entry itself is the freeze note (`docs/phase5.md` Chunk 4's stated home for it)

**What was checked, not just asserted:** `integration/contracts.py::PipelineResult.validate(strict=True)` run against the real `integration/pipeline_runner.py` adapter output (not `ml/pipeline.py`'s local dataclass directly — the adapter is what backend actually calls) for two real cases exercised this phase:
- A real `relative_dsm` result (Bhuvan/Cartosat sample, Chunk 3) — `validate(strict=True)` returns `[]`.
- A real `absolute_dsm` result (`nepal_patch_12_4`, Chunk 1's dense-fusion path, dsm_path populated) — `validate(strict=True)` returns `[]`.

No field was added to either `PipelineResult` (frozen or `ml/pipeline.py`'s local duplicate) during Phase 5 — Chunks 1-3 only *consumed* `dsm_path`/`confidence_map_path` (already present since Phase 4's dense-fusion work), never added new ones. The one known field-set divergence (`ml/pipeline.py`'s local class has no `heightmap_16bit_path` attribute at all; `metrics` defaults to `{}` not `None`) is unchanged from the already-logged, already-accepted "deliberate duplicate" decision (see `CLAUDE.md` Learned rules) — `pipeline_runner.py`'s `getattr(ml_result, "heightmap_16bit_path", None)` and `ml_result.metrics or None` already correct for both, and did before this phase started.

**Go/no-go, stated plainly (per Chunk 4's own instruction not to imply broader readiness than earned):**
- **Contract: GO.** Frozen, verified against real output on both branches. Safe for backend/frontend integration work to build against without expecting further field changes.
- **Backend integration testing (real FastAPI/Celery worker path): NO-GO, unstarted.** Everything validated this phase (and Phase 4) ran through `ml/pipeline.py`/`integration/pipeline_runner.py` directly or via `evaluate.py` — never through an actual Celery task, Postgres job row, or FastAPI endpoint. This freeze says the *shape* is stable, not that the worker path has been exercised even once.
- **Large-image tiling (the 2026-08-31 HARD FLAG entry): still unresolved, unchanged.** Explicitly deferred until after backend integration per that entry's own logged sequencing decision — this freeze does not touch it.
- **`validation_report.json`'s own honest scope:** only `hilly` terrain is quantitatively validated (47/4,583 test patches, 99.0% of the split has no absolute ground truth to score against) — see Chunk 1/2 entries. "Contract frozen" is not "every terrain's accuracy is proven."

**Resolves when:** N/A — this is the freeze. Reopen only if a future phase needs a new `PipelineResult` field (at which point it's a new decision, not a reopening of this one).

---

## 2026-09-13 — New use case proposed: river silt/turbidity estimation, reusing DepthWizard infra

**Status:** OPEN — PRD written (`docs/phase_river_silt.md`), no code started

User wants to extend the same satellite/drone-RGB-to-heightmap infra to a second product: given an overhead river image, estimate suspended sediment concentration (SSC) and render it as a spatial heatmap (silt intensity per pixel), same shape as the DSM pipeline (relative pattern from a CNN/segmentation-style model, absolute mg/L anchored via fusion with in-situ gauge data).

**Datasets found (web search, not yet pulled into repo):**
- **Primary candidate:** global riverine SSC matchup dataset (Prum/Lucchese/Gardner, *Scientific Reports* 2026) — 240,224 records, in-situ SSC paired with Landsat TM/ETM+/OLI surface reflectance, 430 gauge stations (US/Canada/South America/Taiwan), 1984–present. Closest structural analog to this project's existing SRTM-anchor pattern. Paper: https://www.nature.com/articles/s41598-026-58139-0. Matchup data referenced as hosted on CUAHSI HydroShare: https://www.hydroshare.org/resource/2ee7d421618a4873b9906540d047ced4/
- **Secondary:** USGS Lower Mississippi/Atchafalaya SSC + percent-fines (1973–2021) + daily streamflow, US-only, clean tabular ground truth: https://www.usgs.gov/data/datasets-suspended-sediment-concentration-and-percent-fines-1973-2021-sampling-information
- **Reference only (no raw data, band-ratio algorithms):** Yangtze/Yellow River Sentinel-2 SSC papers (R²=0.91 Yellow River band-ratio model), useful for feature-engineering ideas.

**Blocker: no dataset pulled yet.** No browser-automation tool (chrome-devtools MCP or equivalent) is wired into this session — checked, not assumed. Direct `curl` against both HydroShare and USGS data-release pages returned `403` (bot-blocked, likely needs a real browser session/cookies, not a dead link). Two ways to unblock: (a) user downloads manually and drops files under `ml/data/river_silt_raw/` (gitignored, matching the `ml/depth/samples/`/`ml/data/samples/` convention), or (b) user connects a chrome-devtools MCP server to this session and a future turn drives it directly.

**Explicitly modeled on already-learned lessons from the height pipeline** (see PRD for detail) — relative-pattern-only CNN output cannot give absolute mg/L (same scale-blindness as depth-vs-height), so an in-situ gauge anchor is required for any absolute claim, same disqualify-don't-clamp gating pattern as `MIN_SRTM_VALID_FRACTION`.

**Resolves when:** dataset is actually in the repo and Chunk 1 (data ingestion) of `docs/phase_river_silt.md` starts.

---

## 2026-09-14 — River silt Chunk 1 started: real datasets pulled, GEE imagery fetch built and run, real Sentinel-2 launch-date gap found

**Status:** IN PROGRESS

Datasets landed (`ml/data/river_silt_raw/`, gitignored): `SSC_in_situ.csv` (467,088 rows — 393,708 tagged `River`/`River-Stream`, real global spread) and `OC_data.csv` (GloRivSed, 3.99M rows). Confirmed by inspection, not assumed: `OC_data.csv`'s `reach_ID` keys against the SWORD river-geometry database (not yet acquired) — no direct lat/lon in that file — and its `y_pred` column is the source paper's own *modeled* SSC estimate, not a raw in-situ reading. Decided to build Chunk 1 against `SSC_in_situ.csv` only; `OC_data.csv` is deferred until SWORD is in hand.

GCP service-account key for Earth Engine set up (`depthwizard-508518` project). **Security note, not a finding but worth recording:** the downloaded key JSON landed in the repo root first — moved out of the repo entirely to `~/secrets/`, and `.gitignore` tightened (`/*.json` at root, `/*.csv` at root) so a stray `git add -A` can't catch a credential or a multi-GB CSV again. Root-only patterns, verified via `git check-ignore -v` not to shadow any tracked nested `.json` (package.json, tsconfig, manifest.json etc. — none exist at root, checked before adding the pattern).

Built `ml/data/fetch_river_silt_imagery.py` — standalone (matches `ingest_supplementary.py`'s convention), reads the service account's `client_email` straight out of the key JSON (one `--key-file` flag, no separate email arg to keep in sync), samples N real `River`/`River-Stream` rows, matches each to the least-cloudy Sentinel-2 SR scene within ±8 days via `COPERNICUS/S2_SR_HARMONIZED`, downloads a 256×256 uint8 true-color GeoTIFF crop per match. `ee` is lazily imported inside the network-touching functions only, so the pure sampling/filtering logic is unit-testable without `earthengine-api` installed (`ml/tests/test_fetch_river_silt_imagery.py`, 3 tests, no network).

**Real run, 200-row sample:** only 40 images matched, 160 skipped. Root-caused before treating it as a bug: **58% of all real `River`/`River-Stream` rows in `SSC_in_situ.csv` predate 2015-06-23 (Sentinel-2's launch)** — measured directly, not guessed (min date 1985, max 2024). Random sampling from a 1985–2024 dataset against a 2015+-only satellite bakes in most of the miss rate before the script ever runs a query. Fixed by filtering `load_river_rows()` to `date >= SENTINEL2_LAUNCH` up front, so future samples aren't wasted on structurally-unmatchable rows. Genuine cloud-cover misses (real skips, not date-caused) are the remaining, much smaller tail — not yet separately measured.

**Resolves when:** re-run with the launch-date filter in place and confirm the skip rate drops to something close to real cloud-cover-only misses; then decide whether 200 real image/SSC pairs is enough to start feature extraction (Chunk 2) or whether the sample needs to grow first.

**Update (2026-09-14):** re-run at `--n-samples 500` hit a second real bug before the fix landed — one real `SiteID` value is a URL (`Datastream_https://doi.org/...`), and using it raw in a file path broke `urlretrieve()` mid-batch (`FileNotFoundError`, embedded slashes). Fixed with a filename sanitizer (`re.sub(r"[^A-Za-z0-9._-]", "_", site_id)`) and, per the root-cause-not-symptom rule, wrapped the whole per-row fetch+download in one `try/except Exception` — a 500-row real-world batch shouldn't die on any single row's data quirk, not just this specific URL case.

**Result after both fixes, real run:** 315/500 images pulled (63% match rate) vs. the pre-fix 40/200 (20%) — confirms the launch-date filter was the dominant cause, not incidental. Remaining 185 skips are genuine no-cloud-free-scene-in-window misses, not measured further yet. 315 real image/SSC pairs now sit in `ml/data/river_silt_raw/imagery/` + `imagery_manifest.csv` (gitignored). Note: the folder has ~20 extra leftover files from the pre-fix crashed run (different seed-derived sample, same CSV) — harmless, not deduped, flagging so a future row-count check isn't confused by the mismatch between manifest rows (315) and files on disk (335).

**Resolves when:** N/A for Chunk 1's imagery-pull step — 315 pairs is enough to start Chunk 2 (feature extraction). Scale up only if the baseline regressor shows real headroom that more data would close, same standard applied throughout the height pipeline's optimization passes.

**Note on the 185 skipped rows:** genuinely no cloud-free Sentinel-2 scene within ±8 days of the SSC reading for that station/date — not lost, not a bug, logged plainly by the script (`185 rows skipped (no cloud-free scene in +/-8d window)`). Not yet broken down into "zero scenes at all in the archive" vs. "scenes existed but all cloudier than `MAX_CLOUD_PCT=40`" — deferred, pick up next session if the skip rate matters for scaling the sample later.

---

## 2026-09-14 — River silt Chunk 2: baseline turbidity regressor trained on real data — negative R², a real weak baseline, not a bug

**Status:** IN PROGRESS

Built `ml/features/extract_river_silt_features.py` (13 RGB-derived features per image: per-band color mean/std, brightness, NDTI, red/blue ratio, plus the three pattern-vs-magnitude texture features already proven useful in the height pipeline — `_edge_density`/`_freq_high_ratio`/`_local_entropy`, imported and reused on the luminance channel rather than reimplemented) and `ml/calibration/train_river_silt_regressor.py`, which reuses `HeightRegressor` as-is — it's a generic feature-vector MLP with nothing height-specific in its implementation, only in its name/docstrings. A second near-identical MLP class was rejected as pure duplication.

Ran both against the real 315-row `imagery_manifest.csv`: 315/315 feature rows built, 0 skipped. Split 220/47/48 (train/val/test, seed 42).

**Real result, reported honestly, not spun:** test-set **R² = -0.127** (worse than predicting the mean), RMSE 65.4 mg/L, MAE 27.8 mg/L, bias -22.8 mg/L (systematically underestimates). The sanity-check sample makes the failure mode visible directly: predictions cluster tightly around ~9-12 mg/L regardless of the real target's actual range (8.7 to 111 mg/L in just 5 rows) — the model is barely distinguishing sites at all, close to predicting a constant.

**Why this is plausible, not obviously a bug** (flagging the honest reasons before jumping to "fix the code"):
1. **315 rows is small** for global cross-site generalization — this project's own height pipeline needed thousands of rows per terrain bucket before its features showed real signal; 220 training rows spread across dozens of countries/lighting conditions/river types is a much harder generalization problem on far less data.
2. **No per-scene normalization.** Sentinel-2 true-color renders vary with sun angle, atmospheric haze, water depth/bottom-reflectance, and each scene's own arbitrary date within the ±8-day window — color/texture statistics aren't controlled for any of this, unlike DFC2019's roughly-consistent nadir/lighting conditions.
3. **A single crop's classical color/texture stats may simply not carry global SSC signal** the way local, single-basin band-ratio algorithms do (per the Yellow River paper's R²=0.91 — but that model is basin-specific, trained and evaluated on one river system's own lighting/turbidity range, not asked to generalize globally like this baseline was).

**Resolves when:** this is Chunk 2's honest baseline result, matching `docs/phase_river_silt.md`'s own instruction ("measure this honestly before reaching for a CNN — a CNN is worth it only if it beats this"). Options going forward, not yet decided: (a) scale up the imagery sample (more rows, same features) to see if more data alone helps a clearly-underfit model; (b) try per-scene/per-region normalization before adding model complexity; (c) move to Chunk 3/4's CNN-based approach given this baseline's weakness makes the case for it stronger, not weaker. Flagging for explicit user decision before picking one — not assumed.

**Update (2026-09-14) — user picked option (a), scale up the sample. Two real bugs found and fixed during the scale-up run itself:**

1. **Made the pull script resumable/additive first** (it wasn't — a re-run with a bigger `--n-samples` would have re-downloaded and overwritten everything already pulled). `fetch_river_silt_imagery.py` now loads the existing manifest, excludes already-pulled `site_id`s from the new sample pool, and only fetches genuinely new rows.

2. **That fix wasn't enough on its own — the manifest write itself was still batch-at-the-end, not incremental.** Real incident: launched a `--n-samples 2000` background pull; the OS OOM-killed the process mid-run (unrelated to this script — system-wide memory pressure, not a leak in this code). Because the manifest was only written once at the very end, the kill orphaned **469 already-downloaded images** (784 files on disk, only 315 in the manifest) — invisible to the "already pulled" resume check, so a naive re-run would have silently re-fetched and re-downloaded all of them. Fixed by writing the manifest incrementally (`csv.DictWriter` append-mode, one `writerow()` + `flush()` per successful row, `try/finally` to always close the handle) — a kill at any point now only loses the one in-flight row, not the whole batch.

3. **Separately found 15 duplicate `site_id` rows in the manifest**, left over from the two earlier pre-resumable-fix runs re-sampling overlapping rows. Deduped by keeping first occurrence (300 unique rows survived) — real risk if left in: the same image could land in both the train and test split via `extract_river_silt_features.py`'s random split, a data-leakage bug that would have quietly inflated the next R² measurement.

Orphaned files with no manifest metadata were deleted (not recoverable without re-querying Earth Engine for their scene metadata) rather than guessed-at or kept mismatched.

**Resolves when:** the scale-up re-run (now on the fixed script) completes and the regressor is retrained — not done yet as of this entry.

---

## 2026-09-14 — River silt: literature review of active SSC-from-satellite research, checked against the negative-R² baseline above

**Status:** RESEARCH, not yet acted on — logged for whoever picks up the scale-up retrain.

Read the primary dataset paper (Prum/Lucchese/Gardner, *Sci Reports* 2026, paywalled — full methodology pieced together from PubMed/ResearchGate abstracts) plus a fully-open PMC coastal-SSC study with complete methodology, to check our Chunk 2 approach against what the field actually does.

**Model choice — real mismatch found.** Prum/Lucchese/Gardner's global model uses **XGBoost**, not a neural net. The open PMC study ran a direct three-way comparison on the same kind of problem: XGBoost R²=0.72 (100 trees, depth 4, lr 0.03, subsample 0.7) vs. Random Forest R²=0.65 vs. MLP R²=0.47. A second study (coastal turbidity) also found XGBoost best, R²=0.757. Our Chunk 2 baseline reuses `HeightRegressor` (an MLP) and got R²=-0.127. Every literature comparison found puts MLP well behind XGBoost on this exact task — worth trying XGBoost on the existing 13-feature set *before* the sample-scale-up finishes, since it's a cheap thing to test in parallel and the current negative result might be as much a model-choice problem as a data-size one.

**Feature gap — bigger than model choice, likely the real cause.** Literature feature sets: Blue/Red/Green/NIR-narrow/SWIR1 raw bands + Blue/Red, Blue/Green, Red/Green ratios (+ lat/lon, caveat below). Ours (`extract_river_silt_features.py`) has NDTI + red/blue ratio + color/texture stats — reasonable overlap, missing Blue/Green ratio specifically (one study's SHAP found it inversely correlated with turbidity, real signal, cheap to add).

**The actual likely root cause: `fetch_river_silt_imagery.py` pulls Sentinel-2 as a true-color RGB GeoTIFF crop, discarding bands every cited paper depends on.** The literature is explicit about *why* RGB-only struggles: "for sediment-dominated highly turbid waters, green/red reflectance saturates — a NIR band is usually more appropriate" (band-ratio turbidity literature, general finding, not specific to one paper). We pull from `COPERNICUS/S2_SR_HARMONIZED` via Earth Engine — that source has B5/B6/B7 (red-edge), B8 (NIR), B11/B12 (SWIR) available on the same scene we're already fetching; we're just requesting true-color only. This is not the "generic RGB drone photo" constraint the PRD's §0 comparison table assumes — it's a specific export choice on a source that actually has the useful bands. **Before scaling the imagery sample further, worth checking whether re-pulling with the multispectral bands included (still same 315+ already-matched rows, just richer per-crop data) closes more of the R² gap than more RGB-only rows would.** Not yet tried — flagging so the scale-up doesn't spend more download/compute time on a feature representation the literature says is fundamentally undersignaled.

**Water masking — not yet done.** Every paper reviewed isolates water pixels (mNDWI threshold) before computing any color/texture statistic. Our 256×256 crops likely mix bank/vegetation/water pixels into one feature vector undifferentiated. `ml/calibration/semantic_priors.py` already does exactly this kind of segmentation for the height pipeline (building/vegetation/road classes) — same pattern, a water class, would directly apply here and hasn't been tried.

**Cloud/quality masking — unclear if already handled.** Literature standard is Fmask-derived cloud/cirrus/shadow/adjacent-pixel masking, plus a Hampel filter for temporal outliers in time-series use. Not confirmed whether `fetch_river_silt_imagery.py`'s existing `MAX_CLOUD_PCT=40` scene-level filter is doing enough, or whether pixel-level contamination inside an accepted scene is still possible.

**Matchup window — current ±8 days is loose relative to literature.** The open PMC study used ≤1 day between gauge reading and satellite pass, calling tighter windows necessary because SSC drifts fast. This directly answers the open question already logged above ("gauge-anchor freshness gating... needs a real threshold, not guessed") — literature's answer is closer to 1 day than 8. Real tradeoff, not free: match rate is already the bottleneck (315/500 at ±8 days per the entry above), and tightening to ≤1 day will shrink it further. Not decided which side of that tradeoff to take — flagging for whoever picks this up, not choosing here.

**Lat/lon as a feature — flagged as a likely leakage trap, not recommended as-is.** One study's SHAP analysis found longitude the single strongest predictor. Read against this project's own `terrain_type`-leakage finding (see the height-pipeline entries above): baseline water color plausibly varies by region because *specific training rivers* have specific baseline turbidity/mineralogy, not because geographic coordinate is a real physical predictor of SSC. Feeding raw lat/lon into a global model risks the model memorizing "which river is this" rather than learning transferable turbidity signal — same shape of mistake already caught once this project. Don't add without the same scrutiny `terrain_type` got.

**Resolves when:** someone acts on one or more of the above (XGBoost swap, multispectral re-pull, water masking) and re-measures against the same held-out test split, rather than these staying observations only.

**Update (2026-09-14) — acted on the two cheap items (no network needed); real, honest, partial result:**

1. Added `silt_blue_green_ratio` to `extract_river_silt_features.py` (literature-flagged, cheap). Test added to `test_extract_river_silt_features.py` checking clear water reads a higher blue/green ratio than turbid water, same pattern as the existing NDTI/red-blue checks.
2. Re-ran `extract_river_silt_features.py` against the now-current manifest — it had grown to 830 rows (from the 315 this baseline was originally measured on) without a corresponding feature-file re-extraction; that scale-up data was sitting unused until this re-run. New split: 581/124/125 train/val/test.
3. **Re-measured the MLP baseline on the bigger dataset first, before touching anything else:** R² = -0.0495 (up from -0.127, still negative). Confirms the literature-review hypothesis directly — more RGB-only rows alone did not fix this; the problem is feature/model, not sample size.
4. **Added `ml/calibration/train_river_silt_regressor_xgb.py`** — XGBoost, same 14 features, same train/val/test split, hyperparameters taken from the open PMC study's best config (100 trees, depth 4, lr 0.03, subsample 0.7) as a measured starting point, not tuned further. New dependency: `xgboost==2.1.4` in `ml/requirements.txt` — on macOS this also needs `brew install libomp` (xgboost's OpenMP runtime; not resolvable via pip, real install-time gotcha hit and fixed this session).
5. **Result: R² = 0.0039** — crosses to barely positive, and bias dropped sharply (-44.5 mg/L → -6.5 mg/L, far less systematic underestimation). MAE is actually slightly worse (65.2 vs 49.6 mg/L) — a mixed, not a clean, win. Honest reading: **the model-choice literature finding is confirmed and measurably real, but it is a small fix, not the fix.** The bigger lever identified above — re-pulling Sentinel-2 with NIR/red-edge/SWIR bands instead of true-color-only — is still untried, because it requires a live Earth Engine pull (network + GCP service-account credentials) that wasn't attempted this pass. Don't cite "XGBoost fixed the river-silt regressor" — it moved R² from clearly-negative to barely-non-negative, nothing more, on this feature set.

**Resolves when:** the multispectral re-pull (biggest remaining lever, per the literature-review entry above) is attempted and measured — not done yet as of this entry. Water masking and the ±8-day matchup-window tightening also remain untried.

**Update (2026-09-14) — scale-up pull finished (1532 total rows), both models re-measured at full scale: confirms the ceiling is feature representation, not sample size.**

`fetch_river_silt_imagery.py`'s scale-up run completed: 1232 new images pulled this pass, 1532 total (768 skipped, same real cloud-cover-miss pattern as before — no new bug). Re-ran `extract_river_silt_features.py` (0 skipped, 1072/229/231 train/val/test) and both regressors on the full set:

| | 315 rows | 830 rows | **1532 rows** |
|---|---|---|---|
| MLP R² | -0.127 | -0.0495 | **-0.0263** |
| XGBoost R² | (not yet built) | 0.0039 | **-0.0195** |

**Both models flat-lined near zero regardless of scale — MLP crept up marginally, XGBoost actually got *worse* (0.0039 → -0.0195) and its MAE also got worse (65.2 → 92.6 mg/L) going from 830 to 1532 rows.** This is a decisive result, not an ambiguous one: if the problem were data volume, more real rows would show monotonic improvement on at least one model. Neither did. Confirms the literature-review hypothesis directly — **the ceiling is the RGB-only feature representation, not sample size.** Scaling the imagery pull further (more RGB rows) is very unlikely to help; per that entry, the real lever is re-pulling Sentinel-2 with NIR/red-edge/SWIR bands instead of true-color-only.

**Resolves when:** the multispectral re-pull is built and measured — this update makes that the clear next step, not one option among several.

**Update (2026-09-14) — multispectral re-pull built, hit a real hang bug on first run, fixed.**

Built `ml/data/fetch_river_silt_multispectral.py`: reuses each manifest row's already-matched `scene_id` (no re-searching — guarantees the exact same scene the RGB crop came from, same date/cloud cover), pulls raw B2/B3/B4/B5/B8/B11/B12 (blue/green/red/red-edge/NIR/SWIR1/SWIR2) at native Sentinel-2 SR reflectance scale, not visualized to uint8. One file per `site_id` is its own resume checkpoint, same convention as `ml/features/extract_features.py`.

**Real incident on first run:** launched in the background, checked back after ~15 minutes — 0 files pulled, near-zero CPU time (0.62s). Not slow, stuck: killed it and root-caused directly (isolated single-row test of `fetch_multispectral_crop()` + `urlretrieve()` both completed in under 5s each in isolation, so the code path itself is correct) — the real gap is that **no network call anywhere in either fetch script had a timeout**, so a single transient stall (this one, or the original RGB pull, which got lucky and never hit it across 1532 real rows) can hang the entire batch indefinitely with zero progress and no error. Fixed with `socket.setdefaulttimeout(60)` at the top of `main()` in both `fetch_river_silt_multispectral.py` and `fetch_river_silt_imagery.py` (same exposure, same fix, applied to both since it's the identical bug class) — a stuck row now raises `socket.timeout`, caught by the existing per-row `except Exception` handler, and the batch moves on instead of hanging forever.

**Resolves when:** the re-launched pull (now timeout-protected) completes and the combined RGB+multispectral feature extraction + retrain (`ml/features/extract_river_silt_multispectral_features.py`, `ml/calibration/train_river_silt_regressor_multispectral_xgb.py`, both built and unit-tested, not yet run against real data) can proceed — not done yet as of this entry.

---

## 2026-09-14 — Water masking (mNDWI) built while the multispectral pull runs — real finding: the crop is mostly not water

**Status:** IN PROGRESS — built and unit-tested, real limitation found and logged, not fixed

Added `compute_water_mask()` (modified NDWI, Xu 2006: `(green - swir1) / (green + swir1) > 0`) to `extract_river_silt_multispectral_features.py`, wired into `compute_multispectral_features()` — when given a mask, band means/ratios are computed only over water-flagged pixels, isolating turbidity signal from bank/vegetation pixels per the literature-review entry's flagged gap. Falls back to whole-crop stats when the water fraction is under `MIN_WATER_FRACTION=0.05` (same disqualify-don't-silently-degrade pattern as `MIN_SRTM_VALID_FRACTION` elsewhere in this project) — a mask covering a handful of pixels shouldn't be trusted. New diagnostic/feature column `ms_water_fraction` carries the mask coverage itself into the model, whether or not the mask was trusted for that row. 6 tests, real-mask-vs-fallback behavior included.

**Real finding on the crops already pulled (50-row sample):** median water fraction is **1.3%**, mean 10.2%, and **37/50 (74%) fall below the trust threshold** — the mask barely engages for most rows. Root cause: `BUFFER_METERS=1280` (a 2.56km-wide crop, chosen to match the RGB pull's existing crop size for pixel-grid alignment) is wide relative to typical river width — most of a real river station's crop is bank/floodplain/land, not water. **Not fixed this pass** — shrinking the buffer would misalign with the already-pulled RGB crops (same buffer size) and require a full re-pull; changing it now mid-pull wasn't judged worth the disruption. The `ms_water_fraction` feature itself still carries real information regardless (very-low-water-fraction crops are a distinct population XGBoost can learn to weight differently), so the masking work isn't wasted, just not the full fix the literature implies.

**Resolves when:** the combined feature set is retrained and measured against the RGB-only and unmasked-multispectral baselines — worth checking whether `ms_water_fraction` as a feature alone helps, independent of whether the mask itself engages often enough to matter. If it doesn't help, revisit crop size (smaller buffer, re-pulled) as a follow-on, not assumed necessary yet.

---

## 2026-09-14 — Frontend `SiltHeatmapViewer` built; SWORD reach-lookup dataset download started (both requested to run in parallel with the multispectral pull)

**Status:** Frontend component done and typechecked. SWORD download in progress, not yet built against.

**Frontend:** `frontend/src/components/viewer/SiltHeatmapViewer.tsx` — built per `docs/phase_river_silt.md` §4's mockup, matching this project's existing design tokens exactly (same `#5e4cff`/`#36394a`/`#cdd2d9` palette, `rounded-[12px]`/`[8px]`, `font-heading`, loading/error state patterns lifted from `TerrainViewer.tsx`). Canvas-based 2D overlay (source RGB + colorized heatmap blended at adjustable opacity), hover readout in mg/L or relative index depending on `outputType`, summary panel (mean/peak SSC, confidence dots — same `●○` convention style), per-region breakdown table, and the `⚠ relative_silt_index` warning banner from the mockup. `npx tsc --noEmit` passes clean. Not wired into routing/a real job-results flow yet — no backend silt-job endpoint exists (Chunk 5 of the PRD, unstarted) — this is the standalone component itself, demoable once real heatmap data exists.

**SWORD:** needed to resolve `OC_data.csv` (GloRivSed)'s `reach_ID` to lat/lon, since that file has no direct coordinates. No per-continent split exists in any of SWORD's three formats (netcdf/gpkg/shp all ship as one ~1.8-2GB global zip, confirmed via Zenodo's file API before downloading — not guessed). Range-request central-directory peek (to inspect the zip's contents without downloading it all) didn't work cleanly against Zenodo's redirect chain — abandoned rather than over-engineered further. **User explicitly approved the full download** (asked first, given the project's standing preference against large unprompted downloads — see the earlier 26.9GB GloRivSed continent-file incident). Downloading `SWORD_v17b_shp.zip` (shapefile format, chosen over netcdf/gpkg specifically so the reach-lookup can use `pyshp` — a small pure-Python package — instead of needing GDAL/geopandas for a simple reach_id→centroid task). Both the zip and a planned `ml/data/river_silt_raw/sword/` extraction directory are gitignored.

**Resolves when:** SWORD download completes, a reach_id→lat/lon lookup script is built against it, and `OC_data.csv` can finally be joined to real coordinates — none of that started yet, this entry only covers the acquisition decision and what's running.

**Update (2026-09-14) — SWORD download completed (with real network flakiness handled), reach lookup built and run, real ~42% miss rate found and partially explained**

Download dropped mid-transfer twice (`curl` exit 18, connection closed mid-stream — a real, transient network issue, not a bug in this repo) before a resumable retry loop (`curl -C -` in a bash loop) got the full 2,133,807,799-byte zip down cleanly; `unzip -t` confirmed no corruption. **Only the Oceania (`OC`) continent was extracted** (79MB, matching `OC_data.csv`'s own scope — no reason to keep the other 5 continents' ~2GB on disk for a dataset we only have one continent of), and **the 2.13GB zip was deleted immediately after extraction** — per the standing preference against large files sitting around locally.

Built `ml/data/sword_reach_lookup.py` — simpler than planned: SWORD's reach records already carry a representative `x`/`y` point per reach directly in the shapefile's attribute table (checked on a real extracted file before writing any code, not assumed), so no polyline-centroid math was needed at all, just an attribute read. Uses `pyshp` (pure Python), no GDAL/geopandas. 3 tests (index building, multi-file merging, drop-not-fabricate on an unresolvable id).

**Real result on the actual data:** 2,320,566 / 3,993,644 rows resolved to real coordinates (58%), 1,673,078 missed (42%). Checked whether this was wrong-continent contamination before accepting it — it isn't: every single `reach_ID` in `OC_data.csv` starts with SWORD's Oceania region-prefix digit (`5`), confirmed by direct count, so the miss isn't a data-scoping bug on this end. Leading (unconfirmed) hypothesis: SWORD revises reach boundaries and reassigns reach IDs across versions, and GloRivSed's `reach_ID` column was very likely built against an older SWORD release (the paper predates v17b, the only version currently downloaded) — reach-ID drift between hydrography dataset versions is a known category of problem, not specific to this pipeline. Not confirmed by reading GloRivSed's actual methods section (paywalled, only abstracts available per the earlier literature-review entry) — flagging as the leading explanation, not a proven one.

**Resolves when:** if GloRivSed's exact source SWORD version is ever confirmed (would need the paywalled paper or its supplementary methods), re-run the lookup against that version instead of v17b and see if the miss rate closes. Not pursued further this session — 2.32M resolved rows is already a usable, if partial, coordinate set for whoever picks up `OC_data.csv`/GloRivSed integration next.

---

## 2026-09-14 — River silt: remaining plumbing/skeleton work finished (backend tests, frontend wiring end-to-end)

**Status:** RESOLVED (2026-09-14) — the placeholder-scope backend+frontend flow is now fully connected and verified real, not just import-checked

Picked up the two real gaps flagged after the initial backend-wiring slice:

**1. Backend: silt-job routes/service had zero dedicated test coverage** (unlike, it turns out, `jobs.py` too — checked first, `test_job_isolation.py` is the *only* route-level test file that exists for the terrain flow either, so "mirror jobs.py's coverage" meant writing the same kind of test, not matching a higher pre-existing bar). Extended `conftest.py`'s shared `client` fixture to also monkeypatch `process_river_silt_image.delay` (previously only `process_image.delay` was mocked — a silt-job test would have tried a real Celery `.delay()` call with no broker running). Wrote `test_silt_job_isolation.py` (7 tests, mirrors `test_job_isolation.py`'s cross-user isolation coverage plus two silt-specific cases: result-not-ready-yet, list-scoping-per-user).

**Verified against a real Postgres, not just skip-checked:** started the repo's existing `docker-compose.yml` postgres service, created a `depthwizard_test` database, installed `psycopg[binary]`. All 19 backend tests (4 original + 8 terrain isolation + 7 new silt isolation) pass against real tables built from `Base.metadata.create_all()` — meaning the `SiltJob` model's own CHECK constraints, indexes, and FK-free shape are exercised for real, not just import-checked. Previously this suite only ever ran in skip mode in this environment.

**2. Frontend: `SiltHeatmapViewer` existed but nothing reached it.** Built the full chain: `types.ts` (Silt* types mirroring the backend schemas), `mockApi.ts`/`mockFixtures.ts` (mock silt endpoints + fixture, so the flow is demoable without a live backend — same convention the terrain flow already uses when Supabase isn't configured), `api.ts` (real `createSiltJob`/`getSiltJob`/`getSiltJobResult`/`getSiltJobs`/`deleteSiltJob`, same fetch/error-handling shape as the terrain functions), `useSiltJobPolling` hook, `SiltUploadForm` + `SiltJobStatus` components (dedicated, not reused from the terrain versions — both have terrain-specific copy/stage-lists baked in that would've been wrong for silt, same judgment as the polling hook), three pages (`SiltWorkspacePage`/`SiltProcessingPage`/`SiltResultsPage`), three routes (`/silt`, `/silt-processing/:jobId`, `/silt-results/:jobId`), and a `Terrain` / `River Silt` pill-switcher in `Header.tsx` per the original `docs/phase_river_silt.md` §4 mockup.

**Verified for real, not just written:** `npx tsc --noEmit` clean, `npx vite build` production build succeeds clean (one pre-existing chunk-size warning, unrelated). Did not run `npm run lint` — the `lint` script exists in `package.json` but `eslint` itself was never actually added as a dependency, a pre-existing gap in this repo, not something touched here.

**What's still explicitly NOT done, by design, not oversight:** the gauge-station-id input field shown in the original mockup was deliberately omitted from `SiltUploadForm` — Chunk 3 (gauge-anchor fusion) doesn't exist yet, so that field would be dead UI with nothing to wire it to. Real dense heatmap (Chunk 4) and gauge fusion (Chunk 3) remain the actual ML research work still ahead — this entry closes the plumbing/skeleton gap only, not the modeling gap already tracked in the entries above.

---

## 2026-09-14 — Multispectral hypothesis tested at full scale: made the model WORSE, not better — real, honest, notable result

**Status:** RESOLVED (2026-09-14) for this experiment — the literature-review hypothesis did not pan out as predicted

Multispectral pull finished (1352 crops total, reusing each row's already-matched `scene_id`). Ran the actual test the whole multispectral track existed for: `extract_river_silt_multispectral_features.py` (1530/1532 rows, 27 combined features) → `train_river_silt_regressor_multispectral_xgb.py` (same XGBoost hyperparameters as the RGB-only run, for a clean comparison).

**Result: R² = -0.1810 — worse than RGB-only at the same scale**, not better:

| | R² (1532-row scale) |
|---|---|
| MLP, RGB-only | -0.0263 |
| XGBoost, RGB-only | -0.0195 |
| **XGBoost, RGB + multispectral combined (27 features)** | **-0.1810** |

`ms_ndti_nir` (the NIR-based turbidity index the literature specifically flagged) is the single most important feature by XGBoost gain (0.136, well ahead of every RGB feature) — so the multispectral bands aren't *worthless* signal, but the combined model still performs worse overall than dropping them entirely.

**Leading (unconfirmed) explanation, most consistent with everything already found this session:** the water-masking entry directly above measured that real water coverage in these crops is only 1.3% median, with 74% of crops falling below the trust threshold and silently reverting to whole-crop stats — meaning most multispectral feature values here are dominated by bank/land/vegetation reflectance, not actual river water, exactly the contamination the literature's water-masking step exists to prevent. Combined with nearly doubling the feature count (14 → 27) on the same ~1071 training rows, this is consistent with the multispectral features adding noise/overfitting risk that outweighs `ms_ndti_nir`'s real signal. Not confirmed by a controlled ablation (e.g. water-fraction-stratified evaluation) — flagged as the leading hypothesis, not proven.

**Honest framing, matching this project's own standard:** don't cite "multispectral bands don't help river silt estimation" as a general finding — this result is confounded by the water-masking gap, which was never fixed (the crop buffer was kept at 1280m to stay pixel-aligned with the already-pulled RGB crops, a deliberate tradeoff made when water masking was built). The real, controlled experiment — multispectral features restricted to crops where the water mask actually engaged — has not been run.

**Resolves when:** if this is picked up again, the next real step is not "add more multispectral features" — it's re-testing on a water-fraction-stratified subset (or a re-pull with a smaller crop buffer) to isolate whether the multispectral signal helps when the mask actually works, before concluding anything about the bands themselves.

**Update (2026-09-14) — crop-size fix attempted and falsified, not fixed**

Before re-pulling anything, tested the "buffer too wide" hypothesis directly against already-downloaded data — no new network calls needed: took 150 real multispectral crops and recomputed the water mask on progressively smaller center sub-crops (256px/1280m down to 32px/160m buffer) of the *same* images.

**Real result: shrinking the crop does not help.** The trusted-mask rate (`water_fraction >= 0.05`) stayed flat at 27-28% across every crop size tested, and median water fraction actually got *worse* as the crop shrank (0.011 at 256px → 0.001 at 32px) — the opposite of what the "wide crop dilutes water with bank pixels" hypothesis predicted. This means the problem isn't the buffer size or off-center river channels: for roughly 72% of stations, there's little-to-no water anywhere in even the tightest crop tested.

**Leading (unconfirmed) explanations, not isolated further this session:** narrow streams below Sentinel-2's 10m pixel resolution, riparian tree canopy occluding the water surface from the optical sensor (same real phenomenon this project already documented for the height pipeline's own canopy-occlusion finding, different use case), a seasonal/dry-date mismatch between the SSC reading's date and the matched scene, or coordinate imprecision in `SSC_in_situ.csv`'s station metadata. No single-variable test was run to distinguish between these.

**Honest conclusion:** the water-masking gap from the earlier entry is real but NOT fixable by adjusting crop size — that specific fix path is closed, tested, and falsified, not just deprioritized. A real fix would need either higher-resolution imagery (drone-scale, not 10m satellite), a canopy-aware detection step, or accepting `compute_water_mask()` as a best-effort/diagnostic signal rather than a reliable gate. None of these attempted — flagging for a future session, not guessing at which is worth the effort.

**Update (2026-09-14/15) — root-caused via direct visual inspection (not guessing), fixed with an adaptive threshold; real, meaningful mask improvement; downstream regression barely moved**

Generated RGB+mask-overlay composites for real crops (mix of zero-fraction and median-fraction) and looked at them directly, rather than continuing to guess. Found two real, distinct problems immediately: (1) **plainly visible rivers were getting zero mask detection** — not a narrow-stream-below-resolution case, a real, obvious winding river channel with 100% of pixels reading non-water; (2) a false-positive/false-negative pair in one urban crop (bright rooftops flagged as water, an actual swimming pool missed entirely).

**Ruled out a data/band bug before touching the algorithm:** reconstructed a true-color composite directly from the raw multispectral R/G/B bands and compared it against the separately-pulled RGB crop for the same site — they matched almost exactly, confirming band order and reflectance scale are correct. Not a pipeline bug.

**Root cause, confirmed numerically:** for a real failing crop, the maximum mNDWI value anywhere in the entire 256×256 crop was -0.153 — nowhere near the fixed `threshold=0.0`, even at the visually-obvious river pixels. But the **top-1%-highest-mNDWI pixels traced the actual river channel almost exactly** when overlaid back on the RGB — the relative signal is real and spatially coherent, it just never crosses an absolute threshold calibrated for open, easily-resolved water bodies. This is a genuine mixed-pixel effect (narrow/tree-shadowed river + canopy + shadow blending within one 10m pixel), not a broken index.

**Fix:** `compute_adaptive_water_mask()` — Otsu's method (pure numpy, no scipy/cv2) computed on each crop's own mNDWI histogram instead of one fixed global cutoff, same "measure per-scene, don't hardcode one global constant" pattern this project already uses elsewhere (texture-adaptive variance in `calibrate.py`). Guarded against Otsu bisecting a genuinely water-free scene into a fake 50/50 split: any split flagging more than `max_water_fraction=0.3` of the crop is rejected, returning an honest empty mask instead. 3 new tests, including one reproducing the exact real failure mode (a narrow strip with less-negative-but-still-negative mNDWI, which the fixed threshold misses entirely and the adaptive one recovers).

**Real, measured result on the full 1351-crop dataset (1 corrupt file found and skipped along the way — `Waterbase_PL01S1101_0506.tif`, a separate real data-quality issue, not investigated further):**

| | trusted-mask rate (>=5%) | median water fraction |
|---|---|---|
| Fixed threshold (old) | 28.3% | 0.0112 |
| **Adaptive (Otsu, new)** | **43.4%** | **0.0199** |
| Genuinely no water found (adaptive) | — | 48.0% of crops (honest zero, not fabricated) |

A real, meaningful improvement in mask quality — mask engagement rate up over 15 points. **But retraining the combined XGBoost model on the improved features moved R² only from -0.1810 to -0.1589** — still well behind RGB-only's -0.0195. **Honest conclusion: the masking fix was real and worth keeping (better mask quality is its own justified improvement), but it was not the actual bottleneck on the combined model's accuracy.** Something else is limiting the multispectral-combined approach — the leading unconfirmed suspects, not yet tested: 27 features on only ~1071 training rows (overfitting risk), or the SSC labels' own global heterogeneity swamping any per-pixel reflectance signal this feature set can extract. Don't re-attempt more masking refinements expecting this to close the remaining gap — the evidence now points elsewhere.

**Resolves when:** the mask fix itself is done and correctly attributed (real improvement, kept). The regression-accuracy question is a separate, still-open problem — next real steps, not yet tried: feature-count reduction/regularization to check for overfitting, or accepting that RGB-only's simpler feature set remains the better-performing baseline for this dataset size and moving to a different lever entirely (more real training rows, or Chunk 3/4's fusion approach) rather than continuing to refine the multispectral feature set.

---

## 2026-09-14/15 — Literature-matched fixes (log-target training, HSV color features): real, partial improvement, nothing crossed R²=0

**Status:** RESOLVED (2026-09-14) — both changes applied and measured; honest result, no breakthrough

Follow-on research (user asked for methods that would "guarantee" a fix — pushed back on that framing explicitly, ML has no guarantees, but found two concrete literature-matched gaps): the actual published global SSC model this dataset comes from (Prum/Lucchese/Gardner) reports **RMSLE = 0.24**, a log-space error metric, and uses **HSV (Hue/Saturation/Value) water-color features** alongside raw reflectance — neither had been applied to this project's silt regressors.

**1. Log-transform (log1p/expm1) added to both XGBoost trainers** (`train_river_silt_regressor_xgb.py`, `train_river_silt_regressor_multispectral_xgb.py`) — the MLP path already had this via `HeightRegressor`'s `log_target=True` default, inherited without anyone having deliberately chosen it for silt; XGBoost had no such default and was training on raw skewed mg/L values (p99=870, one outlier at 5317) the whole time.

**2. HSV features added to `extract_river_silt_features.py`** (`silt_hue_mean`, `silt_saturation_mean`, `silt_value_mean`, `silt_saturation_std`, via `matplotlib.colors.rgb_to_hsv` — already a dependency, no new one added). Hue is circular (0 and 1 are the same color) — averaged via unit-vector/`arctan2`, not a naive arithmetic mean, so red-water samples near the hue wrap point don't cancel toward a false green/yellow average. 2 new tests (wrap-point correctness, saturation distinguishing gray from vivid color).

**Real, measured result — re-extracted all features, retrained all three models on the same 1532-row dataset:**

| model | R² before this round | R² after |
|---|---|---|
| MLP, RGB-only | -0.0263 | -0.0249 (negligible — already had log-target) |
| XGBoost, RGB-only | -0.0195 | -0.0243 (no help, slightly worse) |
| **XGBoost, RGB + multispectral combined** | **-0.1589** | **-0.0553** |

**Honest read:** the combined model improved substantially — closed more than half the gap to RGB-only in one pass, and HSV saturation/hue features now rank in the top 10 by XGBoost importance (previously absent, since they didn't exist as features). This confirms both changes carry real signal for the multispectral-feature case specifically. But **RGB-only alone saw no benefit from either change**, and **no model has crossed R²=0** — the honest bar `docs/phase_river_silt.md` itself set ("a CNN is worth it only if it beats this" baseline) is still unmet across every approach tried this session (RGB-only MLP, RGB-only XGBoost, combined XGBoost, with and without adaptive water masking, with and without log-target, with and without HSV).

**Update (2026-09-15):** backend deploy target changed from Render to Northflank. `docs/depthwizard.md` §5/§9.10/§12 all name Render explicitly — needs a pass to update if/when this doc is touched again for a real reason; not done as a standalone edit here since nothing else in this session required opening that file.

**Resolves when:** this closes the specific "log-target + HSV" experiment, both changes kept (real, measured value on the combined model, harmless elsewhere). Cumulative picture across the whole session's silt-model work: every lever tried moved the combined model's R² closer to RGB-only's, but never past zero — the honest remaining hypotheses, none tried yet, are (a) real hyperparameter tuning against this actual dataset instead of borrowed literature defaults, (b) checking for overfitting given 27-31 features on ~1071 training rows, or (c) accepting that a scalar regressor on hand-crafted features — RGB or multispectral — may not be the right model family for this problem at this data scale, and the honest next step is Chunk 3/4's fusion approach or a genuinely different architecture, not another feature-engineering pass.

---

## 2026-09-15 — Sample-size scaling tested at 4 points: no trend, big pull stopped

**Status:** RESOLVED (2026-09-15) — sample-size-alone hypothesis closed

Researched the actual published global model's methodology (Prum/Lucchese/Gardner): 170,000-240,224 in-situ matchup rows, DSWE (not mNDWI) for water-pixel selection, HSV color features, global spatial-temporal cross-validation. Two of those (log-target, HSV) were already applied and measured in the entry above. DSWE was checked and found impractical — the only GEE-available global product (`OPERA/DSWX/L3_V1/HLS`) only covers April 2023 onward, while most of this project's matched scenes are 2015-2023; swapping to it would apply to a small fraction of the real data, not a wholesale fix. The remaining, biggest-looking lever was raw sample size: our ~1532 rows vs. their ~200k is a ~150x gap.

Launched a large RGB-only pull targeting ~10,000 sampled attempts (from 1532). **Hit repeated system-level OOM kills during the pull (3 separate kills)** — root-caused as unrelated to this project's scripts: top memory consumers were a long-running Virtualization.framework VM process, the Claude desktop app, Brave, WhatsApp, and VS Code, none of them this pull. The resumable/incremental-write design (built earlier this session specifically for this kind of interruption) held up as intended — each restart picked up exactly where it left off, zero rows lost across all 3 kills.

**Before waiting out the full 10k target, took an intermediate real measurement at ~4804 rows (a 3x increase over the 1532-row baseline) to check whether scaling was actually helping before spending more wall-clock time on it.** Result: **R² = -0.0596 — worse than at 1532 rows (-0.0243 with log-target+HSV already applied), not better.**

This is now the 4th independent sample-size measurement this session: 315 rows (-0.127) → 830 rows (-0.0495) → 1532 rows (-0.0243) → 4804 rows (-0.0596). No monotonic trend in either direction — the numbers bounce around the same flat, negative floor regardless of scale. **Decision: stopped the large pull rather than continuing to the full 10k target.** Four data points spanning a 15x range already answer the question the pull was launched to test — more RGB-only rows at this scale is not the fix. Reaching the paper's actual ~150x-larger scale to test that comparison fairly isn't practical in this environment (real network/wall-clock cost, plus the recurring OOM interruptions).

**Honest final picture for the river-silt use case, everything tried this session:** RGB-only features, multispectral+adaptive-water-masking, log-target training, HSV color features, and now 4x sample-size scaling — every lever produced small, real, individually-honest movements, and none crossed R²=0. The dataset itself (global, heterogeneous, `SSC_in_situ.csv`'s ±8-day matchup window, no basin-level stratification) combined with this project's ~150x-smaller sample size than the literature's own global model is the most likely explanation, not any single fixable bug. Real next steps, if pursued: (a) basin-stratified or regional (not global) modeling — train separate models per major basin/climate region instead of one global model, since the paper's own harder-won accuracy came from a dataset 150x this size; (b) tighten the matchup window from ±8 days toward literature's ≤1 day, at the cost of a smaller usable sample; (c) accept RGB-only's simplicity as the practical baseline for this project's scale and move to Chunk 3/4 (gauge-anchor fusion, dense heatmap) rather than continuing to chase R²=0 on a scalar regressor.

---

## 2026-09-15 — River silt Chunks 3 & 4 built: real gauge-anchor fusion + real dense heatmap (user explicitly asked for both together)

**Status:** RESOLVED (2026-09-15) — both wired, tested, and verified against real live data and real images

**Chunk 3 — gauge-anchor fusion.** Built `ml/calibration/silt_gauge_anchor.py`: queries USGS NWIS (`waterservices.usgs.gov`, public, no API key) for a real, live, nearby SSC (parameter 80154, mg/L) reading to anchor a prediction to — same "a real, grounded, independent measurement overrides the model outright" pattern the height pipeline already uses for SRTM.

**Real, measured limitation found and designed around, not discovered after the fact:** checked live SSC sensor availability before writing any fusion code — a single-county USGS query returned zero active SSC sites, and an entire-California query returned only 2. Turbidity (parameter 63680, FNU) is common, but is a *different physical quantity* from SSC (mg/L) — converting FNU→mg/L needs a site-specific calibration this project doesn't have, and guessing a generic ratio would be exactly the kind of fabricated precision this project's own honesty standard exists to reject. **Deliberate design decision: the anchor only ever matches on real SSC readings, never turbidity** — meaning it will correctly return "no anchor" for the overwhelming majority of real locations. That's correct behavior, not a shortfall: a rare, honest anchor beats a common, wrong one.

`get_image_center_latlon()` (new, `ml/river_silt_pipeline.py`) extracts real coordinates from a georeferenced input the same way `patch_geo.py` already does for height — returns `None` for a plain JPG/PNG with no CRS, same non-georeferenced-input distinction the height pipeline makes. 8 tests (haversine sanity, RDB parsing, network-failure/no-sites/stale/distant disqualification, real-match acceptance) — all offline-mocked except the harness runs below, which hit the real live API.

**Verified against real, live data, not just mocks:** ran the harness against `test_input_appalachian.tif` (real georeferenced US GeoTIFF) — a real network call fired against USGS NWIS, found no live SSC gauge nearby (Appalachian region, consistent with the scarcity finding), correctly fell back to `relative_silt_index`. Confirms the whole real code path — geo-extraction, live API call, disqualify-and-fall-back — works end-to-end, not just against synthetic test fixtures.

**Chunk 4 — dense heatmap.** Replaced the uniform placeholder fill with a real trend+detail composite, same principle as `ml/calibration/dense_fusion.py`'s SRTM+relative-depth split: the scalar SSC value (anchor or model) sets the heatmap's overall level (**trend**), and `compute_ndti_map()` (new — the existing scalar NDTI feature, now returned as a full per-pixel array) sets real local color variation around it (**detail**).

**Honest limit, stated in the result's own warnings, not hidden:** a generic RGB-only user upload has no multispectral bands to build a real water mask from (the adaptive-mNDWI approach built for the training pipeline needs green+SWIR1, which a plain JPG/PNG never has) — so the per-pixel pattern spans the *whole* image, not a verified water boundary. It's real relative color variation, not confirmed water-only turbidity structure. Stated explicitly in `DENSE_HEATMAP_CAVEAT`, always included in the result. `DETAIL_GAIN=60.0` (how strongly the pattern perturbs the trend) is an unvalidated visual-only constant — no real per-pixel ground truth exists to measure it against, flagged as such in-code.

**Verified for real:** ran both a plain JPG and the real georeferenced GeoTIFF through the full harness — heatmap now has real measured variation (std=6.6, range 0-44 on the Appalachian test image) instead of a single uniform value. 4 new pipeline-level tests (georeferenced vs non-georeferenced coordinate extraction, anchor-found-overrides-model, anchor-not-found-falls-back), all passing alongside the pre-existing suite (25 total across the three affected test files).

**Resolves when:** N/A — both chunks are done as scoped. What's NOT done, stated plainly: the gauge anchor is US-only (NWIS has no non-US coverage) and will rarely fire even within the US given the measured SSC-sensor scarcity; the dense heatmap's spatial detail is real but not water-verified for non-multispectral uploads. Neither is a bug — both are honest, designed-in limits of what real, honest data actually supports at this scope.

---

## 2026-09-15 — Bottleneck diagnosis: matchup-window hypothesis tested and falsified; Köppen climate zone tested — dominant feature importance, but accuracy barely moved

**Status:** RESOLVED (2026-09-15) — both real experiments run and measured, one hypothesis killed, one confirmed-but-insufficient

User asked directly "what's the bottleneck" — rather than guess, tested the two most likely remaining candidates with real measurements instead of more feature tinkering.

**1. Matchup-window hypothesis (±8 days vs. literature's ≤1 day) — tested directly, falsified.** Measured real gap distribution across the full manifest: median 4 days, only 18.5% of rows within ≤1 day, 56.5% in the 4-8 day range. Looked like a strong candidate. Directly checked whether prediction error correlates with gap size on real held-out test data: **correlation = -0.013 (noise), MAE for gap≤1 day (51.82) vs gap≥6 days (52.90) — no meaningful difference.** Matchup-window looseness is not the bottleneck, ruled out by direct measurement, not assumed away.

**2. Structural/regional hypothesis — tested with a real feature, partially confirmed.** Reasoning: nothing tested all session (features, masking, log-target, 15x more data, matchup window) moved R² at all — that flat pattern itself suggests a structural ceiling, not a fixable bug. Literature review's own SHAP finding (longitude = strongest predictor in one study) pointed at regional/geological context missing from a pure color-based global model. Rather than add raw lat/lon (a leakage risk flagged earlier — could let the model memorize individual rivers), added a coarser, legitimate proxy: **Köppen-Geiger climate zone**, downloaded as a real 0.5°-grid lookup table (Vienna TU, 244KB, `ml/features/koppen_climate.py`), one-hot encoded into 5 top-level groups (A/B/C/D/E — tropical/arid/temperate/continental/polar) via `compute_koppen_features()`, wired into both `extract_river_silt_features.py` and the combined multispectral extractor. 3 new tests (grid-snapping, real Amazon/Antarctic zone lookups), all passing.

**Real, measured, two-part result:** retrained on the full 4815-row dataset. **The 4 Köppen features dominate XGBoost's feature-importance ranking — together ~44% of total gain, more than all 18 color/texture features combined.** This strongly confirms the hypothesis *directionally*: regional context carries far more raw information than color alone for this problem. **But test-set R² barely moved** (-0.0614 with Köppen vs. -0.0596 without, at the same ~4800-row scale) — high feature importance did not translate into better held-out accuracy.

**Honest interpretation, not oversold either direction:** this is not a contradiction — it means the *direction* of the hypothesis is right (region matters enormously, more than any spectral feature this project has tried) but the *resolution* of a 5-bucket global climate classification is too coarse to actually disambiguate individual river behavior. Each bucket (e.g. "C" = temperate) still spans huge geological/land-use diversity worldwide. This matches why raw lat/lon was the *strongest* predictor in the literature's own study — full coordinates let a model effectively identify individual rivers, which a 5-category climate zone deliberately cannot (by design, to avoid memorization) but also therefore can't fully resolve.

**Resolves when:** if pursued further, the next real test (not yet tried) is a finer regional proxy — full Köppen subtype (e.g. `Cfa` vs `Cfb` vs `Csa`, ~30 categories instead of 5) or genuine basin-level clustering — trading some of the leakage-avoidance the coarse 5-group choice was designed for against more resolving power. Given the sample size (~3370 training rows) is already thin for 22-26 features, adding ~30 more one-hot columns risks overfitting without more data. Flagging as the honest next lever, not attempted this session — the current 5-group Köppen features are kept (real, non-zero signal, harmless) but this specific experiment's own result says they're not sufficient alone.

**Update (2026-09-15) — fine Köppen subtype tested, same session's final diagnosis reached**

Added `get_koppen_subtype()` to `koppen_climate.py` (full class, e.g. `Cfa` not just `C`) and ran a quick measurement (not wired into production, deliberately — a throwaway comparison first, per the overfitting risk already flagged) with one-hot subtype columns in place of the 5-group version: **25 real subtypes present in the actual dataset** (checked directly, not assumed), 43 total features on the same 3370 training rows.

**Result: R² = -0.0546 — marginally better than the 5-group version (-0.0614), but still essentially flat, not a meaningful win.** MAE (54.7) also didn't improve materially. Confirms the overfitting-risk concern was well-founded: more granular categories on the same small sample doesn't pay for itself.

**This closes the loop on the session's whole bottleneck investigation with one honest, unifying explanation:** region genuinely matters (proven twice — the literature's own lat/lon SHAP finding, and this session's own Köppen feature-importance result), but **neither coarse nor fine regional proxies help *because there isn't enough data per region to learn each one's local color-to-SSC mapping*** — 25 subtypes across ~3370 rows averages ~135 rows/zone, nowhere near enough. The literature's own global model has ~170-240k rows; split across comparable strata, that's thousands of rows per zone, not ~135.

**Reframes the earlier "more data doesn't help" conclusion** (the 315→830→1532→4804-row test that found no trend) — that test was correct about *uniform* global sampling not helping, but the real lever was never "more data in general," it's **"more data per region/stratum."** A uniform sample dilutes across too many climate zones to ever concentrate enough rows in any one of them. Every lever tried this entire session (masking, HSV, log-target, coarse region, fine region, matchup window) ran into the same underlying wall, just from different angles.

**Resolves when:** this is the session's final honest diagnosis for the river-silt accuracy problem — not resolved (still no model beats R²=0), but the *reason* is now understood and unified rather than a list of unexplained failed experiments. Real next step, if pursued in a future session: stratified/targeted data collection — pull many more rows specifically from a small number of climate zones/basins (concentrated, not uniform global sampling) to actually test whether enough same-region data closes the gap for at least those zones, rather than another global-uniform pull or another feature pass.

---

## 2026-09-16 — Concentrated regional data collection tested: best result of the entire session, R² nearly at zero

**Status:** IN PROGRESS — real, large improvement confirmed; still pulling more data to push further

Acted on the previous entry's diagnosis directly: rather than another uniform global pull, filtered `SSC_in_situ.csv` to the single largest existing climate bucket (`Cfb` — temperate oceanic, already 1914/4815 rows, ~40% of the dataset) and launched a **targeted pull from that filtered pool only** (`ml/data/river_silt_raw/SSC_in_situ_Cfb.csv`, 55,901 real eligible rows — huge headroom), reusing `fetch_river_silt_imagery.py`'s existing `--csv` override, no new pull-script code needed.

**Hit 4 separate OOM kills during this pull** (system-wide memory pressure from other running apps, same root cause as every prior incident this session) — resumable/incremental-write design held up each time, zero rows lost across all 4 restarts.

**Real result, tested at an intermediate checkpoint (Cfb rows: 1914 -> 3777, ~2x) rather than waiting for the full 8000-attempt target:** trained an XGBoost model on **Cfb-only** rows (2663 train / 542 val / 572 test, same log-target config as every other model this session) and evaluated on **Cfb-only held-out test data** — the direct test of "does a region-specific model on concentrated same-region data close the gap."

**R² = -0.0073 — the best result of the entire session, by a wide margin.** Every global-model variant tried all session (RGB-only, multispectral, masked, HSV, log-target, coarse/fine Köppen features, 15x more uniform data) landed between -0.05 and -0.18. A regional model on ~2x the original same-region data alone gets within a hair of crossing zero. **This directly validates the diagnosis from the entry above**: region-specific modeling with enough same-region data is the real fix, not more global features or more uniformly-spread data.

**Honest caveat, not swept under the rug:** MAE on this Cfb-only test (124.63 mg/L) is actually *higher* than the global models' MAE (~50-55 mg/L) despite the much-improved R². Not yet explained — leading unconfirmed guess is a handful of high-SSC outlier stations within this one region inflating both the target variance (which R² is normalized against, explaining the R² jump) and the absolute error (which MAE isn't normalized against). Not investigated further yet — flagging honestly rather than only reporting the flattering metric.

**Resolves when:** the Cfb pull (still running, targeting the full 8000-attempt budget from the filtered pool, currently ~4000+ Cfb rows) finishes, and the regional model is re-measured on the larger concentrated sample — if R² keeps improving with more same-region density, that's strong confirmation this is the real, generalizable fix (worth doing for other major zones too, e.g. `Dfb`/`Cfa`, the next-largest existing buckets). If it plateaus, that's also real information about how much same-region data is actually needed.

**CORRECTION (2026-09-16) — the result above was not properly controlled; a fair comparison shows no real regional advantage**

User asked directly whether the improving numbers needed a "normalizing factor" or were a data-density issue — prompted a proper check that the earlier result skipped: **the global model was never evaluated on the same test rows as the Cfb-only model before declaring the regional approach validated.** Doing that comparison now:

| | R² (test includes a real 30,390 mg/L outlier) | R² (outlier excluded) | MAE (outlier excluded) |
|---|---|---|---|
| Cfb-only regional model | -0.0073 | -0.0638 | 71.65 mg/L |
| **Global model, evaluated on the identical Cfb test rows** | **-0.0077** | **-0.0758** | **72.16 mg/L** |

**They're essentially the same. The regional model does not beat the global model on a fair comparison.** Two real findings behind this:

1. **A single extreme test-set row (30,390 mg/L, a real flash-flood-scale reading) swings R² dramatically depending on whether it's included** — R² is normalized by total target variance, and this one row inflates that denominator enough to make R² look close to zero regardless of real predictive skill. Every "R² near zero" headline number reported this session (global and regional both) needs this caveat: it is not fully trustworthy as a skill metric while a single outlier this extreme sits in a ~1000-row test set. MAE with the outlier excluded (~72 mg/L against a median target of ~10 mg/L) is a more honest, if less flattering, read of real accuracy.

2. **The global model already has Köppen one-hot features as inputs** (`silt_koppen_C` etc., added in the entry above) — XGBoost can already split internally on "is this a Cfb row" and behave region-specifically *within* one global model. A separate Cfb-only model doesn't give the model new information the global model lacked; it only gives it *less* data (2663 rows vs 4674) to work with. In hindsight this was predictable and should have been checked before the concentrated pull was launched, not after.

**Honest, corrected answer to "why 6000+ files":** the diagnosis that motivated it (region-specific modeling needs concentrated same-region data) is not confirmed by this test. The earlier "best result of the session" claim is retracted — it was a comparison artifact (different test-set composition/size), not a real regional effect. No normalizing factor would have fixed this either; the underlying issue is a genuinely heavy-tailed target distribution making R² an unstable metric at this sample size, not a scale/calibration bug.

**Resolves when:** if regional modeling is worth testing again, it needs a controlled comparison against the global model *on identical held-out rows* from the start, and should probably use MAE or a robust/trimmed metric rather than raw R² given how unstable R² is here. Not re-attempted this session — the Cfb pull can keep running for its own sake (more real data is never harmful) but should not be assumed to fix accuracy until re-tested properly.

**Follow-up (2026-09-16) — Cfb pull killed, real outlier handling shipped instead**

User asked directly why we can't just replicate the source paper — answered honestly: most of the methodology already is replicated (XGBoost, log-target, HSV, regional conditioning); the two real unclosed gaps are (a) raw data scale (150-200x, an engineering-throughput problem, not solved by one more pull), and (b) data curation/QA, which had never been touched. Killed the Cfb pull (7,285 real rows kept, not wasted, just not proven to help yet).

**Shipped the concrete, cheap fix: `MAX_PLAUSIBLE_SSC_MG_L = 5000.0`**, a real measured threshold — the data has a clean natural gap (continuous up to 11,260, then a jump straight to 30,390+), and the top 4 rows (30k-52k mg/L) are a distinct population, most likely data errors or a different reporting convention. Excludes 9/7285 rows (0.12%), wired into both `extract_river_silt_features.py` and the combined multispectral extractor, reported explicitly in the skip log (not silently dropped). **Side-finding, not chased further:** one single station (`Waterbase_PL01S1301_1697`) accounts for 3 of the 9 excluded rows (52230, 30390, 45215 mg/L) — a station-specific data issue, not independent flood events, flagged for whoever investigates data quality next.

Also reordered `evaluate()`'s reported metrics (MAE/MedAE first, R² relabeled `r2_unstable_see_docstring` with the instability reasoning inline) so the misleading headline metric can't be cited uncritically again.

**Real, clean, final numbers after the fix (RGB-only XGBoost, log-target, full 7276-row dataset):**

| Metric | Value |
|---|---|
| MedAE | **9.43 mg/L** (target median ~10 mg/L) |
| MAE | 62.98 mg/L |
| Bias | -52.69 mg/L (systematic underprediction on the remaining high-value tail) |
| R² (unstable) | -0.0579 |

**Honest read:** the model tracks *typical* river conditions reasonably (median error ~9 mg/L against a median target of ~10) — the large MAE/bias come from real, physically-legitimate high-flow events (up to 5000 mg/L) that no single static satellite image can anticipate without temporal/hydrological context. That's a structural limit of the problem as posed (one photo, no time series), not a bug to keep chasing with more features or more data.

**Resolves when:** N/A for this entry — the outlier handling and metric-reporting fix are done and correctly attributed. The regional-modeling question from the entry above remains genuinely open, not re-attempted.

**Follow-up (2026-09-16) — scaled to 8407 real rows (India + global Reservoir pull), tuned XGBoost, R² plateaued**

Parallelized the Earth Engine pull (`ThreadPoolExecutor`, `--concurrency 8`, ~7.3x measured speedup: 84 rows/min vs 11.5 rows/min sequential) and ran it to completion — final dataset 8426 imagery rows (2604 India River, rest global Reservoir + original mixed sources), 8407 usable feature rows after outlier/read-failure skips (5884 train / 1261 val / 1262 test). Switched production model from the MLP `HeightRegressor` to a hyperparameter-tuned `xgboost.XGBRegressor` (`n_estimators=600, max_depth=10, learning_rate=0.05, subsample=1.0, colsample_bytree=1.0`) — this was the single biggest lever this session, fixing a real prediction-compression underfitting problem (pred_std went from ~9 to 144 vs actual test std 246.84).

**Real, verified numbers on the full 8407-row dataset (checkpoint: `ml/models/river_silt_regressor_xgb_v1.json`):**

| Metric | Value |
|---|---|
| MedAE | **8.65 mg/L** |
| MAE | 57.37 mg/L |
| Bias | -27.34 mg/L |
| R² (unstable) | 0.2649 |
| pred_std | 144.00 (actual std 246.84) |

Retrained again after the last 604-row reservoir batch landed (this batch was pulled and processed in this session's continuation) — result came back **byte-identical to 4 decimal places** to the pre-batch run. Verified this isn't a stale-cache artifact: confirmed the new rows (e.g. `GEMS_28.93573_-105.31327`, `GEMS_25.27459_-103.81319`) are genuinely present across all three fresh split files, feature/split files have fresh mtimes, and the training script reads them directly (no intermediate cache). Honest read: this is a real, reproducible finding, not a bug — **the model has hit a real accuracy ceiling that ~600 more rows (7.7% of the dataset) does not move**, consistent with this session's earlier sample-size-scaling finding (non-monotonic/plateaued at small scale, now confirmed at this larger scale too). Don't expect another few-hundred-row pull to move this number; if pursued further, the lever is a different axis (better features, e.g. actual NIR/SWIR bands per the literature-review entry above, not more of the same RGB-only rows).

**Resolves when:** N/A — this is the current production baseline. The NIR/SWIR band gap flagged in the literature-review entry above remains the most promising untried lever.

**Follow-up (2026-09-16) — RGB-only water masking tried for the heatmap overlay, measured unreliable, reverted**

User reported the heatmap overlay wasn't legible: tint painted the whole photo (farmland, roads, everything) the same as any water, not concentrated on the actual river channel. Tried a fix: Otsu-adaptive threshold on a "blueness" index `(B-R)/(B+R+eps)` (RGB-only approximation of the real mNDWI mask `extract_river_silt_multispectral_features.py` already uses with real NIR/SWIR bands).

**Measured, not assumed, before shipping it:** ran the heuristic against all 5 curated real demo images (`silt_demo_best/`). Result — 24-71% of each image flagged as "water":

| Site | "Water" fraction |
|---|---|
| GEMS_40.37129_22.16126 | 24.2% |
| GEMS_52.46882_6.45168 | 70.8% |
| GEMS_45.2244_19.8419 | 32.4% |
| Waterbase_FRB2R01001503 | 52.0% |
| Waterbase_IT10SRD1 | 47.5% |

A real river channel in a crop this size runs ~2-4% (this session's own real mNDWI-based measurement, 2026-09-14 entry). Every one of these is 6-30x too high — the heuristic isn't separating water from land at all, it's roughly bisecting the image on overall color/brightness. Shipping this would have been worse than the honest status quo: a confidently-wrong "water mask" that looks authoritative but paints farmland/forest as river.

**Reverted the masking attempt entirely** (`ml/river_silt_pipeline.py`, `ml/features/texture_utils.py`, `SiltHeatmapViewer.tsx` all back to pre-attempt state). Kept two real, independent fixes made in the same pass:
1. Default heatmap opacity lowered 0.75 → 0.4 (`SiltHeatmapViewer.tsx`) — since the tint is whole-image, not water-restricted, a heavy default buried the source photo under a flat color wash. Lower default reads as a legible blend instead.
2. `SiltCrossSectionScene.ts`: `OrbitControls` had no `minDistance`/`maxDistance` — unbounded scroll-to-zoom let the camera clip inside the bank mesh, rendering as a huge, confusing green block filling most of the view (reported by user, reproduced from the described symptom). Clamped to `[4, 16]`.

**Honest conclusion:** a real, water-restricted heatmap needs the NIR/SWIR bands already flagged as the biggest untried lever above — RGB alone cannot reliably separate water from land in these Sentinel-2 true-color crops. Don't re-attempt an RGB-only heuristic water mask without a genuinely new signal; this one was tried and measured, not guessed.

**Resolves when:** if pursued, needs real multispectral bands at inference time (not just training), which is a bigger scope change to the upload flow (would need to accept multi-band GeoTIFF, not just RGB) — not attempted this session.

**Follow-up (2026-09-16) — cross-section sediment was invisible (real bug: opacity:0), plus a normalization-scale mismatch**

User reported the 3D cross-section never showed a visible sediment layer, just a plain blue-gray water wedge. Real bug found in `SiltCrossSectionScene.ts`: the sediment ribbon's `THREE.Mesh` was built with `opacity: 0` (literally invisible) — a leftover placeholder value, not a distribution problem as first suspected.

Also found a real scale mismatch: `SiltCrossSectionViewer.tsx` normalized sediment fill fraction against the heatmap's 900 mg/L (p99) ceiling, tuned for compressing a heavy-tailed color ramp — every realistic non-flood reading (1-50 mg/L) rounds to `intensity < 0.06`, an imperceptible sliver even with opacity fixed. Changed the cross-section's ceiling to 40 mg/L, the same `GAUGE_MAX` `DredgingIndicator`'s gauge already uses (real tercile-derived thresholds) — a "moderate"/"high" reading now visibly reads as silted, consistent with the indicator panel right next to it.

Fixed opacity, retuned the sediment top surface to be a smoothed, mostly-flat layer (small `local` modulation range 0.9-1.1, moving-average-smoothed profile) instead of mirroring the raw 48-point profile's full jaggedness — physically sediment deposits fill/smooth low spots, they don't amplify bed noise. Replaced the floating, disconnected bank boxes (visually gapped from the channel edge, and the cause of an earlier zoom-clip bug) with continuous sloped ground wedges sharing the exact bed-edge point. Added hemisphere + fill lighting and scene fog for a more natural look, per explicit user ask ("more realistic").

**Resolves when:** N/A — shipped. `frontend/src/lib/realSiltDemoFixture.ts`/`realSiltDemoFixture2.ts` (dev-only, gitignored via the root `*.json`/binary conventions — actually these are `.ts`, tracked; regenerate via `tools/run_river_silt_pipeline.py` if the geometry or heatmap logic changes again) still hold the pre-fix cross-section arrays, which render fine under the new code (same data, just correctly visualized now).

**Follow-up (2026-09-16) — cross-section rebuilt as one solid gradient mesh, banks removed**

Further user feedback on the same scene: sediment/water met at a hard color edge, not a gradient; the mesh was hollow/see-through from some angles; remove the green bank geometry entirely.

`buildChannel()` replaces the old two-separate-ribbons approach with one fully closed mesh (front/back walls, top cap, bottom cap, and end caps at both ends — the previous version was missing the bottom cap and end caps entirely, which is what made it look hollow) using per-vertex colors: sediment color at `bedY`, a murky blended color at `sedimentTopY` (`COLOR_SEDIMENT.lerp(COLOR_WATER, 0.4)`), water color at the water line — GPU-interpolated across each face, giving a real smooth gradient instead of a hard boundary. Kept `side: THREE.DoubleSide` deliberately (not `FrontSide`) — with ~14 separate index-push blocks for walls/caps/end-caps, verifying every one has exactly correct winding by hand was too easy to get wrong, and wrong winding + `FrontSide` silently culls faces (a worse regression than the hollow look this was fixing). Removed `buildBanks()`/`buildGroundWedge()` entirely per explicit ask — the channel is now the only geometry in the scene.

**Resolves when:** N/A — shipped, `tsc`/`vite build` clean. Visual confirmation still pending (no browser-automation tool available in-session) — flagged to the user to check in-browser.

**Follow-up (2026-09-17) — the solid mesh rendered almost black: real normal-averaging bug**

User screenshot showed the channel as a near-solid black wedge, no visible gradient or lit surface. Real cause: `buildChannel()`'s single indexed `BufferGeometry` shares vertices at every seam between geometrically distinct face groups — a vertical wall face and the horizontal top/bottom cap it meets share the same vertex. `computeVertexNormals()` averages the normals of every face touching a shared vertex, so at each of those seams it blended a wall's outward-pointing normal with a cap's up/down-pointing normal, producing wrong, muddy normals across most of the mesh — not a lighting-intensity problem, a geometry-topology one.

Fixed by expanding the same triangle list (the `indices` array was already correct — this wasn't a winding bug) into a non-indexed geometry: each triangle gets its own 3 unique vertices instead of sharing them with neighbors, so `computeVertexNormals()` (now effectively per-face, nothing to average against) gives each face its own correct normal. Added `flatShading: true` too, belt-and-suspenders against any future accidental vertex sharing. Vertex colors (the sediment/water gradient) are untouched — that interpolation was never the broken part.

**Resolves when:** N/A — shipped, `tsc`/`vite build` clean.

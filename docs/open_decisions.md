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

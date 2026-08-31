# Phase 4 Notes — Calibration Module (Scale Correction)

Written at the end of Phase 4 (Chunks 1-4). Informs Phase 5 (validation). Frozen interface: `ml/calibration/calibrate.py::calibrate_scene()` and `ml/pipeline.py::run_pipeline()` — read those first for the actual contract.

## Chunk 1 — Regressor training results

Trained `ml/calibration/regressor.py`'s `HeightRegressor` (PyTorch MLP) on Phase 3's real `data/processed/v1/features/features_{train,val,test}.csv` for the first time — previously synthetic-only. Real early-stopping + best-checkpoint selection added to `fit()` (tracks best val loss, restores that state_dict rather than whatever epoch ran last).

Checkpoint: `ml/models/regressor_v1.pt` (gitignored — not distributed via git; a worker without it falls back to the honest relative-only path, see Chunk 3 below).

Real per-terrain test-set accuracy (final, after all Chunk 1/2 fixes):

| terrain | MAE | notes |
|---|---|---|
| forested | 0.89m | |
| sparse | 1.13m | |
| urban | 2.44m | |
| hilly | ~200m | permanent information ceiling — see below |

Two things tried and **rejected** because measurement said no:
- `log_target=True` (train on `log1p(height)`) — round-trips correctly (verified) but made zero measurable difference to hilly's error. Kept anyway since it's more architecturally correct (heights are non-negative), but don't expect it to fix scale problems — it doesn't.
- A continuous least-squares fit of squared-error vs `depth_grad_std` (texture noise) — R²=0.007, useless, and produced negative "variance" at low percentiles. A robust 2-bin split on the real median was used instead (see Chunk 2 below).

**The regressor cannot recover absolute scale from depth-map statistics alone — permanent, not fixable by more data or a different loss function.** Confirmed by direct nearest-neighbor measurement: real hilly patches (400m+ relief) sit at Euclidean distance 0.18-0.6 (normalized, 11-dim feature space) from real non-hilly patches with near-zero height. Relative depth is scale-free by construction; no amount of training teaches a model to recover information that was never encoded in the input.

## Chunk 2 — Fusion technique decision

The original spec (docs/depthwizard.md §7 Phase 4) named joint bilateral filtering — SRTM as a low-res scale anchor, the depth map as a high-res structural guide. **What's actually built is inverse-variance weighted averaging of independent scalar estimates** (`ml/calibration/fusion.py::fuse_height_estimates`), not spatial guided filtering. This is a deliberate, documented tradeoff given the timeline, not an accidental deviation — it satisfies the same requirement ("combine signals into a height + confidence output") at a coarser level of spatial sophistication. `calibrate_scene()` operates at one scalar estimate per scene, not a dense per-pixel fused field.

Consequence: `ml/pipeline.py`'s dense per-pixel absolute heightmap is produced by anchoring the existing relative depth map's own mean to the single fused scalar (`scale_factor = fused_height / relative_mean`, linear rescale). This preserves the relative depth map's internal structure but applies one uniform scale factor across the whole image — a scene with genuinely mixed terrain (e.g. valley + mountain in one frame) would get one compromise scale, not spatially-varying calibration. True guided filtering would fix this; it's a real gap for very heterogeneous scenes, not yet observed as a problem on the patch-sized (256px) real data validated so far.

**Real bug found and fixed while validating this against real data**: initially computed SRTM's estimate as elevation range (max−min) and fused it directly against `height_mean` (a mean) — different physical quantities, made fusion *worse* than the regressor alone (597m error vs 432m) until caught. Fixed to `mean(elevation - elevation.min())`, matching the training label's own definition exactly.

**Result, verified on 10 real held-out hilly patches (live SRTM fetches, not mocked)**: MAE 243.6m (regressor-only) → 33.3m (fused), an **86.3% reduction**.

## Chunk 3 — Pipeline integration & the confidence-gate redesign

`ml/pipeline.py` now calls `calibrate_scene()` for real. The interesting part: the first design (gate `absolute_dsm` on fused cross-source confidence ≥ 0.5) was **wrong even though it matched the PRD's literal wording**, discovered by running the real pipeline end-to-end. Because the regressor and semantic priors are both structurally near-zero for real hilly scenes, "cross-source disagreement" is baked into every hilly scene by construction — measured confidence 0.37-0.41 across 4 different real crops, regardless of how good the fused number actually was. Gating on that would mean hilly scenes could never reach `absolute_dsm`, punishing SRTM for a disagreement whose cause was already known and already priced into its variance.

**Redesigned**: `calibrate_scene()` returns `CalibrationResult(fusion, srtm_valid_fraction)`. `ml/pipeline.py` gates `absolute_dsm` on `srtm_valid_fraction >= MIN_SRTM_VALID_FRACTION` (0.8) when SRTM succeeds, not on fused confidence. Fused confidence is still computed and surfaced as an informational warning when low — never silently dropped, just no longer the hard switch.

Verified end-to-end on 3 real samples: Nepal crop (georeferenced) → `absolute_dsm`, max_height=2169m; Tuscany crop (georeferenced) → `absolute_dsm`, max_height≈83m; plain non-georeferenced JPG → `relative_dsm`, SRTM correctly never attempted.

## Post-Chunk-3 optimization pass (not in the original Chunk 1-4 scope, done because it was cheap and measurable)

- **`torchvision` was missing all session** — semantic priors had been silently falling back to a crude color heuristic every single run (`Could not load transformers segmentation pipeline... Missing optional dependencies: torchvision`). Installed and pinned. Real impact on hilly is small by design (semantic priors cap at 0-30m); the payoff is for urban/forested/sparse.
- **`regressor_variance` was a single fixed 100.0, backwards for the common case.** Measured real error: ~14.7 m² MSE non-hilly vs ~15,379 m² hilly — genuinely bimodal. Split into `regressor_variance_with_srtm=100.0` (kept, already validated) and a **texture-adaptive** `regressor_variance_without_srtm` (defaults to `None`, triggers a lookup based on the scene's own `depth_grad_std`: 7.226 m² for clean-textured scenes, 22.146 m² for noisy ones — measured, matches `ml/depth/PHASE1_NOTES.md`'s own documented canopy-occlusion failure mode). Verified: fused MAE for the common case improved 3.995m → 2.100m → 1.960m across the two fixes (a cumulative ~51% reduction from the original mis-weighted default).
- Honest caveat carried through both fixes: fused MAE (1.960m) is still slightly behind the regressor alone (1.533m) in the non-hilly regime — fusion trades a little raw accuracy for a cross-check/confidence signal, it doesn't strictly beat the regressor alone there.

## Chunk 4 — Hardening

- `TestSRTMFetch::test_fetch_chennai_elevation` and `test_caching_behavior` marked `@pytest.mark.slow` (real network calls) — default `pytest -m "not slow"` run is now fully offline. Added `test_fetch_srtm_elevation_returns_structured_data_offline` and `test_caching_behavior_offline`, which mock the network layer and additionally prove the disk cache is actually hit (the live version couldn't prove that without mocking).
- Removed `xgboost`/`scikit-learn` from `ml/requirements.txt` — confirmed zero references anywhere in `ml/`, dead weight since the regressor is a PyTorch MLP, not a tree-based model.

## Known limitations going into Phase 5

- **Non-georeferenced hilly input has no path to accurate absolute height.** Permanent — no external scale anchor exists without geo-coordinates. Correct behavior (relative_dsm + warning), not a gap to close.
- **`MIN_SRTM_VALID_FRACTION` (0.8) and `MIN_CALIBRATION_CONFIDENCE` (0.5) are reasonable-looking, untuned defaults** — neither has been tested against a real sweep of void/NoData or extreme-disagreement failure cases.
- **Semantic-prior fusion hasn't had the same real-data validation treatment SRTM got.** Its contribution is small by construction (capped at 0-30m) but its correctness under real conditions is less scrutinized than SRTM's.
- **The dense heightmap uses one global scale factor per image**, not true joint bilateral guided filtering — a real gap for scenes spanning highly heterogeneous terrain within one frame (see Chunk 2 above). Not yet observed as a problem on 256px patch-scale validation.
- **R²=0.26 headroom identified but not pursued** in the non-hilly regressor — richer texture/frequency depth-map features could likely improve this further (~35-45 min estimated). Deferred, logged in `docs/open_decisions.md`, not part of this phase's scope.
- **Two supplementary hilly regions (Wyoming, Australia) never got a valid RGB match** — sitting unused if more hilly volume is ever wanted.

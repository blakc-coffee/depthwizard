# Phase 1 Notes — Backbone Integration & Sanity Testing

Written at the end of Phase 1 (Chunks 1–4). Informs Phase 2 (dataset stratification), Phase 4 (calibration/fusion weighting per terrain type), and Phase 5 (validation).

## Environment (Chunk 1)

- `ml/.venv` — Python 3.12.13 via pyenv (chosen over system Python 3.14 for broader wheel compatibility with rasterio/GDAL/XGBoost in later phases).
- `torch==2.13.0`. MPS backend confirmed available and active (not silently falling back to CPU) — verified with a real matmul on `mps:0`.
- Harmless warning on import: `Failed to initialize NumPy` from torch's internal numpy interop — resolved once `numpy` was installed in Chunk 2. No functional impact either way.

## Backbone (Chunks 2–3)

- Model: Depth Anything V2, base variant — `depth-anything/Depth-Anything-V2-Base-hf` via the `transformers` `pipeline("depth-estimation", ...)` API, running on MPS.
- Confirmed on a generic sanity photo: output shape matches input, full 0–255 value range, no NaNs, near/far ordering visually correct.

## Per-terrain findings (Chunk 3)

| Terrain | Behavior | Notes |
|---|---|---|
| Mountain / hilly | **Good.** | Ridge/valley shading gradients tracked well — this terrain type's depth cues (shading-driven) resemble the natural photos the model was trained on. |
| Sparse residential (isolated structure) | **Good.** | Rooftop cleanly isolated as a distinct near-plane region against surrounding ground — solid object-level separation even from a nadir view. |
| Forest (dense canopy) | **Weak — expected.** | Canopy occlusion: output is blobby texture noise loosely tracking crown clusters, not real elevation. Matches the domain-gap failure the PRD predicted (no ground visibility, model has nothing but self-similar texture to work with). |
| Urban dense residential (grid) | **Weak/ambiguous.** | Blocky pattern loosely tracks rooftop positions but reads more like shadow/material-contrast texture than true relative height. Repetitive nadir grid structure seems to confuse the model. |
| Chennai LISS-IV False Color Composite (Indian/Cartosat-lineage optical, R=NIR/G=Red/B=Green) | **Weak — new finding, not a data-quality issue.** | Real cloud-free river/urban/coastline scene, clean input. Model collapsed to a near-uniform left-to-right brightness gradient, failing to resolve visible river channels, urban grid, or cloud/land boundaries. Likely cause: false-color infrared statistics (e.g. red vegetation) fall outside the natural-color priors the model was trained on. This is a genuine color-domain gap, distinct from the structural domain gap (nadir perspective) the PRD anticipated — worth testing whether a true-color-approximated composite or per-channel renormalization mitigates it before Phase 4. |

An earlier attempt at the Indian-terrain sample used a mis-sourced file that turned out to be a rendered preview of Cartosat-1 DEM elevation data (not an RGB photo) — corrected before this writeup. The real DEM tile (`P5_PAN_CD_N13_000_E080_000_DEM_30m.tif`, Chennai area, 30m, ~54% no-data) and the raw LISS-IV band tifs it was replaced with are not part of this repo; they're staged locally outside version control (see Chunk 3 handoff). They're candidate reference/ground-truth material for Phase 4 (fusion signal, alongside or instead of SRTM) and Phase 5 (Indian-terrain validation, PRD §3.2) — not inputs to the depth backbone itself.

## Systematic bias

- No single-direction bias (e.g. "always underestimates height") observed across terrain types — behavior instead splits along **whether the scene offers shading/occlusion cues the model's natural-photo training distribution already covers** (mountain, isolated structures) versus scenes that don't (dense canopy, repetitive urban grids, false-color composites).
- Practical implication for Phase 4: confidence weighting should key off *scene structure type* and *color-space normality*, not terrain label alone — the Chennai result shows a real Indian scene can fail for a reason (color statistics) orthogonal to the terrain-type failure modes (occlusion, repetition) seen elsewhere.

## Frozen interface (Chunk 4)

`ml/depth/backbone.py` — locked for Phase 2/3 dataset and feature-extraction work to build against:

```python
def estimate_relative_depth(image: PIL.Image.Image) -> PIL.Image.Image: ...
def estimate_relative_depth_batch(images: list[PIL.Image.Image]) -> list[PIL.Image.Image]: ...
```

- Input: PIL RGB image, any size.
- Output: PIL image (mode `L`), same dimensions as input, uint8 relative depth (0=far, 255=near per observed convention).
- No absolute/metric scale, no SRTM, no semantic priors, no calibration logic — out of scope until Phase 4, per the PRD.
- Any change to this signature is a breaking change for downstream phases; bump and announce rather than editing silently.

## Known PRD/practice mismatch

`docs/depthwizard.md` §7.0 (Data Access) says Bhuvan/Cartosat samples should be "a fixed small sample set committed to the repo." Current practice keeps `ml/depth/samples/` gitignored (explicit project decision — no imagery binaries in git). Left as gitignored for now; revisit if the PRD's wording is meant literally rather than aspirationally.

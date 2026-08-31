# DFC2019 Format Notes (Chunk 1)

Inspected tile: `JAX_004_007`

| Property | RGB | Truth (AGL height) |
|---|---|---|
| Shape | 1024x1024, 3 band(s) | 1024x1024, 1 band(s) |
| Dtype | uint8 | float32 |
| CRS | None | None |
| Bounds | BoundingBox(left=0.0, bottom=1024.0, right=1024.0, top=0.0) | BoundingBox(left=0.0, bottom=1024.0, right=1024.0, top=0.0) |
| NoData | None | None |

**Alignment check:** dimensions match: True | CRS match: True | bounds match: True
**Height stats (excluding NoData):** min=-0.37m max=29.55m mean=3.42m

**Patch size:** data/raw/dfc2019/track1 tiles are patchified at 256x256 (see ml/data/preprocess.py DEFAULT_PATCH_SIZE).
Not a guess — Phase 1's frozen interface (ml/depth/PHASE1_NOTES.md) accepts "any size" input,
so 256 is a free choice, not a constraint; picked as a conventional ML patch size that divides
this tile's 1024px width evenly (4 whole patches, 0px remainder handled by the pad edge policy).

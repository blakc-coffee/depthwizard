# Open Decisions Log

Append-only. Every open question, deferred decision, or design tradeoff surfaced during work on this repo goes here — not just in chat. When a decision gets made, update its entry to `RESOLVED` with the date and outcome instead of deleting it (the history of why is worth more than a clean list).

Format per entry: date raised, status, what it's about, current thinking, what would resolve it.

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

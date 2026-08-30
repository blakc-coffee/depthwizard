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

## 2026-08-30 — No automated tests existed under `ml/` before this session

**Status:** RESOLVED (2026-08-30)

Added `ml/pytest.ini` + `ml/tests/` covering every implemented module (`backbone.py`, `texture_export.py`, `preprocess.py`, `download_datasets.py`, `pipeline.py` end-to-end). Nothing written for Phase 3/4/5 files — they were empty (0 bytes) at the time, nothing to test yet. Convention going forward: new ml/ logic ships with a test in the same chunk, not deferred.

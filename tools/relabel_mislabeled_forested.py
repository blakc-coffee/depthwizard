#!/usr/bin/env python3
"""One-off data migration: relabel forested->urban for patches classify_terrain()
mislabeled (docs/open_decisions.md, 2026-08-31 "Forested-bucket relabeling").

classify_terrain()'s std/roughness heuristic doesn't distinguish "no local
height variance because it's flat ground" from "no local height variance
because it's a large, uniformly-elevated flat rooftop" -- both land in
low-variance buckets. Segmentation (now fixed, ml/calibration/semantic_priors.py)
gives a real, independent signal: does the RGB actually show a building.

Criterion for relabeling forested -> urban (all three required, conservative
by design -- this moves real files, false positives are costly to undo):
  - semantic_building_frac >= 0.5 (segmentation says mostly building)
  - semantic_vegetation_frac < 0.2 (not a real mixed canopy+building scene)
  - truth height range (max-min over valid pixels) >= 2.0m (real structure,
    not the flat-pavement false-positive documented in the entry immediately
    before this one in open_decisions.md -- defense in depth, even though
    that bug was measured as 100% confined to `sparse`, never `forested`)

IMPORTANT: this does NOT change any row's features or the regressor's
predictions -- terrain_type is metadata-only (never in FEATURE_COLUMNS). This
only fixes which per-terrain bucket a patch's already-unchanged prediction
error is reported under. See docs/open_decisions.md for the full reasoning.

Moves, for each flagged patch: the raw RGB tif, the raw truth tif, the cached
depth PNG, and the cached semantic classmap PNG, all from their `forested`
subdirectory to the matching `urban` one -- then updates manifest.json in
place (terrain_type, rgb_path, truth_path). Backs up manifest.json first.

Run from the repo root:
    python tools/relabel_mislabeled_forested.py --dry-run   # inspect first
    python tools/relabel_mislabeled_forested.py              # apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ML_DIR = REPO_ROOT / "ml"
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

import numpy as np
import rasterio
from PIL import Image

MANIFEST_PATH = REPO_ROOT / "data" / "processed" / "v1" / "manifest.json"
DATA_ROOT = REPO_ROOT / "data" / "processed" / "v1"
DEPTH_CACHE = DATA_ROOT / "depth_cache"
SEMANTIC_CACHE = DATA_ROOT / "semantic_cache"

BUILDING_FRAC_MIN = 0.5
VEGETATION_FRAC_MAX = 0.2
MIN_REAL_RELIEF_M = 2.0
FROM_TERRAIN = "forested"
TO_TERRAIN = "urban"


def _semantic_fracs(entry: dict) -> tuple[float, float] | None:
    path = SEMANTIC_CACHE / entry["split"] / entry["terrain_type"] / f"{entry['patch_id']}_classmap.png"
    if not path.exists():
        return None
    class_map = np.array(Image.open(path))
    return float((class_map == 0).mean()), float((class_map == 1).mean())


def _real_relief(entry: dict) -> float | None:
    truth_path = DATA_ROOT / entry["truth_path"]
    with rasterio.open(truth_path) as src:
        height = src.read(1).astype(np.float32)
        nodata = src.nodata
    valid = ~np.isnan(height)
    if nodata is not None:
        valid &= height != nodata
    if not valid.any():
        return None
    valid_h = height[valid]
    return float(valid_h.max() - valid_h.min())


def find_mislabeled(manifest: list[dict]) -> list[dict]:
    flagged = []
    for entry in manifest:
        if entry["terrain_type"] != FROM_TERRAIN or not entry.get("truth_path"):
            continue
        fracs = _semantic_fracs(entry)
        if fracs is None:
            continue
        building_frac, vegetation_frac = fracs
        if building_frac < BUILDING_FRAC_MIN or vegetation_frac >= VEGETATION_FRAC_MAX:
            continue
        relief = _real_relief(entry)
        if relief is None or relief < MIN_REAL_RELIEF_M:
            continue
        flagged.append({**entry, "_building_frac": building_frac, "_vegetation_frac": vegetation_frac, "_relief": relief})
    return flagged


def _retarget_path(path_str: str) -> str:
    """{split}/forested/{rgb|truth}/filename -> {split}/urban/{rgb|truth}/filename"""
    parts = Path(path_str).parts
    idx = parts.index(FROM_TERRAIN)
    new_parts = parts[:idx] + (TO_TERRAIN,) + parts[idx + 1 :]
    return str(Path(*new_parts))


def apply_relabel(manifest: list[dict], flagged_ids: set[str], dry_run: bool) -> list[dict]:
    updated = []
    moved_files = 0
    for entry in manifest:
        if entry["patch_id"] not in flagged_ids:
            updated.append(entry)
            continue

        new_rgb_path = _retarget_path(entry["rgb_path"])
        new_truth_path = _retarget_path(entry["truth_path"])
        new_depth = DEPTH_CACHE / entry["split"] / TO_TERRAIN / f"{entry['patch_id']}_depth.png"
        new_semantic = SEMANTIC_CACHE / entry["split"] / TO_TERRAIN / f"{entry['patch_id']}_classmap.png"

        moves = [
            (DATA_ROOT / entry["rgb_path"], DATA_ROOT / new_rgb_path),
            (DATA_ROOT / entry["truth_path"], DATA_ROOT / new_truth_path),
            (DEPTH_CACHE / entry["split"] / FROM_TERRAIN / f"{entry['patch_id']}_depth.png", new_depth),
            (SEMANTIC_CACHE / entry["split"] / FROM_TERRAIN / f"{entry['patch_id']}_classmap.png", new_semantic),
        ]
        for src, dst in moves:
            if not src.exists():
                raise FileNotFoundError(f"expected source file missing, aborting: {src}")
            if dst.exists():
                raise FileExistsError(f"destination already exists, aborting to avoid overwrite: {dst}")
            if not dry_run:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
            moved_files += 1

        new_entry = dict(entry)
        new_entry["terrain_type"] = TO_TERRAIN
        new_entry["rgb_path"] = new_rgb_path
        new_entry["truth_path"] = new_truth_path
        updated.append(new_entry)

    print(f"{'[dry-run] would move' if dry_run else 'moved'} {moved_files} files across {len(flagged_ids)} patches")
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report what would change without moving anything")
    args = parser.parse_args()

    manifest = json.load(open(MANIFEST_PATH))
    flagged = find_mislabeled(manifest)
    flagged_ids = {e["patch_id"] for e in flagged}

    print(f"forested patches examined: {sum(1 for e in manifest if e['terrain_type'] == FROM_TERRAIN)}")
    print(f"flagged as mislabeled (building_frac>={BUILDING_FRAC_MIN}, "
          f"vegetation_frac<{VEGETATION_FRAC_MAX}, real_relief>={MIN_REAL_RELIEF_M}m): {len(flagged)}")

    by_split = {}
    for e in flagged:
        by_split.setdefault(e["split"], 0)
        by_split[e["split"]] += 1
    print(f"by split: {by_split}")

    updated_manifest = apply_relabel(manifest, flagged_ids, dry_run=args.dry_run)

    if not args.dry_run:
        backup_path = MANIFEST_PATH.with_suffix(".json.bak_relabel_applied")
        shutil.copy(MANIFEST_PATH, backup_path)
        with open(MANIFEST_PATH, "w") as f:
            json.dump(updated_manifest, f)
        print(f"manifest.json updated ({backup_path.name} is the pre-relabel backup)")
    else:
        print("dry run only -- manifest.json NOT modified")

    return 0


if __name__ == "__main__":
    sys.exit(main())

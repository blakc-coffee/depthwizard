"""Phase 5 Chunk 1 — the real evaluation harness.

Runs the actual `ml.pipeline.run_pipeline()` entrypoint (not the regressor in
isolation) over the held-out test split and computes real RMSE/MAE/Pearson-r
against ground truth, overall and per terrain type.

Design decisions this script embodies (see docs/open_decisions.md, 2026-08-31
"Phase 5 Chunk 1" entries — read those before changing this file):

- Points `run_pipeline()` directly at each patch's real `rgb_path` (option 1
  in docs/phase5.md's Chunk 1 discussion) rather than calling the scalar
  calibration pieces directly, so a real bug anywhere in the pipeline
  (texture export, georeferencing detection, dense fusion wiring) would show
  up here.
- No manifest patch file — including georeferenceable ones — carries a real
  CRS/transform on disk. `_prepare_pipeline_input()` burns the bounds
  `calibration.patch_geo.get_patch_bounds()` already knows how to recover
  analytically onto a temp copy of the RGB tif, so `run_pipeline()` sees
  exactly what a real georeferenced upload would look like. DFC2019 patches
  (permanently non-georeferenceable) are passed through unmodified.
- Only scenes that reach `output_type == "absolute_dsm"` are scored against
  truth (per-pixel, via `dsm_path`). `relative_dsm` scenes have no absolute
  scale to compare and are counted, not silently dropped — see
  `excluded_fraction` in the printed report.

Run: `python ml/validation/evaluate.py [--limit N] [--timing-sample N]`
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_bounds

_ML_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _ML_DIR.parent
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))

import json  # noqa: E402

from calibration.dense_fusion import CONFIDENCE_MEASURED  # noqa: E402
from calibration.patch_geo import GEOREFERENCEABLE_SOURCES, get_patch_bounds  # noqa: E402
from pipeline import run_pipeline  # noqa: E402

DEFAULT_MANIFEST = _REPO_ROOT / "data" / "processed" / "v1" / "manifest.json"
DEFAULT_DATA_ROOT = _REPO_ROOT / "data" / "processed" / "v1"
DEFAULT_FRONTEND_JSON = _REPO_ROOT / "frontend" / "src" / "data" / "validation_report.json"
DEFAULT_DOCS_JSON = _REPO_ROOT / "docs" / "validation_report.json"
TERRAIN_TYPES = ("urban", "sparse", "forested", "hilly")

# Honest, hand-written per docs/phase5.md Chunk 2: this session's already-
# established finding (docs/open_decisions.md, CLAUDE.md "Learned rules") is
# that genuine post-relabeling canopy is the regressor's real structural weak
# point (R^2≈-0.96), not measurable by this script's own dense per-pixel
# comparison since no `forested` patch in this dataset is ever georeferenced
# (DFC2019-only, permanently non-georeferenceable) and therefore never reaches
# `absolute_dsm`. Stating this honestly here, rather than only reporting what
# this particular harness happens to be able to measure (hilly), is the point
# of the "name the weakest category, don't hide it" instruction.
WEAKEST_CATEGORY = {
    "terrain": "forested",
    "reason": (
        "Genuine tree canopy (post-relabeling, isolated from the mislabeled-building "
        "patches this session found and fixed) has the model's real structural weak "
        "point: scalar-regressor R^2≈-0.96 on held-out canopy patches, a permanent "
        "information ceiling (canopy occludes the true ground surface from a single "
        "RGB image), not a training or feature-engineering gap. This dense per-pixel "
        "validation report cannot show that directly — no forested/canopy patch in "
        "this dataset carries real geo-coordinates, so none ever reaches absolute_dsm "
        "to be scored here. hilly is the only terrain this report can measure "
        "end-to-end (SRTM rescues it from a similar, otherwise-unrescuable ceiling); "
        "forested has no equivalent rescue signal available."
    ),
}


def _load_test_entries(manifest_path: Path = DEFAULT_MANIFEST) -> list[dict]:
    manifest = json.load(open(manifest_path))
    return [e for e in manifest if e["split"] == "test" and e.get("truth_path")]


def _load_truth(entry: dict, data_root: Path = DEFAULT_DATA_ROOT) -> np.ma.MaskedArray:
    """Same nan/nodata masking as tools/depth_truth_diff.py::_load_truth."""
    with rasterio.open(data_root / entry["truth_path"]) as src:
        height = src.read(1).astype(np.float32)
        nodata = src.nodata
    valid = ~np.isnan(height)
    if nodata is not None:
        valid &= height != nodata
    return np.ma.masked_where(~valid, height)


def _prepare_pipeline_input(entry: dict, data_root: Path, tmp_dir: Path) -> tuple[Path, object]:
    """Return the path to feed run_pipeline() plus the recovered GeoBounds
    (None if not georeferenceable). For georeferenceable sources, burns the
    analytically-recovered bounds onto a temp copy so run_pipeline() sees a
    real georeferenced file (see module docstring)."""
    rgb_path = data_root / entry["rgb_path"]
    if entry.get("source") not in GEOREFERENCEABLE_SOURCES:
        return rgb_path, None

    bounds = get_patch_bounds(entry)
    if bounds is None:
        return rgb_path, None

    out_path = tmp_dir / f"{entry['patch_id']}_geo.tif"
    with rasterio.open(rgb_path) as src:
        profile = src.profile.copy()
        transform = from_bounds(bounds.west, bounds.south, bounds.east, bounds.north, src.width, src.height)
        profile.update(crs="EPSG:4326", transform=transform)
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(src.read())
    return out_path, bounds


def _score_patch(entry: dict, data_root: Path, tmp_dir: Path) -> dict:
    """Run the real pipeline on one patch, return a result dict. Never
    raises — a pipeline failure on one patch is recorded, not fatal to the
    whole run."""
    patch_out_dir = tmp_dir / entry["patch_id"]
    patch_out_dir.mkdir(parents=True, exist_ok=True)
    try:
        input_path, _ = _prepare_pipeline_input(entry, data_root, tmp_dir)
        result = run_pipeline(input_path, patch_out_dir)
    except Exception as exc:  # noqa: BLE001 — one bad patch must not kill the full pass
        return {"patch_id": entry["patch_id"], "terrain_type": entry["terrain_type"], "status": "error", "error": str(exc)}

    if result.output_type != "absolute_dsm" or not result.dsm_path:
        return {"patch_id": entry["patch_id"], "terrain_type": entry["terrain_type"], "status": "excluded_relative"}

    truth = _load_truth(entry, data_root)
    with rasterio.open(result.dsm_path) as src:
        predicted = src.read(1).astype(np.float32)

    valid = ~np.ma.getmaskarray(truth)
    if predicted.shape != truth.shape or not valid.any():
        return {"patch_id": entry["patch_id"], "terrain_type": entry["terrain_type"], "status": "error", "error": "shape/valid-mask mismatch between dsm_path and truth"}

    pred_valid = predicted[valid]
    truth_valid = np.ma.getdata(truth)[valid]
    errors = pred_valid - truth_valid

    # Fraction of this scene's absolute_dsm pixels directly SRTM-measured vs.
    # model-predicted (ml/calibration/dense_fusion.py's confidence map) — the
    # "confidence-map field" docs/phase5.md Chunk 2 asks the schema to carry
    # alongside the scalar accuracy metrics, not just the metrics themselves.
    srtm_coverage = None
    if result.confidence_map_path:
        from PIL import Image
        confidence = np.array(Image.open(result.confidence_map_path))
        srtm_coverage = float((confidence == CONFIDENCE_MEASURED).mean())

    return {
        "patch_id": entry["patch_id"],
        "terrain_type": entry["terrain_type"],
        "status": "scored",
        "n_pixels": int(valid.sum()),
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "mae": float(np.mean(np.abs(errors))),
        "pred_mean": float(pred_valid.mean()),
        "truth_mean": float(truth_valid.mean()),
        "srtm_coverage": srtm_coverage,
        "pred_valid": pred_valid,  # consumed for pooled stats, stripped before printing
        "truth_valid": truth_valid,
    }


def _pooled_metrics(scored: list[dict]) -> dict:
    if not scored:
        return {
            "rmse": None, "mae": None, "pearson_r": None, "n_pixels": 0, "n_scenes": 0,
            "median_rmse_per_scene": None, "median_mae_per_scene": None, "mean_srtm_coverage": None,
        }
    preds = np.concatenate([r["pred_valid"] for r in scored])
    truths = np.concatenate([r["truth_valid"] for r in scored])
    errors = preds - truths
    coverages = [r["srtm_coverage"] for r in scored if r["srtm_coverage"] is not None]
    return {
        "rmse": float(np.sqrt(np.mean(errors ** 2))),
        "mae": float(np.mean(np.abs(errors))),
        "pearson_r": float(np.corrcoef(preds, truths)[0, 1]) if len(preds) > 1 else None,
        "n_pixels": int(len(errors)),
        "n_scenes": len(scored),
        # Per-scene (not per-pixel) median — the pooled mean above can be
        # dragged by a small number of real outlier scenes (see
        # docs/open_decisions.md 2026-08-31); the median is the honest
        # "typical case" number to lead with.
        "median_rmse_per_scene": float(np.median([r["rmse"] for r in scored])),
        "median_mae_per_scene": float(np.median([r["mae"] for r in scored])),
        "mean_srtm_coverage": float(np.mean(coverages)) if coverages else None,
    }


def _summarize(results: list[dict]) -> dict:
    scored = [r for r in results if r["status"] == "scored"]
    excluded = [r for r in results if r["status"] == "excluded_relative"]
    errored = [r for r in results if r["status"] == "error"]

    by_terrain: dict[str, list[dict]] = defaultdict(list)
    for r in scored:
        by_terrain[r["terrain_type"]].append(r)

    overall = _pooled_metrics(scored)
    per_terrain = {t: _pooled_metrics(rows) for t, rows in by_terrain.items()}

    n_total = len(results)
    return {
        "n_total": n_total,
        "n_scored": len(scored),
        "n_excluded_relative": len(excluded),
        "n_errored": len(errored),
        "excluded_fraction": len(excluded) / n_total if n_total else None,
        "overall": overall,
        "per_terrain": per_terrain,
        "scored_patches": [
            {k: v for k, v in r.items() if k not in ("pred_valid", "truth_valid")} for r in scored
        ],
        "errors": errored,
    }


def _print_report(summary: dict) -> None:
    print(f"\n{'=' * 60}\nDepthWizard Phase 5 — validation report\n{'=' * 60}")
    print(f"total test-split patches: {summary['n_total']}")
    print(f"  scored (absolute_dsm):  {summary['n_scored']}")
    print(f"  excluded (relative_dsm, no absolute scale): {summary['n_excluded_relative']} "
          f"({summary['excluded_fraction']:.1%})")
    print(f"  errored:                {summary['n_errored']}")

    o = summary["overall"]
    if o["n_scenes"]:
        print(f"\nOVERALL (n_scenes={o['n_scenes']}, n_pixels={o['n_pixels']}):")
        print(f"  pooled:  RMSE={o['rmse']:.2f}m  MAE={o['mae']:.2f}m  Pearson r={o['pearson_r']:.3f}")
        print(f"  median (per-scene, honest typical case): RMSE={o['median_rmse_per_scene']:.2f}m  MAE={o['median_mae_per_scene']:.2f}m")
        if o["mean_srtm_coverage"] is not None:
            print(f"  mean SRTM coverage (fraction of pixels directly measured, not model-predicted): {o['mean_srtm_coverage']:.1%}")
    else:
        print("\nOVERALL: no scenes reached absolute_dsm — nothing to score.")

    print("\nPER-TERRAIN:")
    for terrain in TERRAIN_TYPES:
        m = summary["per_terrain"].get(terrain)
        if not m or not m["n_scenes"]:
            print(f"  {terrain:<10} n_scenes=0 (none reached absolute_dsm)")
            continue
        print(f"  {terrain:<10} n_scenes={m['n_scenes']:<4} RMSE={m['rmse']:.2f}m  MAE={m['mae']:.2f}m  r={m['pearson_r']:.3f}  "
              f"(median RMSE={m['median_rmse_per_scene']:.2f}m)")

    print("\nSPOT-CHECK (individual scored patches, predicted vs. truth mean height):")
    for r in summary["scored_patches"]:
        print(f"  {r['patch_id']:<28} {r['terrain_type']:<10} pred_mean={r['pred_mean']:.1f}m "
              f"truth_mean={r['truth_mean']:.1f}m  RMSE={r['rmse']:.1f}m  MAE={r['mae']:.1f}m")

    if summary["errors"]:
        print(f"\nERRORS ({len(summary['errors'])}):")
        for e in summary["errors"][:20]:
            print(f"  {e['patch_id']:<28} {e['terrain_type']:<10} {e['error']}")
        if len(summary["errors"]) > 20:
            print(f"  ... showing 20/{len(summary['errors'])} errors")


def build_report(summary: dict) -> dict:
    """Package Chunk 1's real summary into the frozen validation_report.json
    schema (docs/phase5.md Chunk 2). Every number here comes from `summary` —
    the one exception is WEAKEST_CATEGORY, a hand-written honest text field
    per Chunk 2's explicit instruction (see its module-level comment)."""
    per_terrain = {}
    for terrain in TERRAIN_TYPES:
        m = summary["per_terrain"].get(terrain)
        if not m or not m["n_scenes"]:
            per_terrain[terrain] = {
                "n_scenes": 0,
                "rmse_m": None, "mae_m": None, "pearson_r": None,
                "median_rmse_m": None, "median_mae_m": None,
                "note": "No absolute-scale scenes for this terrain in the held-out test split "
                        "(no real geo-coordinates available to anchor an absolute comparison).",
            }
        else:
            per_terrain[terrain] = {
                "n_scenes": m["n_scenes"],
                "rmse_m": round(m["rmse"], 2),
                "mae_m": round(m["mae"], 2),
                "pearson_r": round(m["pearson_r"], 3) if m["pearson_r"] is not None else None,
                "median_rmse_m": round(m["median_rmse_per_scene"], 2),
                "median_mae_m": round(m["median_mae_per_scene"], 2),
                "note": None,
            }
    hilly_rows = [r for r in summary["scored_patches"] if r["terrain_type"] == "hilly"]
    if hilly_rows:
        median_rmse = per_terrain["hilly"]["median_rmse_m"]
        # An outlier scene here is defined relative to this run's own median,
        # not a fixed meter threshold — stays honest if the outlier set ever
        # changes on a future retrain/rerun, rather than parroting a stale
        # "2 of 47" figure from one specific past run.
        outliers = [r for r in hilly_rows if r["rmse"] > 5 * median_rmse]
        if outliers:
            names = ", ".join(f"{r['patch_id']} ({r['rmse']:.0f}m)" for r in outliers)
            per_terrain["hilly"]["note"] = (
                f"Pooled RMSE/MAE are dragged up by {len(outliers)} of {len(hilly_rows)} real outlier "
                f"scene(s) — {names} — root cause not yet isolated (see docs/open_decisions.md, "
                "2026-08-31). The median columns are the honest typical-case number."
            )

    o = summary["overall"]
    overall = {
        "n_scenes": o["n_scenes"],
        "rmse_m": round(o["rmse"], 2) if o["rmse"] is not None else None,
        "mae_m": round(o["mae"], 2) if o["mae"] is not None else None,
        "pearson_r": round(o["pearson_r"], 3) if o["pearson_r"] is not None else None,
        "median_rmse_m": round(o["median_rmse_per_scene"], 2) if o["median_rmse_per_scene"] is not None else None,
        "median_mae_m": round(o["median_mae_per_scene"], 2) if o["median_mae_per_scene"] is not None else None,
    }

    confidence = {
        "description": (
            "Fraction of absolute_dsm pixels directly measured from SRTM elevation data vs. "
            "model-predicted where SRTM had no coverage (ml/calibration/dense_fusion.py's "
            "confidence map). Reported here as a model-level average across all scored scenes — "
            "a per-scene confidence_map_url is what the per-scene results panel shows for any "
            "single real job (docs/depthwizard.md Section 10.6), a separate, per-image signal "
            "this aggregate is not a substitute for."
        ),
        "mean_srtm_coverage": round(o["mean_srtm_coverage"], 3) if o["mean_srtm_coverage"] is not None else None,
    }

    return {
        "schema_version": "1",
        "generated_by": "ml/validation/evaluate.py",
        "pipeline_entrypoint": "ml.pipeline.run_pipeline",
        "test_split": {
            "n_total": summary["n_total"],
            "n_scored_absolute_dsm": summary["n_scored"],
            "n_excluded_relative_dsm": summary["n_excluded_relative"],
            "n_errored": summary["n_errored"],
            "excluded_fraction": round(summary["excluded_fraction"], 4) if summary["excluded_fraction"] is not None else None,
            "excluded_note": (
                "relative_dsm scenes have no real geo-coordinates to anchor an absolute-scale "
                "comparison against — excluded from RMSE/MAE/correlation, not silently dropped. "
                "This is the large majority of the test split (DFC2019 patches are permanently "
                "non-georeferenceable), not a data-quality problem."
            ),
        },
        "overall": overall,
        "per_terrain": per_terrain,
        "weakest_category": WEAKEST_CATEGORY,
        "confidence": confidence,
    }


def write_report(report: dict, frontend_path: Path = DEFAULT_FRONTEND_JSON, docs_path: Path = DEFAULT_DOCS_JSON) -> None:
    text = json.dumps(report, indent=2) + "\n"
    for path in (frontend_path, docs_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"wrote {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--limit", type=int, default=None, help="score only the first N test entries (debugging)")
    parser.add_argument("--timing-sample", type=int, default=20, help="warm-timing sample size before the full run")
    parser.add_argument("--no-json", action="store_true", help="skip writing validation_report.json (debugging)")
    args = parser.parse_args()

    entries = _load_test_entries(args.manifest)
    if args.limit:
        entries = entries[: args.limit]
    print(f"loaded {len(entries)} test-split patches with truth")

    # Warm-timing check (project's own stated discipline: never trust a cold
    # timing number — the lazy models here are lazily loaded on first call).
    # The sample's own scoring results are kept and pooled into the final
    # summary, not discarded — no reason to run real models on the same
    # patches twice.
    sample_n = min(args.timing_sample, len(entries))
    sample, remaining = entries[:sample_n], entries[sample_n:]
    tmp_dir = Path(tempfile.mkdtemp(prefix="depthwizard_eval_"))
    t0 = time.monotonic()
    try:
        sample_results = [_score_patch(e, DEFAULT_DATA_ROOT, tmp_dir) for e in sample]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    warm_elapsed = time.monotonic() - t0
    per_patch = warm_elapsed / sample_n if sample_n else 0.0
    projected_total = per_patch * len(entries)
    print(f"timing sample: {sample_n} patches in {warm_elapsed:.1f}s ({per_patch:.3f}s/patch) "
          f"-> projected full run: {projected_total / 60:.1f} min for {len(entries)} patches")

    tmp_dir = Path(tempfile.mkdtemp(prefix="depthwizard_eval_"))
    try:
        rest_results = [_score_patch(e, DEFAULT_DATA_ROOT, tmp_dir) for e in remaining]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    summary = _summarize(sample_results + rest_results)
    _print_report(summary)
    print(f"\nfull scoring pass took {time.monotonic() - t0:.1f}s total")

    if not args.no_json:
        report = build_report(summary)
        write_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())

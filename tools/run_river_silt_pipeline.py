#!/usr/bin/env python3
"""Local river-silt ML harness. No FastAPI, Redis, Celery, or auth needed.

Run against any real RGB image without any backend infrastructure running:

    python tools/run_river_silt_pipeline.py path/to/river_crop.tif
    python tools/run_river_silt_pipeline.py path/to/river_crop.jpg --out /tmp/silt_out

Prints the resulting SiltPipelineResult as JSON — mirrors run_pipeline.py's
role for the height use case (PRD §9's "confirm the pipeline output shape
without anyone's backend running").

See ml/river_silt_pipeline.py's module docstring for what's real vs stylized
in the output (heatmap spatial detail and cross-section shape are real
image-derived signal, not a verified water/bathymetry survey).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ml.river_silt_pipeline import run_silt_pipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Path to a PNG/JPEG/GeoTIFF river image")
    parser.add_argument("--out", type=Path, default=None, help="Output directory (defaults to a temp dir)")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Input not found: {args.input}", file=sys.stderr)
        return 1

    workdir = str(args.out) if args.out else tempfile.mkdtemp(prefix="depthwizard-silt-")
    result = run_silt_pipeline(str(args.input), workdir)

    print(json.dumps({
        "output_type": result.output_type,
        "predicted_ssc_mg_l": round(result.predicted_ssc_mg_l, 2),
        "dredging_level": result.dredging_level,
        "dredging_label": result.dredging_label,
        "heatmap_path": result.heatmap_path,
        "texture_path": result.texture_path,
        "cross_section_profile": result.cross_section_profile,
        "warnings": result.warnings,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

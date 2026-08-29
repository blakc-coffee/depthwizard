#!/usr/bin/env python3
"""Local ML harness. No FastAPI, Redis, Celery or auth needed.

Run against a sample image without any backend infrastructure running:

    python tools/run_pipeline.py path/to/sample.tif
    python tools/run_pipeline.py path/to/sample.png --out /tmp/depthwizard_out

Prints the resulting PipelineResult as JSON and checks it against the frozen
contract (integration/contracts.py) — this is how the ML team can confirm
their pipeline's output shape is correct without anyone's backend running.

By default this runs a non-strict check (fields not yet implemented, like
`heightmap_path`, are reported but don't fail the run) since `ml/pipeline.py`
is still partial. Pass --strict once ML Phase 4/5 lands to enforce the full
contract — that's also what the production worker task uses as its gate.

Owner: Backend Engineer B. See PRD §9.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integration.pipeline_runner import run_pipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Path to a PNG/JPEG/GeoTIFF image")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("/tmp/depthwizard_run"),
        help="Directory to write pipeline artifacts to (default: /tmp/depthwizard_run)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on any contract gap, including fields not yet implemented (ML Phase 4/5)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    result = run_pipeline(args.input, args.out)

    print(json.dumps(result.to_dict(), indent=2, default=str))

    problems = result.validate(strict=args.strict)
    if problems:
        print("\ncontract check:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1 if args.strict else 0

    print("\ncontract check: OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

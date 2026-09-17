"""Adapter: backend -> ml/change_detection/diff.py (Merged PRD §8, §9.9).

Same pattern as pipeline_runner.py: the ML import is deferred until a
comparison actually runs, so the API image never needs ml/ or its libraries.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from integration.contracts import CompareResult

_ML_DIR = Path(__file__).resolve().parent.parent / "ml"


class CompareModelUnavailable(Exception):
    """ml/change_detection/diff.py doesn't provide compute_height_change yet."""


def _import_compute_height_change():
    if str(_ML_DIR) not in sys.path:
        sys.path.insert(0, str(_ML_DIR))
    try:
        from change_detection.diff import compute_height_change
    except ImportError as exc:
        raise CompareModelUnavailable("Comparison model not available yet.") from exc
    return compute_height_change


def run_compare(
    *,
    before_heightmap_path: str | Path,
    after_heightmap_path: str | Path,
    before_metadata: dict[str, Any],
    after_metadata: dict[str, Any],
    output_dir: str | Path,
    before_dsm_path: str | Path | None = None,
    after_dsm_path: str | Path | None = None,
) -> CompareResult:
    compute_height_change = _import_compute_height_change()
    ml_result = compute_height_change(
        before_heightmap_path=str(before_heightmap_path),
        after_heightmap_path=str(after_heightmap_path),
        before_metadata=dict(before_metadata),
        after_metadata=dict(after_metadata),
        output_dir=str(output_dir),
        before_dsm_path=str(before_dsm_path) if before_dsm_path else None,
        after_dsm_path=str(after_dsm_path) if after_dsm_path else None,
    )
    return CompareResult(
        diff_map_path=str(ml_result.diff_map_path),
        metadata=dict(ml_result.metadata),
        warnings=list(ml_result.warnings),
    )

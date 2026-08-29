"""Adapter: backend -> ml/pipeline.py.

Owner: Backend Engineer B. See PRD §9.

ml/pipeline.py is not a package (no __init__.py), and its own internal
imports — e.g. `from utils.texture_export import export_texture` — are flat,
resolved relative to ml/ itself being on sys.path, not `ml.pipeline` as a
submodule of a top-level `ml` package. This adapter is the one place that
knows that and does the sys.path setup, so nothing else in backend/ has to.
"""

from __future__ import annotations

import sys
from pathlib import Path

from integration.contracts import PipelineResult

_ML_DIR = Path(__file__).resolve().parent.parent / "ml"
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))


def _import_ml_pipeline():
    # Deferred until actually called: the API process references this
    # module (to enqueue tasks by name) without ever needing ml/'s heavy
    # dependencies — only the worker process actually runs this.
    import pipeline as ml_pipeline  # flat import; see module docstring

    return ml_pipeline


def run_pipeline(input_path: str | Path, output_dir: str | Path) -> PipelineResult:
    """image in -> canonical PipelineResult out.

    Calls ml/pipeline.py::run_pipeline and normalizes its output onto the
    frozen contract. Corrects shape/semantics discrepancies here, never by
    reinterpreting ML's actual output values (Merged PRD §9.10 B4 guidance:
    "correct discrepancies in the adapter, never by mutating ML output
    semantics").
    """
    ml_pipeline = _import_ml_pipeline()
    ml_result = ml_pipeline.run_pipeline(input_path, output_dir)

    # ml/pipeline.py defaults `metrics` to {} (empty dict); the frozen
    # contract requires None when no reference data exists, never {} (§9.6).
    metrics = ml_result.metrics or None

    return PipelineResult(
        output_type=ml_result.output_type,
        texture_path=ml_result.texture_path,
        heightmap_path=ml_result.heightmap_path,
        heightmap_16bit_path=getattr(ml_result, "heightmap_16bit_path", None),
        confidence_map_path=ml_result.confidence_map_path,
        dsm_path=ml_result.dsm_path,
        metadata=dict(ml_result.metadata),
        metrics=metrics,
        warnings=list(ml_result.warnings),
    )

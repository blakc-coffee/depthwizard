"""End-to-end test for ml/pipeline.py's Stage A wiring.

Runs the real Depth Anything V2 backbone (cached locally after Phase 1) — no
network required, but this is the slow test in the suite: run it whenever
depth/backbone.py, pipeline.py, or the contract in integration/contracts.py
change, not on every save.

Goes through integration.pipeline_runner rather than calling ml.pipeline
directly: that's the actual production entry point (same one
backend/app/tasks/process_image.py uses), and it's what converts ml/
pipeline.py's local, minimal PipelineResult into the frozen contract object
that has .validate() — ml/pipeline.py deliberately does not import
integration/contracts.py itself, to keep ml/ importable standalone with zero
backend dependencies.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integration.pipeline_runner import run_pipeline  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "depth" / "samples"


def _first_sample() -> Path:
    samples = sorted(SAMPLE_DIR.glob("*.jpg"))
    if not samples:
        import pytest

        pytest.skip(f"no sample images in {SAMPLE_DIR} — see ml/depth/PHASE1_NOTES.md")
    return samples[0]


def test_run_pipeline_produces_a_contract_valid_relative_result(tmp_path):
    result = run_pipeline(_first_sample(), tmp_path)

    problems = result.validate(strict=True)
    assert problems == []

    # Honesty rule (docs/depthwizard.md Section 1): calibration isn't built
    # yet, so nothing may claim absolute/metric height regardless of input.
    assert result.output_type == "relative_dsm"
    assert result.metadata["height_units"] == "relative"
    assert result.warnings  # the calibration-not-implemented warning must be visible


def test_run_pipeline_heightmap_is_pixel_aligned_with_texture(tmp_path):
    from PIL import Image

    result = run_pipeline(_first_sample(), tmp_path)

    texture = Image.open(result.texture_path)
    heightmap = Image.open(result.heightmap_path)
    assert texture.size == heightmap.size
    assert heightmap.mode == "LA"  # grey=height, alpha=NoData validity (Section 9.6)

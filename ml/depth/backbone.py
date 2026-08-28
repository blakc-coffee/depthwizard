"""Depth Anything V2 wrapper — relative depth extraction (Phase 1).

Interface is frozen per Phase 1, Chunk 4: image in, relative depth map out.
No absolute/metric scale, no calibration — see docs/phase1.md.
"""

from PIL import Image
from transformers import pipeline

MODEL_ID = "depth-anything/Depth-Anything-V2-Base-hf"
DEVICE = "mps"

_pipe = None


def _get_pipe():
    global _pipe
    if _pipe is None:
        _pipe = pipeline(task="depth-estimation", model=MODEL_ID, device=DEVICE)
    return _pipe


def estimate_relative_depth(image: Image.Image) -> Image.Image:
    """Run Depth Anything V2 on a single PIL image, return a relative depth map as a PIL image."""
    return _get_pipe()(image)["depth"]


def estimate_relative_depth_batch(images: list[Image.Image]) -> list[Image.Image]:
    """Run Depth Anything V2 on a batch of PIL images, return a list of relative depth maps."""
    return [out["depth"] for out in _get_pipe()(images)]

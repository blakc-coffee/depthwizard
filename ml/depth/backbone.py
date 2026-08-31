"""Depth Anything V2 wrapper — relative depth extraction (Phase 1).

Interface is frozen per Phase 1, Chunk 4: image in, relative depth map out.
No absolute/metric scale, no calibration — see docs/phase1.md.
"""

import logging

import torch
from PIL import Image
from transformers import pipeline

logger = logging.getLogger(__name__)

MODEL_ID = "depth-anything/Depth-Anything-V2-Base-hf"


def _detect_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


DEVICE = _detect_device()
logger.info("ml.depth.backbone: using device=%s", DEVICE)

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

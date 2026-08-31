"""Tests for ml/depth/backbone.py — device-selection logic only.

Does not exercise estimate_relative_depth()/_batch() here (that requires the
real Depth Anything V2 weights and is covered end-to-end by test_pipeline.py
instead, so the heavy model load happens once, not once per test file).
"""

from depth import backbone


def test_prefers_cuda_when_available(monkeypatch):
    monkeypatch.setattr(backbone.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(backbone.torch.backends.mps, "is_available", lambda: True)
    assert backbone._detect_device() == "cuda"


def test_falls_back_to_mps_when_no_cuda(monkeypatch):
    monkeypatch.setattr(backbone.torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(backbone.torch.backends.mps, "is_available", lambda: True)
    assert backbone._detect_device() == "mps"


def test_falls_back_to_cpu_when_nothing_available(monkeypatch):
    monkeypatch.setattr(backbone.torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(backbone.torch.backends.mps, "is_available", lambda: False)
    assert backbone._detect_device() == "cpu"

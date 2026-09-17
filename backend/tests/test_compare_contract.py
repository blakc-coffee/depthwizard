"""CompareResult contract and compare_runner adapter — no DB or infra required."""

from __future__ import annotations

import sys
import types

import pytest

from integration.compare_runner import CompareModelUnavailable, run_compare
from integration.contracts import CompareResult


def _metadata(**overrides):
    base = {"height_units": "relative", "max_loss": -12.0, "max_gain": 4.0, "changed_area_fraction": 0.2, "threshold": 2.0}
    base.update(overrides)
    return base


def _relative(**overrides):
    return CompareResult(diff_map_path="diff.png", metadata=_metadata(**overrides), warnings=["relative change only"])


def test_valid_relative_comparison_passes():
    assert _relative().validate(both_absolute=False) == []


def test_valid_metric_comparison_passes():
    result = CompareResult(diff_map_path="diff.png", metadata=_metadata(height_units="m"))
    assert result.validate(both_absolute=True) == []


def test_metres_require_both_sources_absolute():
    problems = _relative(height_units="m").validate(both_absolute=False)
    assert any("requires both source jobs" in p for p in problems)


def test_relative_comparison_requires_a_warning():
    result = CompareResult(diff_map_path="diff.png", metadata=_metadata())
    assert any("warning is required" in p for p in result.validate(both_absolute=False))


def test_missing_diff_map_and_metadata_keys_are_reported():
    result = CompareResult(diff_map_path="", metadata={"height_units": "relative"}, warnings=["w"])
    problems = result.validate(both_absolute=False)
    assert any("diff_map_path is required" in p for p in problems)
    assert any("missing required keys" in p for p in problems)


@pytest.mark.parametrize(
    "key, value",
    [
        ("max_loss", 1.5),
        ("max_gain", -0.5),
        ("changed_area_fraction", 1.2),
        ("threshold", 0),
        ("max_loss", float("nan")),
        ("threshold", True),
        ("max_gain", "3"),
    ],
)
def test_out_of_range_or_non_numeric_values_are_reported(key, value):
    problems = _relative(**{key: value}).validate(both_absolute=False)
    assert any(key in p for p in problems)


def test_unknown_height_units_are_reported():
    assert any("height_units must be one of" in p for p in _relative(height_units="ft").validate(both_absolute=False))


def _install_fake_ml(monkeypatch, diff_module):
    monkeypatch.setitem(sys.modules, "change_detection", types.ModuleType("change_detection"))
    monkeypatch.setitem(sys.modules, "change_detection.diff", diff_module)


def test_run_compare_raises_when_ml_function_missing(monkeypatch):
    _install_fake_ml(monkeypatch, types.ModuleType("change_detection.diff"))
    with pytest.raises(CompareModelUnavailable):
        run_compare(
            before_heightmap_path="b.png", after_heightmap_path="a.png",
            before_metadata={}, after_metadata={}, output_dir="out",
        )


def test_run_compare_passes_inputs_and_normalizes_output(monkeypatch):
    received = {}

    def compute_height_change(**kwargs):
        received.update(kwargs)
        return types.SimpleNamespace(diff_map_path=f"{kwargs['output_dir']}/diff.png", metadata=_metadata(), warnings=("w",))

    module = types.ModuleType("change_detection.diff")
    module.compute_height_change = compute_height_change
    _install_fake_ml(monkeypatch, module)

    result = run_compare(
        before_heightmap_path="b.png", after_heightmap_path="a.png",
        before_metadata={"height_units": "relative"}, after_metadata={"height_units": "relative"},
        output_dir="out", after_dsm_path="after.tif",
    )

    assert isinstance(result, CompareResult)
    assert result.diff_map_path == "out/diff.png"
    assert result.warnings == ["w"]
    assert received["before_dsm_path"] is None and received["after_dsm_path"] == "after.tif"
    assert result.validate(both_absolute=False) == []

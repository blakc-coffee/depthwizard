#!/usr/bin/env python3
"""River-silt use case — Köppen climate zone lookup.

A legitimate regional proxy feature, not raw lat/lon. Literature review
(docs/open_decisions.md, 2026-09-14) found one study's SHAP analysis ranked
longitude as the single strongest SSC predictor — flagged at the time as a
likely leakage trap (a global model could just be memorizing "which river
is this" via coordinates, rather than learning transferable turbidity
signal). Real bottleneck testing (2026-09-15) found nothing else (features,
masking, log-target, 15x more data) moved R^2 at all, which points at a
structural cause: water's baseline color depends heavily on regional
geology/soil/land-use, not just instantaneous turbidity, so a global
color-only model may be underdetermined without *some* regional context.

Köppen-Geiger climate zone is the compromise: real, physically meaningful,
and coarse enough (5 top-level groups covering the whole planet) that it
cannot memorize an individual river the way raw coordinates could — many
completely different rivers worldwide share the same top-level zone.

Data: Koeppen-Geiger-ASCII.txt (Vienna TU, 0.5-degree global grid, tiny —
244KB zipped), ml/data/river_silt_raw/koppen/ (gitignored, matches this
project's river-silt-raw-data convention).
"""

from __future__ import annotations

import math
from pathlib import Path

DEFAULT_TABLE_PATH = Path(__file__).resolve().parent.parent / "data" / "river_silt_raw" / "koppen" / "Koeppen-Geiger-ASCII.txt"
KOPPEN_GROUPS = ["A", "B", "C", "D", "E"]  # tropical, arid, temperate, continental, polar

_table_cache: dict[tuple[float, float], str] | None = None


def _load_table(path: Path = DEFAULT_TABLE_PATH) -> dict[tuple[float, float], str]:
    global _table_cache
    if _table_cache is not None:
        return _table_cache
    table: dict[tuple[float, float], str] = {}
    with open(path) as f:
        next(f)  # header
        for line in f:
            parts = line.split()
            if len(parts) != 3:
                continue
            lat, lon, cls = parts
            table[(float(lat), float(lon))] = cls
    _table_cache = table
    return table


def _nearest_grid_center(value: float) -> float:
    """Table is a regular 0.5-degree grid, centers at x.25/x.75 — snap to
    the nearest one rather than doing a real nearest-neighbor search."""
    return math.floor(value * 2) / 2 + 0.25


def get_koppen_group(lat: float, lon: float, table_path: Path = DEFAULT_TABLE_PATH) -> str | None:
    """Returns one of KOPPEN_GROUPS, or None for a grid cell the table has
    no classification for (open ocean far from any station, Antarctic
    interior, etc.) — real gaps in the source data, not guessed around."""
    subtype = get_koppen_subtype(lat, lon, table_path)
    return subtype[0] if subtype else None


def get_koppen_subtype(lat: float, lon: float, table_path: Path = DEFAULT_TABLE_PATH) -> str | None:
    """Full Köppen subtype (e.g. 'Cfa', not just 'C') — finer regional
    resolution than get_koppen_group(), tried after the 5-group version
    showed real feature importance but didn't move accuracy
    (docs/open_decisions.md, 2026-09-15). ~30 real subtypes exist globally
    (checked directly against the source table, not assumed)."""
    table = _load_table(table_path)
    key = (_nearest_grid_center(lat), _nearest_grid_center(lon))
    return table.get(key)

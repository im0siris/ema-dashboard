"""Mode definitions: scorer composition, gates, sort key.

A mode is pure config — what scorers to run, how to weight them, what
gates to apply post-scoring, what to sort by. No scoring logic lives here.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

import config
from scorers import (
    AlignmentScorer,
    BaseBreakScorer,
    CompressionScorer,
    FlatAgainstBandScorer,
    Scorer,
    SqueezeScorer,
    VolumeProfileScorer,
    WeeklySetupScorer,
)


@dataclass
class Gate:
    """A pass/fail filter applied to a result dict after scoring."""
    field: str
    op: str    # eq | ne | gt | gte | lt | lte | in
    value: Any

    def passes(self, result: dict) -> bool:
        v = result.get(self.field)
        if v is None:
            return False
        try:
            if self.op == "eq":  return v == self.value
            if self.op == "ne":  return v != self.value
            if self.op == "gt":  return v > self.value
            if self.op == "gte": return v >= self.value
            if self.op == "lt":  return v < self.value
            if self.op == "lte": return v <= self.value
            if self.op == "in":  return v in self.value
        except TypeError:
            return False
        raise ValueError(f"Unknown gate op: {self.op}")


@dataclass
class Mode:
    name: str
    description: str
    scorers: list[Scorer]
    weights: dict[str, float]
    gates: list[Gate]
    sort_by: str
    sort_desc: bool = True
    regime_warn: bool = False
    regime_gate: bool = False
    required_period: str = config.YF_DEFAULT_PERIOD
    implemented: bool = True
    display_columns: list[str] | None = None


def composite_score(result: dict, weights: dict[str, float]) -> float:
    total = 0.0
    weight_sum = 0.0
    for sname, w in weights.items():
        key = f"{sname}_score"
        v = result.get(key)
        if v is None or _is_nan(v):
            continue
        total += float(v) * w
        weight_sum += w
    return total / weight_sum if weight_sum > 0 else 0.0


def _is_nan(v) -> bool:
    try:
        return v != v
    except Exception:
        return False


# ============================================================================
# Mode definitions
# ============================================================================

COMPRESSION_MODE = Mode(
    name="compression",
    description="Tight EMA9/EMA21/SMA50 compression with bullish stack and price > SMA50",
    scorers=[CompressionScorer()],
    weights={"compression": 1.0},
    gates=[
        Gate("compression_alignment", "eq", "BULLISH"),
        Gate("compression_above_sma50", "eq", True),
        Gate("compression_pct", "lte", config.COMPRESSION_DEFAULT_MAX_SPREAD),
    ],
    sort_by="compression_pct",
    sort_desc=False,
    display_columns=[
        "ticker", "name", "market_cap_m",
        "compression_close", "compression_ema9", "compression_ema21", "compression_sma50",
        "compression_pct", "compression_alignment", "compression_score",
    ],
)


FULL_SETUP_MODE = Mode(
    name="full_setup",
    description="Composite of alignment + flat_against_band + squeeze + weekly_setup + base_break + volume_profile",
    scorers=[
        AlignmentScorer(),
        FlatAgainstBandScorer(),
        SqueezeScorer(),
        WeeklySetupScorer(),
        BaseBreakScorer(),
        VolumeProfileScorer(),
    ],
    weights={
        "alignment": 1.0,
        "flat_against_band": 1.5,
        "squeeze": 1.0,
        "weekly_setup": 1.0,
        "base_break": 1.0,
        "volume_profile": 0.5,
    },
    gates=[],
    sort_by="composite_score",
    sort_desc=True,
    required_period="5y",
    implemented=True,
    display_columns=[
        "ticker", "name", "market_cap_m", "composite_score",
        "alignment_label", "alignment_count",
        "flat_against_band_distance_pct", "flat_against_band_is_inside_band",
        "squeeze_active", "squeeze_overhead_ma",
        "weekly_setup_score", "weekly_setup_alignment_count",
        "base_break_active", "base_break_years_of_base",
        "volume_profile_label", "volume_profile_ratio",
    ],
)


MODES: dict[str, Mode] = {m.name: m for m in [COMPRESSION_MODE, FULL_SETUP_MODE]}


def get_mode(name: str) -> Mode:
    if name not in MODES:
        raise ValueError(f"Unknown mode: {name}. Available: {list(MODES.keys())}")
    return MODES[name]

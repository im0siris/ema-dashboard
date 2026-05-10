"""Scorer ABC + helpers."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import pandas as pd


class Scorer(ABC):
    """Base class for all scorers.

    Subclasses declare:
        name: short identifier (used as prefix for output keys, mode weights).
        required_frames: tuple of frame names ("daily", "weekly", "monthly")
            that must be present in the frames dict passed to score().
    """
    name: ClassVar[str]
    required_frames: ClassVar[tuple[str, ...]]

    @abstractmethod
    def score(self, frames: dict[str, pd.DataFrame], regime: Any) -> dict[str, Any]:
        """Compute scoring outputs for one ticker.

        Args:
            frames: {"daily": DataFrame, "weekly": DataFrame, "monthly": DataFrame}
                Each DataFrame is augmented with MA columns by indicators.add_mas().
            regime: RegimeState (or None if --no-regime). Scorers that don't use
                the regime may ignore this argument.

        Returns:
            Flat dict of fields. Keys are prefixed with self.name (e.g.
            "compression_score", "compression_pct"). One key MUST be
            "{name}_score" — a float in [0, 100] used for composite scoring.
        """
        ...

    def validate_frames(self, frames: dict[str, pd.DataFrame]) -> None:
        missing = [f for f in self.required_frames if f not in frames]
        if missing:
            raise ValueError(
                f"Scorer {self.name!r} requires frames {missing} but only "
                f"received {list(frames.keys())}"
            )

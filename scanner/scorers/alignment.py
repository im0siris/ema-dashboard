"""Bullish stack of moving averages.

Spec:
    c1 = ema9 > ema21
    c2 = ema21 > sma50
    c3 = sma50 > sma200
    alignment_count = c1 + c2 + c3   # 0..3
    alignment_score = count / 3 * 100  # 0/33.33/66.67/100

Labels: FULL_BULL (3), PARTIAL_BULL (2), MIXED (1), BEAR (0).

Insufficient data: if any of the four MAs is NaN we return INSUFFICIENT_DATA.
This typically means the period passed to data.download_with_cache was shorter
than 200 trading days (sma200 needs >=200 closes). The full_setup mode declares
required_period="5y" so this only fires for misconfigured ad-hoc modes.

Required frames: daily.
"""
from typing import Any

import pandas as pd

from scorers.base import Scorer

_LABELS = {3: "FULL_BULL", 2: "PARTIAL_BULL", 1: "MIXED", 0: "BEAR"}


class AlignmentScorer(Scorer):
    name = "alignment"
    required_frames = ("daily",)

    def score(self, frames: dict[str, pd.DataFrame], regime: Any) -> dict[str, Any]:
        self.validate_frames(frames)
        last = frames["daily"].iloc[-1]
        ema9, ema21 = last["ema9"], last["ema21"]
        sma50, sma200 = last["sma50"], last["sma200"]

        if any(pd.isna(v) for v in (ema9, ema21, sma50, sma200)):
            return {
                "alignment_score": 0.0,
                "alignment_label": "INSUFFICIENT_DATA",
                "alignment_count": 0,
                "alignment_ema9_gt_ema21": False,
                "alignment_ema21_gt_sma50": False,
                "alignment_sma50_gt_sma200": False,
            }

        c1 = bool(ema9 > ema21)
        c2 = bool(ema21 > sma50)
        c3 = bool(sma50 > sma200)
        count = int(c1) + int(c2) + int(c3)

        return {
            "alignment_score": round(count / 3 * 100, 2),
            "alignment_label": _LABELS[count],
            "alignment_count": count,
            "alignment_ema9_gt_ema21": c1,
            "alignment_ema21_gt_sma50": c2,
            "alignment_sma50_gt_sma200": c3,
        }

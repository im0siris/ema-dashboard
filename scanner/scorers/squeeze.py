"""Price compressed between rising small EMAs and an overhead larger SMA.

Spec:
    small_mas_below = close > ema9 and close > ema21
    overhead_ma = SMA100 if close < sma100 else (SMA200 if close < sma200 else None)
    overhead_distance_pct = (overhead - close) / close * 100  (None if no overhead)

    ema9_slope_5d  = (ema9[-1]  - ema9[-6])  / ema9[-6]
    ema21_slope_5d = (ema21[-1] - ema21[-6]) / ema21[-6]
    emas_rising = ema9_slope_5d > 0 and ema21_slope_5d > 0

    squeeze_active = (
        small_mas_below
        and overhead_ma is not None
        and overhead_distance_pct < SQUEEZE_OVERHEAD_MAX_PCT (5.0)
        and emas_rising
    )

    squeeze_score = (100 if active else 0) + (20 if active and overhead == SMA200 else 0)
                  capped at 100
    (Per spec: SMA200 bonus exists but the cap nullifies it at base=100. Left as
    written; raise base or cap if you want the bonus to bite.)

Required frames: daily (with at least SQUEEZE_SLOPE_LOOKBACK + 1 = 6 rows).
"""
from typing import Any

import pandas as pd

import config
from scorers.base import Scorer


class SqueezeScorer(Scorer):
    name = "squeeze"
    required_frames = ("daily",)

    def score(self, frames: dict[str, pd.DataFrame], regime: Any) -> dict[str, Any]:
        self.validate_frames(frames)
        d = frames["daily"]

        if len(d) < config.SQUEEZE_SLOPE_LOOKBACK + 1:
            return _insufficient()

        last = d.iloc[-1]
        prev = d.iloc[-(config.SQUEEZE_SLOPE_LOOKBACK + 1)]  # i.e. iloc[-6] for lookback=5

        ema9, ema21 = last["ema9"], last["ema21"]
        sma100, sma200, close = last["sma100"], last["sma200"], last["close"]
        ema9_prev, ema21_prev = prev["ema9"], prev["ema21"]

        if any(pd.isna(v) for v in (ema9, ema21, sma100, sma200, close, ema9_prev, ema21_prev)):
            return _insufficient()

        small_mas_below = bool(close > ema9 and close > ema21)

        if close < sma100:
            overhead_label, overhead_val = "SMA100", float(sma100)
        elif close < sma200:
            overhead_label, overhead_val = "SMA200", float(sma200)
        else:
            overhead_label, overhead_val = None, None

        if overhead_val is not None:
            overhead_distance_pct = (overhead_val - float(close)) / float(close) * 100.0
        else:
            overhead_distance_pct = None

        ema9_slope  = (float(ema9)  - float(ema9_prev))  / float(ema9_prev)  if ema9_prev  else 0.0
        ema21_slope = (float(ema21) - float(ema21_prev)) / float(ema21_prev) if ema21_prev else 0.0
        emas_rising = bool(ema9_slope > 0 and ema21_slope > 0)

        active = bool(
            small_mas_below
            and overhead_val is not None
            and overhead_distance_pct < config.SQUEEZE_OVERHEAD_MAX_PCT
            and emas_rising
        )

        base = 100.0 if active else 0.0
        bonus = 20.0 if (active and overhead_label == "SMA200") else 0.0
        score = min(base + bonus, 100.0)

        return {
            "squeeze_score": score,
            "squeeze_active": active,
            "squeeze_overhead_ma": overhead_label,
            "squeeze_overhead_distance_pct": (
                round(overhead_distance_pct, 3) if overhead_distance_pct is not None else None
            ),
            "squeeze_small_mas_below": small_mas_below,
            "squeeze_emas_rising": emas_rising,
            "squeeze_ema9_slope_5d": round(ema9_slope, 5),
            "squeeze_ema21_slope_5d": round(ema21_slope, 5),
        }


def _insufficient() -> dict[str, Any]:
    return {
        "squeeze_score": 0.0,
        "squeeze_active": False,
        "squeeze_overhead_ma": None,
        "squeeze_overhead_distance_pct": None,
        "squeeze_small_mas_below": False,
        "squeeze_emas_rising": False,
        "squeeze_ema9_slope_5d": 0.0,
        "squeeze_ema21_slope_5d": 0.0,
    }

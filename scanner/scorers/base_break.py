"""Multi-year base breakout on the monthly chart.

Spec:
    if len(monthly_df) < BASE_BREAK_LOOKBACK_MONTHS (60):
        return base_break_active=False, years_of_base=0, score=0

    historical_max = monthly_df["close"].iloc[-60:-1].max()  # 59 months pre-current
    base_break = current_close > historical_max

    years_of_base: walk back from index len-2; first row with close >= historical_max
    fixes the base length. years_of_base = (len-1 - i) / 12.

    breakout_volume = monthly_df["volume"].iloc[-1] >
        BASE_BREAK_VOL_MULTIPLIER (1.5) * monthly_df["volume"].iloc[-13:-1].mean()

    base_break_score = (100 if break else 0) + (20 if break and volume else 0)
                     capped at 100
    (Per spec: SMA200-style cap nullifies the volume bonus when base=100. Left
    as written.)

Required frames: monthly. Upstream period must be >=5y so the monthly resample
yields >=60 rows.
"""
from typing import Any

import pandas as pd

import config
from scorers.base import Scorer


class BaseBreakScorer(Scorer):
    name = "base_break"
    required_frames = ("monthly",)

    def score(self, frames: dict[str, pd.DataFrame], regime: Any) -> dict[str, Any]:
        self.validate_frames(frames)
        m = frames["monthly"]

        if len(m) < config.BASE_BREAK_LOOKBACK_MONTHS:
            return _default()

        if "close" not in m.columns or "volume" not in m.columns:
            return _default()

        current_close = float(m["close"].iloc[-1])
        prior_window = m["close"].iloc[-config.BASE_BREAK_LOOKBACK_MONTHS:-1]
        if prior_window.empty or pd.isna(current_close):
            return _default()

        historical_max = float(prior_window.max())
        active = bool(current_close > historical_max)

        years_of_base = 0.0
        if active:
            for i in range(len(m) - 2, -1, -1):
                v = m["close"].iloc[i]
                if pd.isna(v):
                    continue
                if float(v) >= historical_max:
                    years_of_base = (len(m) - 1 - i) / 12.0
                    break

        vol_lookback = config.BASE_BREAK_VOL_LOOKBACK_MONTHS
        recent_vol = float(m["volume"].iloc[-1])
        baseline_vol_mean = float(m["volume"].iloc[-(vol_lookback + 1):-1].mean())
        breakout_volume = bool(
            baseline_vol_mean > 0
            and recent_vol > config.BASE_BREAK_VOL_MULTIPLIER * baseline_vol_mean
        )

        base = 100.0 if active else 0.0
        bonus = 20.0 if (active and breakout_volume) else 0.0
        score = min(base + bonus, 100.0)

        return {
            "base_break_score": score,
            "base_break_active": active,
            "base_break_years_of_base": round(years_of_base, 2),
            "base_break_breakout_volume": breakout_volume,
            "base_break_historical_max": round(historical_max, 2),
            "base_break_current_close": round(current_close, 2),
        }


def _default() -> dict[str, Any]:
    return {
        "base_break_score": 0.0,
        "base_break_active": False,
        "base_break_years_of_base": 0.0,
        "base_break_breakout_volume": False,
        "base_break_historical_max": float("nan"),
        "base_break_current_close": float("nan"),
    }

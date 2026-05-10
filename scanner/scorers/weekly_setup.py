"""Weekly chart confirmation.

Spec (computed on the resampled weekly frame):
    weekly_above_9ema  = close_w > ema9_w
    weekly_above_21ema = close_w > ema21_w
    weekly_alignment_count = sum([
        ema9_w > ema21_w,
        ema21_w > sma50_w,
        sma50_w > sma200_w,
    ])

    Cross detection: did weekly ema9 cross above weekly sma200 within the last
    WEEKLY_CROSS_LOOKBACK_WEEKS (4) weeks? Iterates the last N rows and looks for
    a row where ema9 went from <= sma200 to > sma200 vs the prior row. Matches
    the spec's `recent_window = weekly_df.iloc[-N:]` slice — note that yields
    N-1 transitions inside a window of N rows.

    weekly_score = (
        (weekly_above_9ema  * 25)
      + (weekly_above_21ema * 15)
      + (weekly_alignment_count / 3 * 40)
      + (crossed_recently * 20)
    )  # 0..100

Required frames: weekly. Note: weekly sma200 needs ~200 weeks of history
(~4 years), so the upstream period must be >=5y for this scorer to be useful.
"""
from typing import Any

import pandas as pd

import config
from scorers.base import Scorer


class WeeklySetupScorer(Scorer):
    name = "weekly_setup"
    required_frames = ("weekly",)

    def score(self, frames: dict[str, pd.DataFrame], regime: Any) -> dict[str, Any]:
        self.validate_frames(frames)
        w = frames["weekly"]

        if len(w) < 2:
            return _insufficient()

        last = w.iloc[-1]
        close, ema9, ema21 = last["close"], last["ema9"], last["ema21"]
        sma50, sma200 = last["sma50"], last["sma200"]

        if any(pd.isna(v) for v in (close, ema9, ema21, sma50, sma200)):
            return _insufficient()

        above_9  = bool(close > ema9)
        above_21 = bool(close > ema21)

        c1 = bool(ema9  > ema21)
        c2 = bool(ema21 > sma50)
        c3 = bool(sma50 > sma200)
        alignment_count = int(c1) + int(c2) + int(c3)

        crossed = _detect_recent_cross(w, config.WEEKLY_CROSS_LOOKBACK_WEEKS)

        score = (
            (25.0 if above_9 else 0.0)
            + (15.0 if above_21 else 0.0)
            + (alignment_count / 3.0 * 40.0)
            + (20.0 if crossed else 0.0)
        )

        return {
            "weekly_setup_score": round(score, 2),
            "weekly_setup_above_9ema": above_9,
            "weekly_setup_above_21ema": above_21,
            "weekly_setup_alignment_count": alignment_count,
            "weekly_setup_9ema_crossed_200sma_recent": crossed,
        }


def _detect_recent_cross(w: pd.DataFrame, lookback: int) -> bool:
    """True if ema9 crossed above sma200 (from <= to >) anywhere in the last `lookback` rows."""
    window = w.iloc[-lookback:]
    if len(window) < 2:
        return False
    ema9 = window["ema9"].values
    sma200 = window["sma200"].values
    for i in range(1, len(window)):
        if pd.isna(ema9[i]) or pd.isna(sma200[i]) or pd.isna(ema9[i - 1]) or pd.isna(sma200[i - 1]):
            continue
        if ema9[i] > sma200[i] and ema9[i - 1] <= sma200[i - 1]:
            return True
    return False


def _insufficient() -> dict[str, Any]:
    return {
        "weekly_setup_score": 0.0,
        "weekly_setup_above_9ema": False,
        "weekly_setup_above_21ema": False,
        "weekly_setup_alignment_count": 0,
        "weekly_setup_9ema_crossed_200sma_recent": False,
    }

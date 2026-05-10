"""EMA9/EMA21/SMA50 compression scorer (refactored from v1/v2)."""
from typing import Any

import pandas as pd

import config
from scorers.base import Scorer


class CompressionScorer(Scorer):
    name = "compression"
    required_frames = ("daily",)

    def score(self, frames: dict[str, pd.DataFrame], regime: Any) -> dict[str, Any]:
        self.validate_frames(frames)
        d = frames["daily"]
        last = d.iloc[-1]
        ema9, ema21, sma50, close = last["ema9"], last["ema21"], last["sma50"], last["close"]

        if pd.isna(sma50) or pd.isna(ema9) or pd.isna(ema21):
            return {
                "compression_score": 0.0,
                "compression_pct": float("nan"),
                "compression_alignment": "INSUFFICIENT_DATA",
                "compression_close": float(close) if not pd.isna(close) else float("nan"),
                "compression_ema9": float("nan"),
                "compression_ema21": float("nan"),
                "compression_sma50": float("nan"),
                "compression_above_sma50": False,
            }

        spread_pct = (max(ema9, ema21, sma50) - min(ema9, ema21, sma50)) / close * 100.0
        score = max(0.0, 100.0 - (spread_pct / config.COMPRESSION_SCORE_MAX_SPREAD_PCT * 100.0))

        if ema9 > ema21 > sma50:
            alignment = "BULLISH"
        elif ema9 < ema21 < sma50:
            alignment = "BEARISH"
        else:
            alignment = "MIXED"

        return {
            "compression_score": round(float(score), 2),
            "compression_pct": round(float(spread_pct), 3),
            "compression_alignment": alignment,
            "compression_close": round(float(close), 2),
            "compression_ema9": round(float(ema9), 2),
            "compression_ema21": round(float(ema21), 2),
            "compression_sma50": round(float(sma50), 2),
            "compression_above_sma50": bool(close > sma50),
        }

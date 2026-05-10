"""Distance of price from the EMA9/EMA21 band — primary entry signal.

Spec:
    band_low  = min(ema9, ema21)
    band_high = max(ema9, ema21)
    band_mid  = (ema9 + ema21) / 2
    distance_pct = abs(close - band_mid) / close * 100
    is_inside_band = band_low <= close <= band_high
    is_flat = distance_pct < FLAT_THRESHOLD_PCT (1.5)

    Score:
        is_inside_band            -> 100  (highest precedence)
        elif is_flat              -> 75
        elif distance < 5.0 (FLAT_DECAY_LIMIT_PCT) -> linear decay 75 -> 0
                                                      across [1.5, 5.0]
        else                      -> 0

Required frames: daily.
"""
from typing import Any

import pandas as pd

import config
from scorers.base import Scorer


class FlatAgainstBandScorer(Scorer):
    name = "flat_against_band"
    required_frames = ("daily",)

    def score(self, frames: dict[str, pd.DataFrame], regime: Any) -> dict[str, Any]:
        self.validate_frames(frames)
        last = frames["daily"].iloc[-1]
        ema9, ema21, close = last["ema9"], last["ema21"], last["close"]

        if pd.isna(ema9) or pd.isna(ema21) or pd.isna(close) or close <= 0:
            return {
                "flat_against_band_score": 0.0,
                "flat_against_band_distance_pct": float("nan"),
                "flat_against_band_is_flat": False,
                "flat_against_band_is_inside_band": False,
                "flat_against_band_mid": float("nan"),
            }

        band_low  = float(min(ema9, ema21))
        band_high = float(max(ema9, ema21))
        band_mid  = (float(ema9) + float(ema21)) / 2.0
        distance_pct = abs(float(close) - band_mid) / float(close) * 100.0
        is_inside  = bool(band_low <= float(close) <= band_high)
        is_flat    = bool(distance_pct < config.FLAT_THRESHOLD_PCT)

        if is_inside:
            score = 100.0
        elif is_flat:
            score = 75.0
        elif distance_pct < config.FLAT_DECAY_LIMIT_PCT:
            # linear decay from 75 at FLAT_THRESHOLD_PCT to 0 at FLAT_DECAY_LIMIT_PCT
            span = config.FLAT_DECAY_LIMIT_PCT - config.FLAT_THRESHOLD_PCT
            score = 75.0 * (config.FLAT_DECAY_LIMIT_PCT - distance_pct) / span
        else:
            score = 0.0

        return {
            "flat_against_band_score": round(score, 2),
            "flat_against_band_distance_pct": round(distance_pct, 3),
            "flat_against_band_is_flat": is_flat,
            "flat_against_band_is_inside_band": is_inside,
            "flat_against_band_mid": round(band_mid, 2),
        }

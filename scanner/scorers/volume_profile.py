"""Recent volume relative to baseline.

Spec:
    vol_5d  = daily["volume"].iloc[-VOL_PROFILE_RECENT:].mean()    # last 5
    vol_50d = daily["volume"].iloc[-VOL_PROFILE_BASELINE:].mean()  # last 50
    vol_ratio = vol_5d / vol_50d  (or 0 if vol_50d is 0/NaN)

    Score buckets:
        ratio < 0.5   -> 0
        ratio < 1.0   -> 50
        ratio < 1.5   -> 75
        ratio >= 1.5  -> 100

    is_anomaly = vol_ratio > VOL_PROFILE_ANOMALY_RATIO (3.0)
        — flag for human review; does NOT alter the score.

Required frames: daily.
"""
from typing import Any

import pandas as pd

import config
from scorers.base import Scorer


class VolumeProfileScorer(Scorer):
    name = "volume_profile"
    required_frames = ("daily",)

    def score(self, frames: dict[str, pd.DataFrame], regime: Any) -> dict[str, Any]:
        self.validate_frames(frames)
        d = frames["daily"]

        if "volume" not in d.columns or len(d) < config.VOL_PROFILE_BASELINE:
            return {
                "volume_profile_score": 0.0,
                "volume_profile_ratio": 0.0,
                "volume_profile_is_anomaly": False,
                "volume_profile_label": "INSUFFICIENT_DATA",
            }

        vol_recent   = float(d["volume"].iloc[-config.VOL_PROFILE_RECENT:].mean())
        vol_baseline = float(d["volume"].iloc[-config.VOL_PROFILE_BASELINE:].mean())

        if not vol_baseline or pd.isna(vol_baseline):
            ratio = 0.0
        else:
            ratio = vol_recent / vol_baseline

        if ratio < 0.5:
            score = 0.0
        elif ratio < 1.0:
            score = 50.0
        elif ratio < 1.5:
            score = 75.0
        else:
            score = 100.0

        return {
            "volume_profile_score": score,
            "volume_profile_ratio": round(ratio, 3),
            "volume_profile_is_anomaly": bool(ratio > config.VOL_PROFILE_ANOMALY_RATIO),
            "volume_profile_label": _label(ratio),
        }


def _label(ratio: float) -> str:
    if ratio < 0.5:  return "DRY"
    if ratio < 1.0:  return "BELOW_AVG"
    if ratio < 1.5:  return "ABOVE_AVG"
    return "EXPANDING"

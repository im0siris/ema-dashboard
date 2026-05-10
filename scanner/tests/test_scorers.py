"""Synthetic OHLCV fixture tests for scorers + universe filter."""
import numpy as np
import pandas as pd
import pytest

import indicators
import universe as u
from scorers.alignment import AlignmentScorer
from scorers.base_break import BaseBreakScorer
from scorers.compression import CompressionScorer
from scorers.flat_against_band import FlatAgainstBandScorer
from scorers.squeeze import SqueezeScorer
from scorers.volume_profile import VolumeProfileScorer
from scorers.weekly_setup import WeeklySetupScorer


def make_ohlcv(days: int = 120, base: float = 100.0,
               drift: float = 0.0, noise: float = 0.5, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(end="2026-04-24", periods=days, freq="B")
    n = len(dates)
    closes = base + np.cumsum(rng.normal(drift, noise, n))
    closes = np.maximum(closes, 0.01)
    return pd.DataFrame({
        "open":   closes - rng.normal(0, 0.1, n),
        "high":   closes + np.abs(rng.normal(0.5, 0.2, n)),
        "low":    closes - np.abs(rng.normal(0.5, 0.2, n)),
        "close":  closes,
        "volume": rng.integers(1_000_000, 5_000_000, n),
    }, index=dates)


# ---------- indicators ----------

def test_indicators_add_mas_columns():
    df = indicators.add_mas(make_ohlcv())
    for col in ["ema9", "ema21", "sma50", "sma100", "sma200",
                "vol_avg_5", "vol_avg_20", "vol_avg_50"]:
        assert col in df.columns, f"missing column: {col}"


# ---------- compression scorer ----------

def test_compression_returns_required_keys():
    df = indicators.add_mas(make_ohlcv())
    r = CompressionScorer().score({"daily": df}, regime=None)
    for k in ["compression_score", "compression_pct", "compression_alignment",
              "compression_above_sma50", "compression_close",
              "compression_ema9", "compression_ema21", "compression_sma50"]:
        assert k in r, f"missing {k}"


def test_compression_flat_series_high_score():
    df = indicators.add_mas(make_ohlcv(drift=0.0, noise=0.01, base=50.0))
    r = CompressionScorer().score({"daily": df}, regime=None)
    assert r["compression_pct"] < 1.0
    assert r["compression_score"] > 90


def test_compression_alignment_bullish_in_uptrend():
    df = indicators.add_mas(make_ohlcv(drift=0.5, noise=0.1, base=50.0))
    r = CompressionScorer().score({"daily": df}, regime=None)
    assert r["compression_alignment"] == "BULLISH"
    assert r["compression_above_sma50"] is True


def test_compression_alignment_bearish_in_downtrend():
    df = indicators.add_mas(make_ohlcv(drift=-0.5, noise=0.1, base=200.0))
    r = CompressionScorer().score({"daily": df}, regime=None)
    assert r["compression_alignment"] == "BEARISH"
    assert r["compression_above_sma50"] is False


def test_compression_insufficient_data_handles_gracefully():
    df = indicators.add_mas(make_ohlcv(days=30))
    r = CompressionScorer().score({"daily": df}, regime=None)
    assert r["compression_alignment"] == "INSUFFICIENT_DATA"
    assert r["compression_score"] == 0.0


def test_compression_score_decays_with_spread():
    tight = indicators.add_mas(make_ohlcv(drift=0.0, noise=0.01))
    wide  = indicators.add_mas(make_ohlcv(drift=0.0, noise=2.0, seed=99))
    rt = CompressionScorer().score({"daily": tight}, regime=None)
    rw = CompressionScorer().score({"daily": wide}, regime=None)
    assert rt["compression_score"] > rw["compression_score"]


def test_validate_frames_raises_when_required_missing():
    s = CompressionScorer()
    with pytest.raises(ValueError, match="requires frames"):
        s.score({"weekly": pd.DataFrame()}, regime=None)


# ---------- alignment scorer ----------

def test_alignment_returns_required_keys():
    df = indicators.add_mas(make_ohlcv(days=300, drift=0.5, noise=0.1))
    r = AlignmentScorer().score({"daily": df}, regime=None)
    for k in ["alignment_score", "alignment_label", "alignment_count",
              "alignment_ema9_gt_ema21", "alignment_ema21_gt_sma50",
              "alignment_sma50_gt_sma200"]:
        assert k in r, f"missing {k}"


def test_alignment_full_bull_in_strong_uptrend():
    df = indicators.add_mas(make_ohlcv(days=300, drift=0.5, noise=0.1, base=50.0))
    r = AlignmentScorer().score({"daily": df}, regime=None)
    assert r["alignment_label"] == "FULL_BULL"
    assert r["alignment_count"] == 3
    assert r["alignment_score"] == 100.0


def test_alignment_bear_in_strong_downtrend():
    df = indicators.add_mas(make_ohlcv(days=300, drift=-0.5, noise=0.1, base=300.0))
    r = AlignmentScorer().score({"daily": df}, regime=None)
    assert r["alignment_label"] == "BEAR"
    assert r["alignment_count"] == 0
    assert r["alignment_score"] == 0.0


def test_alignment_insufficient_data_short_series():
    """Period < 200 trading days -> sma200 NaN -> INSUFFICIENT_DATA."""
    df = indicators.add_mas(make_ohlcv(days=120))
    r = AlignmentScorer().score({"daily": df}, regime=None)
    assert r["alignment_label"] == "INSUFFICIENT_DATA"
    assert r["alignment_score"] == 0.0


def test_alignment_score_buckets():
    """Score must be one of {0, 33.33, 66.67, 100}."""
    df = indicators.add_mas(make_ohlcv(days=300, drift=0.5, noise=0.1, base=50.0))
    r = AlignmentScorer().score({"daily": df}, regime=None)
    assert r["alignment_score"] in (0.0, 33.33, 66.67, 100.0)


# ---------- volume_profile scorer ----------

def test_volume_profile_required_keys():
    df = indicators.add_mas(make_ohlcv())
    r = VolumeProfileScorer().score({"daily": df}, regime=None)
    for k in ["volume_profile_score", "volume_profile_ratio",
              "volume_profile_is_anomaly", "volume_profile_label"]:
        assert k in r, f"missing {k}"


def test_volume_profile_high_recent_volume_max_score():
    df = make_ohlcv(days=120)
    df.loc[df.index[:-5],  "volume"] = 1_000_000
    df.loc[df.index[-5:],  "volume"] = 2_000_000
    # 5d mean = 2M; 50d mean = (45*1 + 5*2)/50 = 1.1M; ratio = 1.82
    df = indicators.add_mas(df)
    r = VolumeProfileScorer().score({"daily": df}, regime=None)
    assert r["volume_profile_score"] == 100.0
    assert r["volume_profile_ratio"] > 1.5
    assert r["volume_profile_is_anomaly"] is False  # 1.82 < 3.0
    assert r["volume_profile_label"] == "EXPANDING"


def test_volume_profile_low_volume_zero_score():
    df = make_ohlcv(days=120)
    df.loc[df.index[:-5],  "volume"] = 1_000_000
    df.loc[df.index[-5:],  "volume"] = 100_000
    # 5d mean = 100k; 50d mean = (45M + 0.5M)/50 = 0.91M; ratio = 0.110
    df = indicators.add_mas(df)
    r = VolumeProfileScorer().score({"daily": df}, regime=None)
    assert r["volume_profile_score"] == 0.0
    assert r["volume_profile_ratio"] < 0.5
    assert r["volume_profile_label"] == "DRY"


def test_volume_profile_anomaly_flag_set_above_3x():
    df = make_ohlcv(days=120)
    df.loc[df.index[:-5],  "volume"] = 1_000_000
    df.loc[df.index[-5:],  "volume"] = 10_000_000
    # 5d = 10M; 50d = (45 + 50)/50 = 1.9M; ratio = 5.26
    df = indicators.add_mas(df)
    r = VolumeProfileScorer().score({"daily": df}, regime=None)
    assert r["volume_profile_is_anomaly"] is True
    assert r["volume_profile_score"] == 100.0


def test_volume_profile_zero_baseline_no_crash():
    df = make_ohlcv(days=120)
    df["volume"] = 0
    df = indicators.add_mas(df)
    r = VolumeProfileScorer().score({"daily": df}, regime=None)
    assert r["volume_profile_score"] == 0.0
    assert r["volume_profile_ratio"] == 0.0


def test_volume_profile_insufficient_data():
    df = indicators.add_mas(make_ohlcv(days=30))
    r = VolumeProfileScorer().score({"daily": df}, regime=None)
    assert r["volume_profile_label"] == "INSUFFICIENT_DATA"
    assert r["volume_profile_score"] == 0.0


# ---------- flat_against_band scorer ----------

def test_flat_against_band_required_keys():
    df = indicators.add_mas(make_ohlcv())
    r = FlatAgainstBandScorer().score({"daily": df}, regime=None)
    for k in ["flat_against_band_score", "flat_against_band_distance_pct",
              "flat_against_band_is_flat", "flat_against_band_is_inside_band",
              "flat_against_band_mid"]:
        assert k in r, f"missing {k}"


def test_flat_against_band_flat_series_high_score():
    """Flat noise series → close hovers near band → max score."""
    df = indicators.add_mas(make_ohlcv(days=120, drift=0.0, noise=0.05))
    r = FlatAgainstBandScorer().score({"daily": df}, regime=None)
    assert r["flat_against_band_score"] == 100.0
    assert r["flat_against_band_is_inside_band"] is True


def test_flat_against_band_strong_uptrend_zero_score():
    """Strong uptrend pulls close well past 5% above band -> score 0."""
    df = indicators.add_mas(make_ohlcv(days=120, drift=4.0, noise=0.1, base=50.0))
    r = FlatAgainstBandScorer().score({"daily": df}, regime=None)
    assert r["flat_against_band_is_inside_band"] is False
    assert r["flat_against_band_distance_pct"] > 5.0
    assert r["flat_against_band_score"] == 0.0


def test_flat_against_band_decay_inside_5pct():
    """Mid-distance (1.5%-5% from band_mid) -> score between 0 and 75 exclusive."""
    df = indicators.add_mas(make_ohlcv(days=120, drift=0.4, noise=0.1, base=50.0, seed=7))
    r = FlatAgainstBandScorer().score({"daily": df}, regime=None)
    if not r["flat_against_band_is_inside_band"] and 1.5 <= r["flat_against_band_distance_pct"] < 5.0:
        assert 0.0 < r["flat_against_band_score"] < 75.0


# ---------- squeeze scorer ----------

def _make_augmented_daily(n: int, *, close, ema9, ema21, sma50, sma100, sma200, volume=1_000_000):
    """Build a daily-augmented DataFrame with explicit MA columns. Each MA arg is
    either a scalar (broadcast to length n) or a list of length n."""
    def _arr(v): return [v] * n if not hasattr(v, "__len__") else list(v)
    dates = pd.date_range(end="2026-04-24", periods=n, freq="B")
    return pd.DataFrame({
        "open":  _arr(close), "high": _arr(close), "low": _arr(close),
        "close": _arr(close), "volume": _arr(volume),
        "ema9":  _arr(ema9),  "ema21": _arr(ema21),
        "sma50": _arr(sma50), "sma100": _arr(sma100), "sma200": _arr(sma200),
        "vol_avg_5":  _arr(volume), "vol_avg_20": _arr(volume), "vol_avg_50": _arr(volume),
    }, index=dates)


def test_squeeze_required_keys():
    df = _make_augmented_daily(50, close=100, ema9=99, ema21=98,
                               sma50=97, sma100=102, sma200=105)
    r = SqueezeScorer().score({"daily": df}, regime=None)
    for k in ["squeeze_score", "squeeze_active", "squeeze_overhead_ma",
              "squeeze_overhead_distance_pct", "squeeze_small_mas_below",
              "squeeze_emas_rising", "squeeze_ema9_slope_5d", "squeeze_ema21_slope_5d"]:
        assert k in r, f"missing {k}"


def test_squeeze_active_with_sma100_overhead():
    n = 50
    df = _make_augmented_daily(
        n,
        close=100,
        ema9=list(np.linspace(95, 99, n)),    # rising, just below close
        ema21=list(np.linspace(94, 98, n)),   # rising, just below close
        sma50=97,
        sma100=102,                            # 2% overhead
        sma200=105,
    )
    r = SqueezeScorer().score({"daily": df}, regime=None)
    assert r["squeeze_active"] is True
    assert r["squeeze_overhead_ma"] == "SMA100"
    assert r["squeeze_overhead_distance_pct"] == 2.0
    assert r["squeeze_score"] == 100.0


def test_squeeze_inactive_when_above_all_mas():
    df = _make_augmented_daily(50, close=110, ema9=109, ema21=108,
                               sma50=105, sma100=100, sma200=95)
    r = SqueezeScorer().score({"daily": df}, regime=None)
    assert r["squeeze_active"] is False
    assert r["squeeze_overhead_ma"] is None
    assert r["squeeze_score"] == 0.0


def test_squeeze_inactive_when_emas_flat():
    """Constant EMAs -> slope 0 -> not rising -> inactive."""
    df = _make_augmented_daily(50, close=100, ema9=99, ema21=98,
                               sma50=97, sma100=102, sma200=105)
    r = SqueezeScorer().score({"daily": df}, regime=None)
    assert r["squeeze_emas_rising"] is False
    assert r["squeeze_active"] is False


def test_squeeze_overhead_picks_sma200_when_close_between():
    n = 50
    df = _make_augmented_daily(
        n,
        close=103,
        ema9=list(np.linspace(98, 102, n)),
        ema21=list(np.linspace(97, 101, n)),
        sma50=99,
        sma100=100,        # close > sma100
        sma200=106,        # close < sma200 -> overhead
    )
    r = SqueezeScorer().score({"daily": df}, regime=None)
    assert r["squeeze_overhead_ma"] == "SMA200"
    assert r["squeeze_active"] is True


def test_squeeze_insufficient_rows():
    df = _make_augmented_daily(3, close=100, ema9=99, ema21=98,
                               sma50=97, sma100=102, sma200=105)
    r = SqueezeScorer().score({"daily": df}, regime=None)
    assert r["squeeze_active"] is False
    assert r["squeeze_score"] == 0.0


# ---------- weekly_setup scorer ----------

def _make_augmented_weekly(n: int, *, close, ema9, ema21, sma50, sma200):
    def _arr(v): return [v] * n if not hasattr(v, "__len__") else list(v)
    dates = pd.date_range(end="2026-04-24", periods=n, freq="W-FRI")
    return pd.DataFrame({
        "close": _arr(close),
        "ema9":  _arr(ema9),  "ema21": _arr(ema21),
        "sma50": _arr(sma50), "sma200": _arr(sma200),
    }, index=dates)


def test_weekly_setup_required_keys():
    df = _make_augmented_weekly(20, close=100, ema9=98, ema21=96, sma50=94, sma200=90)
    r = WeeklySetupScorer().score({"weekly": df}, regime=None)
    for k in ["weekly_setup_score", "weekly_setup_above_9ema", "weekly_setup_above_21ema",
              "weekly_setup_alignment_count", "weekly_setup_9ema_crossed_200sma_recent"]:
        assert k in r, f"missing {k}"


def test_weekly_setup_max_score_with_recent_cross():
    """Above 9EMA + above 21EMA + full alignment + recent cross -> 100.

    Cross must occur within WEEKLY_CROSS_LOOKBACK_WEEKS (4) so it lands
    inside `weekly_df.iloc[-4:]` and produces a transition we can detect.
    """
    n = 10
    # ema9 stays below sma200 until index -3, then breaks above by index -2
    ema9   = [85, 85, 85, 85, 85, 85, 85, 91, 96, 102]
    sma200 = [90] * n
    df = _make_augmented_weekly(n, close=110, ema9=ema9, ema21=99, sma50=95, sma200=sma200)
    r = WeeklySetupScorer().score({"weekly": df}, regime=None)
    assert r["weekly_setup_above_9ema"] is True
    assert r["weekly_setup_above_21ema"] is True
    assert r["weekly_setup_alignment_count"] == 3
    assert r["weekly_setup_9ema_crossed_200sma_recent"] is True
    assert r["weekly_setup_score"] == 100.0


def test_weekly_setup_zero_score_in_bear_setup():
    """Below all MAs, bearish stack, no cross."""
    df = _make_augmented_weekly(20, close=80, ema9=85, ema21=90, sma50=95, sma200=100)
    r = WeeklySetupScorer().score({"weekly": df}, regime=None)
    assert r["weekly_setup_above_9ema"] is False
    assert r["weekly_setup_above_21ema"] is False
    assert r["weekly_setup_alignment_count"] == 0
    assert r["weekly_setup_9ema_crossed_200sma_recent"] is False
    assert r["weekly_setup_score"] == 0.0


def test_weekly_setup_cross_not_detected_when_already_above():
    """ema9 already above sma200 throughout -> no cross."""
    df = _make_augmented_weekly(20, close=110, ema9=105, ema21=100,
                                sma50=95, sma200=90)
    r = WeeklySetupScorer().score({"weekly": df}, regime=None)
    assert r["weekly_setup_9ema_crossed_200sma_recent"] is False
    # Still gets above_9 (25) + above_21 (15) + alignment 3/3*40 (40) = 80
    assert r["weekly_setup_score"] == 80.0


def test_weekly_setup_partial_alignment_score():
    """Above ema9 + above ema21 but only 2/3 alignment, no cross."""
    # ema9>ema21 ✓, ema21>sma50 ✓, sma50>sma200 ✗
    df = _make_augmented_weekly(20, close=110, ema9=105, ema21=100,
                                sma50=95, sma200=98)
    r = WeeklySetupScorer().score({"weekly": df}, regime=None)
    assert r["weekly_setup_alignment_count"] == 2
    # 25 + 15 + (2/3 * 40) = 25 + 15 + 26.67 = 66.67
    assert abs(r["weekly_setup_score"] - 66.67) < 0.1


# ---------- base_break scorer ----------

def _make_monthly(close_array, volume_array=None):
    n = len(close_array)
    if volume_array is None:
        volume_array = [1_000_000] * n
    dates = pd.date_range(end="2026-04-30", periods=n, freq="ME")
    return pd.DataFrame({
        "open": close_array, "high": close_array, "low": close_array,
        "close": close_array, "volume": volume_array,
    }, index=dates)


def test_base_break_required_keys():
    df = _make_monthly([100] * 60)
    r = BaseBreakScorer().score({"monthly": df}, regime=None)
    for k in ["base_break_score", "base_break_active", "base_break_years_of_base",
              "base_break_breakout_volume", "base_break_historical_max",
              "base_break_current_close"]:
        assert k in r, f"missing {k}"


def test_base_break_insufficient_history():
    df = _make_monthly([100] * 30)
    r = BaseBreakScorer().score({"monthly": df}, regime=None)
    assert r["base_break_active"] is False
    assert r["base_break_score"] == 0.0
    assert r["base_break_years_of_base"] == 0.0


def test_base_break_active_when_breaking_5y_high():
    closes = [80 + (i % 21) for i in range(59)] + [110]   # max in prior = 100, current = 110
    df = _make_monthly(closes)
    r = BaseBreakScorer().score({"monthly": df}, regime=None)
    assert r["base_break_active"] is True
    assert r["base_break_historical_max"] == 100.0
    assert r["base_break_current_close"] == 110.0
    assert r["base_break_score"] == 100.0


def test_base_break_inactive_inside_range():
    closes = [80 + (i % 21) for i in range(59)] + [85]   # current within prior range
    df = _make_monthly(closes)
    r = BaseBreakScorer().score({"monthly": df}, regime=None)
    assert r["base_break_active"] is False
    assert r["base_break_score"] == 0.0


def test_base_break_years_of_base_two_years_back():
    """Last high at index 35 (24 months before current=index 59) -> 2.0 years."""
    closes = [80] * 35 + [100] + [90] * 23 + [110]   # len = 60
    df = _make_monthly(closes)
    r = BaseBreakScorer().score({"monthly": df}, regime=None)
    assert r["base_break_active"] is True
    assert r["base_break_years_of_base"] == 2.0


def test_base_break_breakout_volume_flag():
    """Final-month volume > 1.5x prior 12-month mean -> flag set."""
    closes = [80 + (i % 21) for i in range(59)] + [110]
    volumes = [1_000_000] * 59 + [3_000_000]    # 3x baseline
    df = _make_monthly(closes, volumes)
    r = BaseBreakScorer().score({"monthly": df}, regime=None)
    assert r["base_break_breakout_volume"] is True
    assert r["base_break_score"] == 100.0     # capped (100 base + 20 bonus -> min 100)


def test_base_break_no_volume_confirmation():
    closes = [80 + (i % 21) for i in range(59)] + [110]
    volumes = [1_000_000] * 60
    df = _make_monthly(closes, volumes)
    r = BaseBreakScorer().score({"monthly": df}, regime=None)
    assert r["base_break_breakout_volume"] is False
    assert r["base_break_score"] == 100.0     # break only, no volume bonus (capped same)


# ---------- universe filter ----------

def test_universe_keeps_common_equity():
    keepers = [
        {"symbol": "AAPL", "name": "Apple Inc. Common Stock"},
        {"symbol": "STRS", "name": "Stratus Properties Inc. Common Stock"},
        {"symbol": "FINW", "name": "FinWise Bancorp Common Stock"},
        {"symbol": "BOC",  "name": "Boston Omaha Corporation Class A Common Stock"},
    ]
    for s in keepers:
        assert u.is_common_equity(s), f"should keep: {s}"


def test_universe_drops_typical_noise():
    droppers = [
        {"symbol": "FCRX",  "name": "Crescent Capital BDC, Inc. 5.00% Notes due 2026"},
        {"symbol": "MMT",   "name": "MFS Multimarket Income Trust Common Stock"},
        {"symbol": "HCMA",  "name": "HCM III Acquisition Corp. Class A Ordinary"},
        {"symbol": "CHSCP", "name": "CHS Inc. 8% Cumulative Redeemable Preferred"},
        {"symbol": "FCNCP", "name": "First Citizens BancShares Depositary Shares"},
        {"symbol": "FOOAW", "name": "Foo Acquisition Corp. Warrant"},
        {"symbol": "VPV",   "name": "Invesco Pennsylvania Value Municipal Income Trust"},
        # Added 2026-05: closed-end funds and mREITs that slipped through earlier
        {"symbol": "SOR",   "name": "Source Capital, Inc. Cmn Shs of BI"},
        {"symbol": "LEO",   "name": "BNY Mellon Strategic Municipals, Inc. Common Stock"},
        {"symbol": "IVR",   "name": "INVESCO MORTGAGE CAPITAL INC Common Stock"},
    ]
    for s in droppers:
        assert not u.is_common_equity(s), f"should drop: {s}"


def test_universe_market_cap_filter_inclusive():
    stocks = [
        {"symbol": "A", "name": "A Co",   "marketCap": "199000000"},   # below
        {"symbol": "B", "name": "B Co",   "marketCap": "200000000"},   # at min
        {"symbol": "C", "name": "C Co",   "marketCap": "500000000"},   # in
        {"symbol": "D", "name": "D Co",   "marketCap": "1000000000"},  # at max
        {"symbol": "E", "name": "E Co",   "marketCap": "1100000000"},  # above
    ]
    out = u.filter_by_market_cap(stocks, 200, 1000)
    assert {s["symbol"] for s in out} == {"B", "C", "D"}

"""Vectorized indicator math. Augments OHLCV DataFrames with MA / volume columns.

Convention: input DataFrames must have lowercase columns: open, high, low, close, volume.
data.py normalizes to lowercase before calling this module.
"""
import pandas as pd

MA_COLUMNS = (
    "ema9", "ema21",
    "sma50", "sma100", "sma200",
    "vol_avg_5", "vol_avg_20", "vol_avg_50",
)


def add_mas(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a copy of df with MA + volume-average columns appended.

    Tolerates short series — rolling SMAs return NaN until enough data accumulates.
    Scorers must check for NaN on the values they actually consume.
    """
    df = df.copy()
    close = df["close"]
    df["ema9"]   = close.ewm(span=9,  adjust=False).mean()
    df["ema21"]  = close.ewm(span=21, adjust=False).mean()
    df["sma50"]  = close.rolling(50).mean()
    df["sma100"] = close.rolling(100).mean()
    df["sma200"] = close.rolling(200).mean()
    if "volume" in df.columns:
        df["vol_avg_5"]  = df["volume"].rolling(5).mean()
        df["vol_avg_20"] = df["volume"].rolling(20).mean()
        df["vol_avg_50"] = df["volume"].rolling(50).mean()
    return df

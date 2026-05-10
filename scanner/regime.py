"""SPY/QQQ market regime gate.

Two-factor regime: each of SPY and QQQ contributes "above 50DMA?" and "above 200SMA?".
Labels:
    RISK_ON_FULL  — both above 50DMA AND both above 200SMA
    RISK_ON_SHORT — both above 50DMA, but at least one below 200SMA
    MIXED         — partial (50+200 combined count >= 2 but not both above 50)
    RISK_OFF      — fewer than 2 of the four signals are positive
"""
from dataclasses import dataclass
from typing import Literal

import data

RegimeLabel = Literal["RISK_ON_FULL", "RISK_ON_SHORT", "MIXED", "RISK_OFF"]


@dataclass
class RegimeState:
    label: RegimeLabel
    spy_above_50dma: bool
    spy_above_200sma: bool
    qqq_above_50dma: bool
    qqq_above_200sma: bool


def compute_regime(use_cache: bool = True) -> RegimeState:
    frames = data.download_with_cache(["SPY", "QQQ"], use_cache=use_cache, period="1y")

    if "SPY" not in frames or "QQQ" not in frames:
        raise RuntimeError("Could not fetch SPY/QQQ for regime gate")

    spy = frames["SPY"]["daily"].iloc[-1]
    qqq = frames["QQQ"]["daily"].iloc[-1]

    spy_50  = bool(spy["close"] > spy["sma50"])
    spy_200 = bool(spy["close"] > spy["sma200"])
    qqq_50  = bool(qqq["close"] > qqq["sma50"])
    qqq_200 = bool(qqq["close"] > qqq["sma200"])

    count_50  = int(spy_50)  + int(qqq_50)
    count_200 = int(spy_200) + int(qqq_200)

    if count_50 == 2 and count_200 == 2:
        label: RegimeLabel = "RISK_ON_FULL"
    elif count_50 == 2:
        label = "RISK_ON_SHORT"
    elif count_50 + count_200 >= 2:
        label = "MIXED"
    else:
        label = "RISK_OFF"

    return RegimeState(
        label=label,
        spy_above_50dma=spy_50,
        spy_above_200sma=spy_200,
        qqq_above_50dma=qqq_50,
        qqq_above_200sma=qqq_200,
    )


def format_regime(state: RegimeState) -> str:
    return "\n".join([
        "=" * 60,
        f"  MARKET REGIME: {state.label}",
        f"  SPY: above 50DMA={state.spy_above_50dma}  above 200SMA={state.spy_above_200sma}",
        f"  QQQ: above 50DMA={state.qqq_above_50dma}  above 200SMA={state.qqq_above_200sma}",
        "=" * 60,
    ])

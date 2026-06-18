"""
Market regime classification using Fear & Greed Index + BTC Dominance.

Regime matrix:
  RISK_ON_ALT   : F&G >= 55 and BTC dom <= 52  → alt season, momentum longs
  RISK_ON_BTC   : F&G >= 55 and BTC dom >  52  → BTC season, prefer BTC/majors
  NEUTRAL       : 35 < F&G < 55               → no strong edge, reduce size
  RISK_OFF      : F&G <= 35 and BTC dom >  52  → fear + BTC flight, defensive
  EXTREME_FEAR  : F&G <= 20                   → contrarian accumulation signal
  EXTREME_GREED : F&G >= 80                   → contrarian reduction signal
"""

from dataclasses import dataclass


@dataclass
class Regime:
    label: str
    fg_value: int
    fg_classification: str
    btc_dominance: float
    signal_bias: str      # LONG / SHORT / NEUTRAL / CONTRARIAN_LONG / CONTRARIAN_SHORT
    size_multiplier: float  # 0.0–1.0, scales position size
    description: str


def classify(fg_value: int, btc_dominance: float) -> Regime:
    if fg_value <= 20:
        return Regime(
            label="EXTREME_FEAR",
            fg_value=fg_value,
            fg_classification="Extreme Fear",
            btc_dominance=btc_dominance,
            signal_bias="CONTRARIAN_LONG",
            size_multiplier=0.5,
            description="Extreme fear — contrarian accumulation. Small size, scale in over days.",
        )
    if fg_value >= 80:
        return Regime(
            label="EXTREME_GREED",
            fg_value=fg_value,
            fg_classification="Extreme Greed",
            btc_dominance=btc_dominance,
            signal_bias="CONTRARIAN_SHORT",
            size_multiplier=0.3,
            description="Extreme greed — trim longs, avoid chasing. Market likely overextended.",
        )
    if fg_value >= 55 and btc_dominance <= 52:
        return Regime(
            label="RISK_ON_ALT",
            fg_value=fg_value,
            fg_classification="Greed",
            btc_dominance=btc_dominance,
            signal_bias="LONG",
            size_multiplier=1.0,
            description="Alt season in progress. Full size on high-momentum BEP-20 tokens.",
        )
    if fg_value >= 55 and btc_dominance > 52:
        return Regime(
            label="RISK_ON_BTC",
            fg_value=fg_value,
            fg_classification="Greed",
            btc_dominance=btc_dominance,
            signal_bias="LONG",
            size_multiplier=0.7,
            description="Greed but BTC-dominant. Prefer BTC/majors over small caps.",
        )
    if fg_value <= 35 and btc_dominance > 52:
        return Regime(
            label="RISK_OFF",
            fg_value=fg_value,
            fg_classification="Fear",
            btc_dominance=btc_dominance,
            signal_bias="NEUTRAL",
            size_multiplier=0.2,
            description="Fear + BTC dominance rising. Defensive — hold stables or BTC only.",
        )
    return Regime(
        label="NEUTRAL",
        fg_value=fg_value,
        fg_classification="Neutral",
        btc_dominance=btc_dominance,
        signal_bias="NEUTRAL",
        size_multiplier=0.5,
        description="No clear regime. Reduce size and wait for confirmation.",
    )

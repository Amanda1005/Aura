"""
CMC Skill: Regime-Momentum Strategy Signal

Callable by any LLM agent via MCP or directly.
Returns a structured strategy spec with entry/exit rules and current signals.

Architecture:
  1. Rule-based Regime  → structural signal (direction + base size)
  2. XGBoost Confidence → position-sizing calibrator (adjusts base size)
  Final position size   = regime.size_multiplier × confidence_multiplier
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone

from skill.data.cmc_client import (
    get_fear_greed_latest,
    get_global_metrics,
    get_listings,
)
from skill.signals.regime import classify, Regime
from skill.signals.momentum import score_tokens
from ml.predictor import predict_confidence


@dataclass
class StrategySpec:
    generated_at: str
    regime: dict
    ml_signal: dict
    effective_size_pct: int
    top_long_candidates: list[dict]
    top_short_candidates: list[dict]
    entry_rules: list[str]
    exit_rules: list[str]
    risk_rules: list[str]
    raw_signals: dict


def run(top_n: int = 5) -> StrategySpec:
    """
    Main Skill entry point.
    Returns a StrategySpec with current regime, ML confidence, ranked tokens, and strategy rules.
    """
    fg = get_fear_greed_latest()
    metrics = get_global_metrics()
    listings = get_listings(limit=200)

    fg_value = int(fg["value"])
    btc_dom  = metrics["btc_dominance"]
    total_mcap = metrics["quote"]["USD"]["total_market_cap"]

    regime: Regime = classify(fg_value, btc_dom)
    momentum_df = score_tokens(listings)

    # BTC price features for ML (from listings)
    btc_data = next((t for t in listings if t["symbol"] == "BTC"), None)
    btc_ret_1d = btc_data["quote"]["USD"]["percent_change_24h"] / 100 if btc_data else 0.0
    btc_ret_7d = btc_data["quote"]["USD"]["percent_change_7d"]  / 100 if btc_data else 0.0

    ml_features = {
        "fg":             fg_value,
        "fg_change_1d":   0.0,   # live: no previous day cached, default 0
        "fg_change_7d":   0.0,
        "fg_ma_7d":       float(fg_value),
        "fg_ma_14d":      float(fg_value),
        "fg_above_ma7":   1,
        "regime_int":     regime.label in ["EXTREME_FEAR", "RISK_OFF", "NEUTRAL", "RISK_ON_BTC", "RISK_ON_ALT", "EXTREME_GREED"],
        "btc_ret_1d":     btc_ret_1d,
        "btc_ret_7d":     btc_ret_7d,
        "btc_vol_7d":     abs(btc_ret_1d),   # single-day proxy
        "day_of_week":    datetime.now(timezone.utc).weekday(),
    }
    # regime_int as ordinal
    regime_map = {"EXTREME_FEAR": 0, "RISK_OFF": 1, "NEUTRAL": 2,
                  "RISK_ON_BTC": 3, "RISK_ON_ALT": 3, "EXTREME_GREED": 4}
    ml_features["regime_int"] = regime_map.get(regime.label, 2)

    ml_signal = predict_confidence(ml_features)

    # Final effective size = regime base × ML multiplier
    effective_size = regime.size_multiplier * ml_signal["confidence_multiplier"]
    effective_size_pct = int(round(effective_size * 100))

    longs, shorts = [], []
    if not momentum_df.empty:
        longs  = momentum_df.head(top_n)[["symbol", "price", "pct_24h", "pct_7d", "momentum_score"]].to_dict("records")
        shorts = momentum_df.tail(top_n)[["symbol", "price", "pct_24h", "pct_7d", "momentum_score"]].to_dict("records")

    entry_rules, exit_rules, risk_rules = _build_rules(regime, longs, effective_size_pct)

    return StrategySpec(
        generated_at=datetime.now(timezone.utc).isoformat(),
        regime=asdict(regime),
        ml_signal=ml_signal,
        effective_size_pct=effective_size_pct,
        top_long_candidates=longs,
        top_short_candidates=shorts,
        entry_rules=entry_rules,
        exit_rules=exit_rules,
        risk_rules=risk_rules,
        raw_signals={
            "fear_greed_value": fg_value,
            "fear_greed_classification": fg["value_classification"],
            "btc_dominance_pct": round(btc_dom, 2),
            "total_market_cap_usd": round(total_mcap, 0),
        },
    )


def _build_rules(regime: Regime, longs: list[dict], effective_size_pct: int = 50) -> tuple[list, list, list]:
    symbols = [t["symbol"] for t in longs[:3]] if longs else ["N/A"]

    if regime.signal_bias == "LONG":
        entry = [
            f"Enter LONG on {', '.join(symbols)} when momentum_score > 0.5.",
            "Confirm with 1h close above 20-period EMA before entry.",
            f"Scale position to {effective_size_pct}% of max allocation (regime base × ML confidence).",
        ]
        exit_r = [
            "Exit when momentum_score drops below 0 for 2 consecutive 4h candles.",
            "Hard stop: -8% from entry price.",
            "Take partial profit (+15%) at first target; trail remainder with -5% stop.",
        ]
    elif regime.signal_bias == "CONTRARIAN_LONG":
        entry = [
            "Enter LONG in tranches: 25% now, 25% at -5%, 25% at -10%, 25% at -15%.",
            f"Focus on large-cap eligible tokens only: {', '.join(symbols[:2])}.",
            "Require F&G < 20 for at least 3 consecutive days before full entry.",
        ]
        exit_r = [
            "Exit 50% when F&G crosses back above 30.",
            "Exit remaining 50% when F&G crosses above 50.",
            "Hard stop: -15% on full position.",
        ]
    elif regime.signal_bias == "CONTRARIAN_SHORT":
        entry = [
            "Trim existing longs by 50% immediately.",
            "Do NOT open new longs until F&G drops below 70.",
            "Optional: small short on weakest momentum tokens if conviction high.",
        ]
        exit_r = [
            "Cover shorts when F&G drops below 65.",
            "Resume longs only after F&G resets below 60.",
        ]
    else:  # NEUTRAL / RISK_OFF
        entry = [
            "No new positions in NEUTRAL/RISK_OFF regime.",
            "Hold stablecoins or BTC only.",
            "Re-evaluate when F&G moves outside 35–55 range.",
        ]
        exit_r = [
            "Close any open altcoin positions on next 4h close.",
            "Keep BTC position if held; tighten stop to -5%.",
        ]

    risk = [
        f"Max position size: {effective_size_pct}% of portfolio per token.",
        "Max total exposure: 3 tokens simultaneously.",
        "Daily loss limit: -5% of total portfolio → stop trading for the day.",
        "Never trade tokens not on the BEP-20 eligible list.",
    ]

    return entry, exit_r, risk

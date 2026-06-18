"""
30-day backtest using CMC historical Fear & Greed + yfinance prices.

Strategy:
  - Regime classified daily from F&G value
  - Token selection: top N by 7-day rolling momentum
  - Equal-weight portfolio, rebalanced daily
  - Benchmark: BTC buy-and-hold
"""

import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

from skill.data.cmc_client import get_fear_greed_historical
from skill.signals.regime import classify

# Eligible tokens with reliable yfinance coverage
UNIVERSE = {
    "BTC": "BTC-USD", "ETH": "ETH-USD", "ADA": "ADA-USD",
    "LINK": "LINK-USD", "DOT": "DOT-USD",
    "AAVE": "AAVE-USD", "ATOM": "ATOM-USD", "LTC": "LTC-USD",
    "SNX": "SNX-USD", "SUSHI": "SUSHI-USD",
    "BAT": "BAT-USD", "ZIL": "ZIL-USD", "KAVA": "KAVA-USD",
    "AXS": "AXS-USD", "1INCH": "1INCH-USD", "YFI": "YFI-USD",
}

# F&G-only regime (no historical BTC dominance available on Basic plan)
def _regime_from_fg(fg_value: int) -> tuple[str, float]:
    if fg_value <= 20:
        return "EXTREME_FEAR", 0.5
    if fg_value <= 35:
        return "RISK_OFF", 0.2
    if fg_value <= 54:
        return "NEUTRAL", 0.5
    if fg_value <= 79:
        return "RISK_ON", 1.0
    return "EXTREME_GREED", 0.3


def run_backtest(top_n: int = 3, initial_capital: float = 10_000) -> dict:
    # --- 1. F&G historical (30 days, newest first) ---
    fg_raw = get_fear_greed_historical(limit=30)
    fg_df = pd.DataFrame(fg_raw)[["timestamp", "value"]].copy()
    fg_df["date"] = pd.to_datetime(fg_df["timestamp"].astype(int), unit="s").dt.date
    fg_df["fg"] = fg_df["value"].astype(int)
    fg_df = fg_df.sort_values("date").reset_index(drop=True)

    start = str(fg_df["date"].iloc[0])
    end   = str(fg_df["date"].iloc[-1])

    # --- 2. Price data ---
    tickers = list(UNIVERSE.values())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    prices = raw["Close"] if "Close" in raw else raw.xs("Close", axis=1, level=0)
    prices.index = pd.to_datetime(prices.index).date
    prices.columns = [c.replace("-USD", "") for c in prices.columns]
    prices = prices.ffill().dropna(how="all")

    # Rename columns back to symbol
    sym_map = {v.replace("-USD", ""): k for k, v in UNIVERSE.items()}
    prices = prices.rename(columns=sym_map)

    # --- 3. Rolling 7-day momentum ---
    momentum = prices.pct_change(7, fill_method=None)

    # --- 4. Daily simulation ---
    common_dates = sorted(set(fg_df["date"]) & set(prices.index))
    fg_lookup = dict(zip(fg_df["date"], fg_df["fg"]))

    portfolio_value = initial_capital
    records = []
    prev_portfolio = portfolio_value

    for i, date in enumerate(common_dates):
        fg_val = fg_lookup.get(date, 50)
        regime_label, size_mult = _regime_from_fg(fg_val)

        if i == 0:
            records.append({
                "date": date, "portfolio": portfolio_value,
                "regime": regime_label, "fg": fg_val,
                "daily_return": 0.0, "holdings": [],
            })
            continue

        prev_date = common_dates[i - 1]
        mom_row = momentum.loc[date] if date in momentum.index else pd.Series(dtype=float)
        mom_row = mom_row.dropna()

        if regime_label in ("RISK_ON",) and not mom_row.empty:
            top_syms = mom_row.nlargest(top_n).index.tolist()
        elif regime_label == "EXTREME_FEAR" and not mom_row.empty:
            top_syms = mom_row.nlargest(top_n).index.tolist()
        else:
            top_syms = []  # cash

        if top_syms:
            # Equal-weight daily return
            day_rets = []
            for sym in top_syms:
                if sym in prices.columns and prev_date in prices.index and date in prices.index:
                    p0 = prices.loc[prev_date, sym]
                    p1 = prices.loc[date, sym]
                    if p0 and p0 > 0:
                        day_rets.append((p1 - p0) / p0)
            avg_ret = float(np.mean(day_rets)) if day_rets else 0.0
            # Scale by size multiplier (remainder in cash = 0% return)
            portfolio_return = avg_ret * size_mult
        else:
            portfolio_return = 0.0

        portfolio_value *= (1 + portfolio_return)
        records.append({
            "date": date,
            "portfolio": round(portfolio_value, 2),
            "regime": regime_label,
            "fg": fg_val,
            "daily_return": round(portfolio_return * 100, 4),
            "holdings": top_syms,
        })

    df = pd.DataFrame(records)

    # --- 5. Benchmark: BTC buy-and-hold ---
    btc_prices = prices["BTC"].reindex([d for d in common_dates if d in prices.index]).dropna()
    if len(btc_prices) > 1:
        btc_return = (btc_prices.iloc[-1] / btc_prices.iloc[0] - 1) * 100
    else:
        btc_return = 0.0

    # --- 6. Metrics ---
    returns = df["daily_return"].values / 100
    total_return = (portfolio_value / initial_capital - 1) * 100
    sharpe = _sharpe(returns)
    max_dd = _max_drawdown(df["portfolio"].values)
    win_rate = float(np.mean(returns > 0)) * 100

    return {
        "period": {"start": start, "end": end, "days": len(common_dates)},
        "metrics": {
            "total_return_pct": round(total_return, 2),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown_pct": round(max_dd, 2),
            "win_rate_pct": round(win_rate, 1),
            "benchmark_btc_return_pct": round(btc_return, 2),
        },
        "daily": df.to_dict("records"),
    }


def _sharpe(returns: np.ndarray, risk_free: float = 0.0) -> float:
    excess = returns - risk_free / 252
    if excess.std() == 0:
        return 0.0
    return float(np.sqrt(252) * excess.mean() / excess.std())


def _max_drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    return float(dd.min() * 100)

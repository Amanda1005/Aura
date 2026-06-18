"""
Feature engineering for XGBoost regime-momentum signal predictor.

Features:
  F&G-based  : value, 1d/7d change, 7d/14d rolling mean, rule-based regime label
  Price-based : BTC 1d/7d return, 7d volatility  (market proxy)
  Calendar   : day of week (crypto has intra-week patterns)

Target:
  next_day_positive (binary) — will tomorrow's top-3 momentum basket return > 0?
  Built from actual BTC returns as proxy (top tokens correlate ~0.7 with BTC in bear regimes).
"""

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime, timedelta


def _fetch_alternative_fg(days: int = 365) -> pd.DataFrame:
    url = f"https://api.alternative.me/fng/?limit={days}&format=json"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()["data"]
    df = pd.DataFrame(data)[["timestamp", "value"]].copy()
    df["date"] = pd.to_datetime(df["timestamp"].astype(int), unit="s").dt.date
    df["fg"] = df["value"].astype(int)
    return df[["date", "fg"]].sort_values("date").reset_index(drop=True)


def _fetch_btc_prices(start: str, end: str) -> pd.Series:
    raw = yf.download("BTC-USD", start=start, end=end, auto_adjust=True, progress=False)
    close = raw["Close"].squeeze()
    close.index = pd.to_datetime(close.index).date
    return close


def build_features(days: int = 365) -> pd.DataFrame:
    fg_df = _fetch_alternative_fg(days + 30)  # extra buffer for rolling windows

    start = str(fg_df["date"].iloc[0] - timedelta(days=1))
    end   = str(fg_df["date"].iloc[-1] + timedelta(days=2))
    btc   = _fetch_btc_prices(start, end)

    df = fg_df.copy()
    df = df[df["date"].isin(btc.index)].reset_index(drop=True)
    df["btc_close"] = df["date"].map(btc)

    # F&G features
    df["fg_change_1d"]  = df["fg"].diff(1)
    df["fg_change_7d"]  = df["fg"].diff(7)
    df["fg_ma_7d"]      = df["fg"].rolling(7).mean()
    df["fg_ma_14d"]     = df["fg"].rolling(14).mean()
    df["fg_above_ma7"]  = (df["fg"] > df["fg_ma_7d"]).astype(int)

    # Rule-based regime as ordinal feature (0=EXTREME_FEAR … 5=EXTREME_GREED)
    def _regime_int(v):
        if v <= 20: return 0
        if v <= 35: return 1
        if v <= 54: return 2
        if v <= 79: return 3
        return 4

    df["regime_int"] = df["fg"].apply(_regime_int)

    # BTC price features
    df["btc_ret_1d"]  = df["btc_close"].pct_change(1)
    df["btc_ret_7d"]  = df["btc_close"].pct_change(7)
    df["btc_vol_7d"]  = df["btc_ret_1d"].rolling(7).std()

    # Calendar
    df["day_of_week"] = pd.to_datetime(df["date"]).dt.dayofweek

    # Target: is tomorrow's BTC return positive? (proxy for top-momentum basket)
    df["next_btc_ret"] = df["btc_ret_1d"].shift(-1)
    df["target"]       = (df["next_btc_ret"] > 0).astype(int)

    feature_cols = [
        "fg", "fg_change_1d", "fg_change_7d",
        "fg_ma_7d", "fg_ma_14d", "fg_above_ma7",
        "regime_int",
        "btc_ret_1d", "btc_ret_7d", "btc_vol_7d",
        "day_of_week",
    ]

    df = df.dropna(subset=feature_cols + ["target"]).reset_index(drop=True)
    return df[["date"] + feature_cols + ["target", "next_btc_ret"]]


FEATURE_COLS = [
    "fg", "fg_change_1d", "fg_change_7d",
    "fg_ma_7d", "fg_ma_14d", "fg_above_ma7",
    "regime_int",
    "btc_ret_1d", "btc_ret_7d", "btc_vol_7d",
    "day_of_week",
]

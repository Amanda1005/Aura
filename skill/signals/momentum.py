"""
Token momentum scoring from CMC listings data.

Score = 0.5 * z(24h_pct) + 0.3 * z(7d_pct) + 0.2 * z(volume_24h)
Z-scores normalize across the token universe so one outlier doesn't dominate.
"""

import pandas as pd


# BEP-20 tokens eligible for the competition (subset with sufficient liquidity)
ELIGIBLE_SYMBOLS = {
    "ETH", "USDT", "USDC", "XRP", "DOGE", "ADA", "LINK", "BCH", "DAI",
    "DOT", "UNI", "AAVE", "ATOM", "FIL", "INJ", "FET", "CAKE", "PENDLE",
    "AXS", "TWT", "RAY", "COMP", "BAT", "APE", "SNX", "SUSHI", "LTC",
    "AVAX", "SHIB", "FLOKI", "LDO", "ZRO", "STG", "1INCH", "YFI", "ZIL",
    "KAVA", "ELF", "ACH", "ROSE",
}


def score_tokens(listings: list[dict]) -> pd.DataFrame:
    rows = []
    for token in listings:
        sym = token["symbol"]
        if sym not in ELIGIBLE_SYMBOLS:
            continue
        q = token.get("quote", {}).get("USD", {})
        rows.append({
            "symbol": sym,
            "price": q.get("price"),
            "pct_24h": q.get("percent_change_24h"),
            "pct_7d": q.get("percent_change_7d"),
            "volume_24h": q.get("volume_24h"),
            "market_cap": q.get("market_cap"),
        })

    df = pd.DataFrame(rows).dropna()
    if df.empty:
        return df

    for col in ["pct_24h", "pct_7d", "volume_24h"]:
        std = df[col].std()
        df[f"z_{col}"] = (df[col] - df[col].mean()) / std if std > 0 else 0.0

    df["momentum_score"] = (
        0.5 * df["z_pct_24h"] +
        0.3 * df["z_pct_7d"] +
        0.2 * df["z_volume_24h"]
    )
    return df.sort_values("momentum_score", ascending=False).reset_index(drop=True)

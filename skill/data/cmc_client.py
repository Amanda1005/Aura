import os
import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "https://pro-api.coinmarketcap.com"


def _get(path: str, params: dict = None) -> dict:
    headers = {
        "X-CMC_PRO_API_KEY": os.getenv("CMC_API_KEY"),
        "Accept": "application/json",
    }
    r = requests.get(f"{BASE}{path}", headers=headers, params=params or {}, timeout=10)
    r.raise_for_status()
    return r.json()


def get_fear_greed_latest() -> dict:
    return _get("/v3/fear-and-greed/latest")["data"]


def get_fear_greed_historical(limit: int = 30) -> list[dict]:
    return _get("/v3/fear-and-greed/historical", {"limit": limit})["data"]


def get_global_metrics() -> dict:
    return _get("/v1/global-metrics/quotes/latest")["data"]


def get_listings(limit: int = 200, convert: str = "USD") -> list[dict]:
    data = _get("/v1/cryptocurrency/listings/latest", {"limit": limit, "convert": convert})
    return data["data"]


def get_quotes(symbols: list[str], convert: str = "USD") -> dict:
    data = _get("/v2/cryptocurrency/quotes/latest", {"symbol": ",".join(symbols), "convert": convert})
    return data["data"]

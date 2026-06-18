"""
TWAK CLI wrapper — calls Trust Wallet Agent Kit via subprocess.
Simpler and more reliable than the REST server approach.
"""

import json
import subprocess
import logging

log = logging.getLogger(__name__)


def _run(args: list[str]) -> dict:
    """Run a twak CLI command and return parsed JSON output."""
    cmd = ["twak"] + args + ["--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"TWAK error: {result.stderr.strip()}")
    return json.loads(result.stdout)


class TWAKClient:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def start(self):
        log.info("[TWAK] CLI mode ready")

    def stop(self):
        pass

    def get_balance(self, chain: str = "bsc") -> dict:
        return _run(["wallet", "balance", "--chain", chain])

    def get_portfolio_value_usd(self, chain: str = "bsc") -> float:
        try:
            balance = self.get_balance(chain)
            total = float(balance.get("totalUsd", 0))
            for token in balance.get("tokens", []):
                total += float(token.get("valueUsd", 0))
            return total
        except Exception:
            log.warning("[TWAK] wallet balance unavailable, falling back to BSCScan")
            return self._get_portfolio_bscscan()

    def _get_portfolio_bscscan(self) -> float:
        import requests
        address = "0xF5cc8e032a368D07d3e2Cf94Bd7bC6CB2F047631"
        BSC_RPC = "https://bsc-dataseed.binance.org/"
        USDT_CONTRACT = "0x55d398326f99059fF775485246999027B3197955"
        try:
            bnb_resp = requests.post(BSC_RPC, json={
                "jsonrpc": "2.0", "method": "eth_getBalance",
                "params": [address, "latest"], "id": 1,
            }, timeout=10).json()
            bnb_amount = int(bnb_resp["result"], 16) / 1e18

            padded = address[2:].lower().zfill(64)
            usdt_resp = requests.post(BSC_RPC, json={
                "jsonrpc": "2.0", "method": "eth_call",
                "params": [{"to": USDT_CONTRACT, "data": "0x70a08231" + padded}, "latest"],
                "id": 2,
            }, timeout=10).json()
            usdt_amount = int(usdt_resp["result"], 16) / 1e18

            bnb_usd = self.get_price("BNB") or 600.0
            total = bnb_amount * bnb_usd + usdt_amount
            log.info(f"[RPC] BNB={bnb_amount:.4f}(${bnb_amount*bnb_usd:.2f}) USDT={usdt_amount:.2f} Total=${total:.2f}")
            return total
        except Exception as e:
            log.error(f"[RPC] fallback failed: {e}")
            return 0.0

    def swap(
        self,
        amount: float,
        from_token: str,
        to_token: str,
        chain: str = "bsc",
        slippage: float = 1.0,
    ) -> dict:
        if self.dry_run:
            log.info(f"[DRY RUN] swap {amount:.2f} {from_token} → {to_token} on {chain}")
            return {"status": "dry_run", "from": from_token, "to": to_token, "amount": amount}

        log.info(f"[TWAK] swap {amount:.4f} {from_token} → {to_token} --chain {chain}")
        return _run([
            "swap", str(round(amount, 6)), from_token, to_token,
            "--chain", chain,
            "--slippage", str(slippage),
        ])

    def register_competition(self) -> dict:
        log.info("[TWAK] Registering for competition...")
        return _run(["compete", "register"])

    def get_price(self, symbol: str) -> float:
        try:
            data = _run(["price", symbol])
            return float(data.get("price", 0))
        except Exception:
            return 0.0

"""
Aura — Autonomous BSC Trading Agent
BNB Hack: AI Trading Agent Edition — Track 1

Main loop: runs every hour, reads CMC signal, applies 5-layer risk gate,
executes via TWAK if all gates pass.
"""

import argparse
import json
import logging
import time
from datetime import datetime, timezone

from skill.skill import run as get_signal
from twak_client import TWAKClient
from llm_reviewer import review_trade

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Risk parameters ────────────────────────────────────────────────────────────
MAX_POSITION_PCT   = 0.10   # max 10% of portfolio per token
DAILY_LOSS_LIMIT   = 0.03   # L4: stop if down >3% today
MAX_DRAWDOWN_LIMIT = 0.15   # L5: halt if total drawdown >15%
MIN_MOMENTUM_SCORE = 0.30   # L3: skip if momentum score below this
ML_CONFIDENCE_MIN  = 0.50   # L2: skip if ML confidence below this
SCAN_INTERVAL_SECS = 3600   # 1 hour

# ── Exit parameters ───────────────────────────────────────────────────────────
SL_PCT         = -0.08   # Stop loss: exit if down >8%
TP_PCT         =  0.15   # Take profit: exit if up >15%
MAX_HOLD_HOURS =  24     # Force exit after 24 hours

# ── Competition compliance ─────────────────────────────────────────────────────
COMPLIANCE_HOUR     = 21    # UTC hour — fire compliance trade if no trade yet today
COMPLIANCE_SIZE_PCT = 0.02  # 2% of portfolio — minimum trade for daily qualification

# ── Agent state ────────────────────────────────────────────────────────────────
state = {
    "start_value":        None,
    "day_start_value":    None,
    "current_day":        None,
    "daily_stopped":      False,
    "halted":             False,
    "scan_count":         0,
    "consecutive_losses": 0,
    "last_trade_date":    None,  # tracks last day a BUY was executed
    "positions":          {},  # symbol → {amount_tokens, entry_price, amount_usd, entry_time}
    "trades":             [],
}


def _position_scale() -> float:
    """Drawdown ladder: reduce size after consecutive losses."""
    losses = state["consecutive_losses"]
    if losses >= 3:
        return 0.25
    if losses >= 2:
        return 0.50
    return 1.0


def _check_exits(twak: TWAKClient, signal):
    """Check all open positions for SL / TP / regime exit / max hold time."""
    for symbol in list(state["positions"].keys()):
        pos = state["positions"][symbol]
        current_price = twak.get_price(symbol)
        if current_price <= 0:
            log.warning(f"[EXIT] Cannot price {symbol}, skipping")
            continue

        ret = (current_price / pos["entry_price"]) - 1
        hold_h = (
            datetime.now(timezone.utc) - datetime.fromisoformat(pos["entry_time"])
        ).total_seconds() / 3600

        exit_reason = ""
        if ret <= SL_PCT:
            exit_reason = f"SL {ret:+.1%}"
        elif ret >= TP_PCT:
            exit_reason = f"TP {ret:+.1%}"
        elif signal and signal.regime["label"] == "EXTREME_GREED":
            exit_reason = f"Regime→EXTREME_GREED"
        elif hold_h >= MAX_HOLD_HOURS:
            exit_reason = f"MaxHold {hold_h:.0f}h"

        if not exit_reason:
            log.info(f"[HOLD] {symbol} return={ret:+.1%} hold={hold_h:.1f}h")
            continue

        log.info(f"[EXIT] {symbol} | {exit_reason} | return={ret:+.1%}")
        result = twak.swap(
            amount=pos["amount_tokens"],
            from_token=symbol,
            to_token="USDT",
            chain="bsc",
            slippage=1.5,
        )

        state["consecutive_losses"] = state["consecutive_losses"] + 1 if ret < 0 else 0

        state["trades"].append({
            "time":       datetime.now(timezone.utc).isoformat(),
            "action":     "SELL",
            "symbol":     symbol,
            "return_pct": round(ret * 100, 2),
            "reason":     exit_reason,
            "result":     result,
        })
        del state["positions"][symbol]
        log.info(f"Sell result: {result}")


def _needs_compliance_trade() -> bool:
    """True if no trade yet today and it's past COMPLIANCE_HOUR UTC."""
    today = str(datetime.now(timezone.utc).date())
    hour  = datetime.now(timezone.utc).hour
    return hour >= COMPLIANCE_HOUR and state["last_trade_date"] != today


def _do_compliance_trade(twak: TWAKClient, signal, portfolio_usd: float):
    """Minimal daily trade to meet competition 1-trade/day requirement."""
    if state["daily_stopped"] or state["halted"]:
        log.info("[COMPLIANCE] Skipped — halt active")
        return
    if not signal.top_long_candidates:
        log.info("[COMPLIANCE] Skipped — no token candidates")
        return

    symbol = signal.top_long_candidates[0]["symbol"]
    if symbol in state["positions"]:
        log.info(f"[COMPLIANCE] Already holding {symbol}, qualification satisfied")
        state["last_trade_date"] = str(datetime.now(timezone.utc).date())
        return

    position_usd = portfolio_usd * COMPLIANCE_SIZE_PCT
    log.info(f"[COMPLIANCE] No trade today — forcing qualification buy: {symbol} ${position_usd:.2f}")

    entry_price = twak.get_price(symbol)
    result = twak.swap(
        amount=position_usd,
        from_token="USDT",
        to_token=symbol,
        chain="bsc",
        slippage=1.0,
    )

    today = str(datetime.now(timezone.utc).date())
    state["last_trade_date"] = today

    if entry_price > 0:
        state["positions"][symbol] = {
            "amount_tokens": position_usd / entry_price,
            "entry_price":   entry_price,
            "amount_usd":    position_usd,
            "entry_time":    datetime.now(timezone.utc).isoformat(),
        }

    state["trades"].append({
        "time":        datetime.now(timezone.utc).isoformat(),
        "action":      "BUY",
        "scan":        state["scan_count"],
        "symbol":      symbol,
        "amount_usd":  position_usd,
        "entry_price": entry_price,
        "regime":      signal.regime["label"],
        "compliance":  True,
        "result":      result,
    })
    log.info(f"[COMPLIANCE] Result: {result}")


def _risk_gate(signal, portfolio_usd: float) -> tuple[bool, str]:
    """5-layer risk gate. Returns (pass, reason)."""
    regime = signal.regime

    # L1: Regime gate
    if regime["signal_bias"] == "NEUTRAL" and regime["label"] in ("RISK_OFF", "NEUTRAL"):
        return False, f"L1 BLOCKED: Regime={regime['label']}, bias=NEUTRAL"

    # L2: ML confidence gate
    conf = signal.ml_signal["confidence"]
    if conf < ML_CONFIDENCE_MIN:
        return False, f"L2 BLOCKED: ML confidence={conf:.3f} < {ML_CONFIDENCE_MIN}"

    # L3: Momentum quality gate
    top = signal.top_long_candidates
    score = top[0]["momentum_score"] if top else 0
    if not top or score < MIN_MOMENTUM_SCORE:
        return False, f"L3 BLOCKED: momentum_score={score:.3f} < {MIN_MOMENTUM_SCORE}"

    # L4: Daily loss gate
    if state["daily_stopped"]:
        return False, "L4 BLOCKED: Daily loss limit hit"

    today = datetime.now(timezone.utc).date()
    if state["current_day"] == today and state["day_start_value"]:
        daily_ret = (portfolio_usd - state["day_start_value"]) / state["day_start_value"]
        if daily_ret < -DAILY_LOSS_LIMIT:
            state["daily_stopped"] = True
            return False, f"L4 BLOCKED: Daily loss {daily_ret:.1%}"

    # L5: Max drawdown gate
    if state["halted"]:
        return False, "L5 BLOCKED: Max drawdown halt active"

    if state["start_value"]:
        total_dd = (portfolio_usd - state["start_value"]) / state["start_value"]
        if total_dd < -MAX_DRAWDOWN_LIMIT:
            state["halted"] = True
            return False, f"L5 BLOCKED: Drawdown {total_dd:.1%} — HALTED"

    return True, "PASS"


def _reset_daily(portfolio_usd: float):
    today = datetime.now(timezone.utc).date()
    if state["current_day"] != today:
        state["current_day"]     = today
        state["day_start_value"] = portfolio_usd
        state["daily_stopped"]   = False
        log.info(f"New day {today} — daily gate reset. Portfolio: ${portfolio_usd:.2f}")


def _save_state():
    with open("agent_state.json", "w") as f:
        json.dump(state, f, indent=2, default=str)


def run_scan(twak: TWAKClient):
    state["scan_count"] += 1
    log.info(f"=== Scan #{state['scan_count']} ===")

    portfolio_usd = twak.get_portfolio_value_usd("bsc")
    log.info(f"Portfolio: ${portfolio_usd:.2f}")

    if state["start_value"] is None:
        state["start_value"] = portfolio_usd
        log.info(f"Starting value: ${portfolio_usd:.2f}")

    _reset_daily(portfolio_usd)

    # Get signal (needed for both exit check and entry)
    signal = get_signal(top_n=3)
    log.info(
        f"Regime: {signal.regime['label']} | "
        f"F&G: {signal.raw_signals['fear_greed_value']} | "
        f"ML conf: {signal.ml_signal['confidence']:.3f} | "
        f"Effective size: {signal.effective_size_pct}%"
    )

    # Always check exits first
    _check_exits(twak, signal)

    # 5-layer risk gate for new entries
    ok, reason = _risk_gate(signal, portfolio_usd)
    log.info(f"Risk gate: {reason}")

    if not ok:
        if _needs_compliance_trade():
            _do_compliance_trade(twak, signal, portfolio_usd)
        _save_state()
        return

    # Pick top candidate
    top_token = signal.top_long_candidates[0]
    symbol    = top_token["symbol"]

    if symbol in state["positions"]:
        log.info(f"Already holding {symbol}, skipping")
        _save_state()
        return

    # LLM final review
    llm_ok, llm_reason = review_trade(signal)
    if not llm_ok:
        log.info(f"[LLM] VETOED: {llm_reason}")
        _save_state()
        return
    log.info(f"[LLM] APPROVED: {llm_reason}")

    # Position size with drawdown ladder
    scale        = _position_scale()
    position_usd = portfolio_usd * MAX_POSITION_PCT * (signal.effective_size_pct / 100) * scale
    if scale < 1.0:
        log.info(f"Drawdown ladder: losses={state['consecutive_losses']} → scale={scale:.0%}")

    log.info(
        f"BUY {symbol} | momentum={top_token['momentum_score']:.3f} | "
        f"size=${position_usd:.2f}"
    )

    entry_price = twak.get_price(symbol)
    result = twak.swap(
        amount=position_usd,
        from_token="USDT",
        to_token=symbol,
        chain="bsc",
        slippage=1.0,
    )

    if entry_price > 0:
        state["positions"][symbol] = {
            "amount_tokens": position_usd / entry_price,
            "entry_price":   entry_price,
            "amount_usd":    position_usd,
            "entry_time":    datetime.now(timezone.utc).isoformat(),
        }

    state["last_trade_date"] = str(datetime.now(timezone.utc).date())
    state["trades"].append({
        "time":          datetime.now(timezone.utc).isoformat(),
        "action":        "BUY",
        "scan":          state["scan_count"],
        "symbol":        symbol,
        "amount_usd":    position_usd,
        "entry_price":   entry_price,
        "regime":        signal.regime["label"],
        "ml_confidence": signal.ml_signal["confidence"],
        "result":        result,
    })
    log.info(f"Buy result: {result}")
    _save_state()


def main():
    parser = argparse.ArgumentParser(description="Aura autonomous agent")
    parser.add_argument("--dry-run", action="store_true", help="Signal only, no execution")
    parser.add_argument("--once",    action="store_true", help="Run one scan and exit")
    parser.add_argument("--status",  action="store_true", help="Show portfolio status and exit")
    args = parser.parse_args()

    twak = TWAKClient(dry_run=args.dry_run)

    if args.status:
        twak.start()
        print(f"Portfolio (BSC): ${twak.get_portfolio_value_usd('bsc'):.2f}")
        twak.stop()
        return

    log.info("Aura Agent starting...")
    if args.dry_run:
        log.info("DRY RUN MODE — no trades will execute")

    twak.start()
    try:
        if args.once:
            run_scan(twak)
        else:
            while True:
                run_scan(twak)
                log.info(f"Next scan in {SCAN_INTERVAL_SECS // 60} minutes...")
                time.sleep(SCAN_INTERVAL_SECS)
    except KeyboardInterrupt:
        log.info("Agent stopped by user.")
    finally:
        twak.stop()


if __name__ == "__main__":
    main()

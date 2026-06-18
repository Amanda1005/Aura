#!/bin/bash

source venv/bin/activate

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║         AURA — Autonomous BSC Trading Agent      ║"
echo "║     BNB Hack: AI Trading Agent Edition 2026      ║"
echo "║   CoinMarketCap × Trust Wallet × BNB Chain       ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

sleep 1

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 1 — Live Market Signal (CMC AI Agent Hub)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
python run_skill.py
echo ""

sleep 1

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 2 — Agent Decision Loop (dry run)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
python agent.py --dry-run --once
echo ""

sleep 1

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 3 — Backtest Results (29-day bear market)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
python run_backtest.py
echo ""

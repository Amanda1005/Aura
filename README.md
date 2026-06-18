<p align="center">
  <img src="Aura.png" alt="Aura" width="120" />
</p>

# Aura — Autonomous BSC Trading Agent

**BNB Hack: AI Trading Agent Edition — Track 1 Submission**
Powered by CoinMarketCap AI Agent Hub × Trust Wallet Agent Kit × BNB Chain

[![Aura Demo](https://img.youtube.com/vi/MNhQzuih-5U/maxresdefault.jpg)](https://www.youtube.com/watch?v=MNhQzuih-5U)

---

## TL;DR for Judges

| | |
|---|---|
| **What** | Autonomous trading agent: CMC market regime → XGBoost calibration → Groq LLM review → BSC execution via TWAK |
| **Signal** | Fear & Greed + BTC Dominance → 6-state Regime × XGBoost confidence calibrator |
| **AI Brain** | Groq Llama-3.3-70b reviews every trade before execution — approves or vetoes with reasoning |
| **Execution** | Trust Wallet Agent Kit (local signing, non-custodial, autonomous) |
| **Exit Logic** | Stop Loss −8% / Take Profit +15% / Regime exit / 24h max hold |
| **Risk** | 5-layer risk gate + drawdown ladder (position scales down after consecutive losses) |
| **Backtest** | −2.27% vs BTC −14.53% over 29 days (May–June 2026 bear market) |
| **Design principle** | Rule engine is the foundation — AI calibrates and reviews, never controls alone |

---

## The Problem

AI trading agents fail the same way human traders do: they chase momentum in greed markets and panic-exit in fear markets. They don't know *when* to act — only *how*.

Most agents treat every hour as a trading opportunity. Aura treats market regime as a first-class signal: **most hours, the right action is to do nothing.**

---

## Architecture

```
Every hour:
  ┌─────────────────────────────────────┐
  │  CMC AI Agent Hub                   │
  │  • Fear & Greed Index               │
  │  • BTC Dominance (Global Metrics)   │
  │  • Token momentum (Listings API)    │
  └──────────────┬──────────────────────┘
                 │
  ┌──────────────▼──────────────────────┐
  │  Regime Classifier (rule-based)     │
  │  6 states: EXTREME_FEAR →           │
  │  EXTREME_GREED × BTC dom matrix     │
  │  → signal_bias + base position size │
  └──────────────┬──────────────────────┘
                 │
  ┌──────────────▼──────────────────────┐
  │  XGBoost Confidence Calibrator      │
  │  Trained on 1yr F&G + BTC features  │
  │  Walk-forward validated (6 folds)   │
  │  → confidence_score → size mult     │
  └──────────────┬──────────────────────┘
                 │
  ┌──────────────▼──────────────────────┐
  │  5-Layer Risk Gate                  │
  │  L1: Regime gate (block RISK_OFF +  │
  │      NEUTRAL)                       │
  │  L2: ML confidence gate (< 0.5)     │
  │  L3: Momentum quality gate (< 0.3)  │
  │  L4: Daily loss gate (> 3%)         │
  │  L5: Max drawdown gate (> 15%)      │
  └──────────────┬──────────────────────┘
                 │ passes all 5 gates?
  ┌──────────────▼──────────────────────┐
  │  Groq LLM Review (Llama-3.3-70b)    │
  │  Reviews regime + ML + momentum     │
  │  context, approves or vetoes with   │
  │  chain-of-thought reasoning         │
  └──────────────┬──────────────────────┘
                 │ approved?
  ┌──────────────▼──────────────────────┐
  │  Trust Wallet Agent Kit (TWAK)      │
  │  Local signing — keys never leave   │
  │  this machine                       │
  │  twak swap <amount> <from> <to>     │
  │  --chain bsc                        │
  └──────────────┬──────────────────────┘
                 │
         BSC on-chain execution

  Exit Logic (every scan):
  • Stop Loss  −8%  → sell → USDT
  • Take Profit +15% → sell → USDT
  • Regime → EXTREME_GREED → exit all
  • Max hold 24h → force exit
  • Drawdown ladder: 2 losses → 50% size,
    3+ losses → 25% size
```

---

## Design Principle: AI as Tool, Not Crutch

Three layers of intelligence, each with a distinct role:

1. **Rule-based Regime** — structural market state (deterministic, always runs)
2. **XGBoost Calibrator** — historical confidence calibration (statistical)
3. **Groq LLM Reviewer** — final sanity check with market reasoning (generative)

If ML or LLM fails, the rule engine continues operating. Every trade decision is traceable to a deterministic rule at Layer 1.

---

## Signal Logic

### Market Regime (6 states)

| Regime | F&G | BTC Dom | Bias | Base Size |
|---|---|---|---|---|
| EXTREME_FEAR | ≤ 20 | any | CONTRARIAN_LONG | 50% |
| RISK_OFF | ≤ 35 | > 52% | NEUTRAL | 20% |
| NEUTRAL | 36–54 | any | NEUTRAL | 50% |
| RISK_ON_BTC | ≥ 55 | > 52% | LONG (majors) | 70% |
| RISK_ON_ALT | ≥ 55 | ≤ 52% | LONG (alts) | 100% |
| EXTREME_GREED | ≥ 80 | any | CONTRARIAN_SHORT | 30% |

### Momentum Scoring

```
score = 0.5 × z(24h_return) + 0.3 × z(7d_return) + 0.2 × z(volume_24h)
```

Z-scored across eligible BEP-20 universe. Top 3 tokens by score are candidates.

### Effective Position Size

```
effective_size = regime.base_size × ml_confidence_multiplier × drawdown_scale
```

| ML Confidence | Multiplier |
|---|---|
| ≥ 0.65 | 1.0× (full) |
| 0.55–0.64 | 0.7× |
| < 0.55 | 0.3× |

| Consecutive Losses | Drawdown Scale |
|---|---|
| 0–1 | 1.0× (full) |
| 2 | 0.5× |
| 3+ | 0.25× |

---

## 5-Layer Risk Gate + LLM Review

| Layer | Rule | Threshold |
|---|---|---|
| L1 | Regime gate | RISK_OFF / NEUTRAL → no new positions |
| L2 | ML confidence gate | confidence < 0.5 → block entry |
| L3 | Momentum quality gate | momentum_score < 0.3 → block entry |
| L4 | Daily loss gate | portfolio down > 3% today → stop for the day |
| L5 | Max drawdown gate | total drawdown > 15% → close all, halt |
| LLM | Groq Llama-3.3-70b | reviews macro context, vetoes if conditions wrong |

---

## Exit Logic

| Trigger | Action |
|---|---|
| Position down −8% | Stop loss → sell all → USDT |
| Position up +15% | Take profit → sell all → USDT |
| Regime → EXTREME_GREED | Distribution signal → exit all positions |
| Hold time > 24h | Force exit regardless of P&L |

---

## Backtest Results (29 days, May 19 – June 17 2026)

| Metric | Value |
|---|---|
| Strategy return | −2.27% |
| BTC buy & hold | −14.53% |
| Outperformance | +12.26% |
| Sharpe ratio | −0.868 |
| Max drawdown | −7.76% |
| Win rate | 13.8% |

**Context:** Low win rate reflects the strategy spending most days in cash (RISK_OFF during a sustained bear market). Capital preservation was the correct behavior — and the system delivered it.

---

## ML Model

- **Algorithm:** XGBoost classifier
- **Features:** F&G value, 1d/7d F&G change, 7d/14d rolling mean, BTC 1d/7d return, BTC 7-day volatility, day of week, rule-based regime
- **Training data:** 1 year (2025–2026), Alternative.me F&G + yfinance prices
- **Validation:** Walk-forward (6 folds, 6-month training window, 1-month test)
- **Role:** Position-sizing calibrator — does not make entry/exit decisions

Walk-forward results showed near-random AUC (0.50) for next-day direction prediction — confirming that short-term price movement is not predictable from sentiment alone. XGBoost is therefore used for confidence calibration, not signal generation. The regime rules carry the structural signal.

---

## Tech Stack

| Component | Technology |
|---|---|
| Market data | CMC AI Agent Hub (REST API) |
| Signal generation | Python — regime rules + z-score momentum |
| ML calibration | XGBoost + scikit-learn (walk-forward validated) |
| LLM review | Groq Llama-3.3-70b (chain-of-thought trade review) |
| Execution | Trust Wallet Agent Kit (TWAK CLI) |
| Chain | BSC (BNB Smart Chain) |
| Self-custody | TWAK local wallet — keys encrypted on-device |

---

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/Amanda1005/Aura.git
cd Aura
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Install TWAK
npm install -g @trustwallet/cli
twak setup

# 3. Configure environment
cp .env.example .env
# Fill in: CMC_API_KEY, GROQ_API_KEY

# 4. Train ML model
python -m ml.train

# 5. Dry run — see signal without executing
python agent.py --dry-run

# 6. Live mode
python agent.py
```

---

## Agent Wallet

**BSC Address:** `0xF5cc8e032a368D07d3e2Cf94Bd7bC6CB2F047631`

Competition registration: `twak compete register`

---

## Honest Reporting

This agent was backtested over a 29-day bear market. The strategy spent the majority of time in cash — which is correct behavior for a risk-aware system in adverse conditions.

The ML model's direction-prediction AUC of 0.50 is disclosed. This finding shaped the architecture: ML is a calibrator, not a predictor.

The Groq LLM reviewer is a final sanity check — it can veto technically valid signals when macro context is unfavorable. If LLM is unavailable, the agent falls back to rule-based execution.

---

## Repository Structure

```
agent.py              Autonomous agent main loop (scan + exit + entry)
twak_client.py        TWAK CLI wrapper + BSC RPC portfolio fallback
llm_reviewer.py       Groq LLM trade review (final gate before execution)
skill/
  skill.py            CMC Skill — main signal entry point
  data/cmc_client.py  CMC API wrapper
  signals/regime.py   6-state regime classifier
  signals/momentum.py Z-score momentum scoring
ml/
  features.py         Feature engineering (F&G + BTC)
  train.py            XGBoost + walk-forward validation
  predictor.py        Live confidence inference
backtest/
  backtest.py         29-day backtest (CMC F&G + yfinance)
run_skill.py          Test current signal output
run_backtest.py       Reproduce backtest results
```

---

*Built for BNB Hack: AI Trading Agent Edition — June 2026*
*CoinMarketCap × Trust Wallet × BNB Chain*

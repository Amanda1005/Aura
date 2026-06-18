"""
Groq LLM trade reviewer — final gate before execution.
Approves or vetoes a trade based on market context + signal.
Falls back to approve if API unavailable.
"""

import logging
import os

log = logging.getLogger(__name__)


def review_trade(signal) -> tuple[bool, str]:
    """
    Ask Groq LLM to review the trade signal.
    Returns (approve: bool, reason: str).
    Falls back to True if GROQ_API_KEY not set or call fails.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        log.warning("[LLM] GROQ_API_KEY not set, skipping review")
        return True, "LLM skipped (no key)"

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        top = signal.top_long_candidates[0]
        prompt = f"""You are a risk-aware crypto trading AI reviewing a BSC trade signal.
The rule-based system and ML model already approved this trade after 5 risk checks.
Your job: final sanity check. Veto only if there is a strong macro reason NOT to enter.

Market Context:
- Fear & Greed Index: {signal.raw_signals['fear_greed_value']} ({signal.raw_signals.get('fear_greed_label', '')})
- Market Regime: {signal.regime['label']} (bias: {signal.regime['signal_bias']})
- BTC Dominance: {signal.raw_signals.get('btc_dominance', 'N/A')}%
- ML Confidence: {signal.ml_signal['confidence']:.3f}
- Effective Position Size: {signal.effective_size_pct}%

Trade Candidate:
- Token: {top['symbol']}
- Momentum Score: {top['momentum_score']:.3f}
- 24h Return: {top.get('pct_24h', 'N/A')}%
- 7d Return: {top.get('pct_7d', 'N/A')}%

Reply with exactly: BUY or SKIP, then one sentence reason."""

        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.1,
        )
        text = resp.choices[0].message.content.strip()
        approve = text.upper().startswith("BUY")
        log.info(f"[LLM] {text}")
        return approve, text

    except Exception as e:
        log.warning(f"[LLM] Review failed ({e}), defaulting to approve")
        return True, f"LLM error: {e}"

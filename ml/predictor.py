"""
Live inference: generates ML confidence score for current market conditions.

Confidence score = XGBoost predicted probability that the current feature
set resembles historical conditions where the momentum strategy succeeded.

Used to adjust position sizing on top of the rule-based regime signal:
  final_size = regime.size_multiplier * confidence_multiplier(score)
"""

import pickle
import numpy as np
import pandas as pd
from pathlib import Path

from ml.features import FEATURE_COLS
from ml.train import MODEL_PATH


def _confidence_multiplier(score: float) -> float:
    if score >= 0.65:
        return 1.0   # high confidence → full regime size
    if score >= 0.55:
        return 0.7   # moderate → partial
    return 0.3        # low confidence → minimal exposure


def predict_confidence(features: dict) -> dict:
    """
    features: dict with keys matching FEATURE_COLS
    Returns confidence score + position size multiplier.
    """
    if not MODEL_PATH.exists():
        return {"confidence": 0.5, "confidence_multiplier": 0.7, "ml_available": False}

    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)

    row = pd.DataFrame([features])[FEATURE_COLS].values
    proba = float(model.predict_proba(row)[0, 1])
    mult  = _confidence_multiplier(proba)

    return {
        "confidence": round(proba, 4),
        "confidence_multiplier": mult,
        "ml_available": True,
    }

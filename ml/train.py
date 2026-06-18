"""
Walk-forward validation + XGBoost training.

Walk-forward setup:
  Training window : 6 months (182 days)
  Test window     : 1 month  (30 days)
  Step            : 1 month  (30 days)

Final model: retrained on all available data, saved for live inference.
"""

import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import shap
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

from ml.features import build_features, FEATURE_COLS

TRAIN_DAYS  = 182
TEST_DAYS   = 30
STEP_DAYS   = 30
MODEL_PATH  = Path(__file__).parent / "model.pkl"
METRICS_PATH = Path(__file__).parent / "metrics.json"


def _xgb() -> XGBClassifier:
    return XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
        verbosity=0,
    )


def walk_forward(df: pd.DataFrame) -> dict:
    results = []
    n = len(df)
    start = TRAIN_DAYS

    while start + TEST_DAYS <= n:
        train = df.iloc[start - TRAIN_DAYS : start]
        test  = df.iloc[start : start + TEST_DAYS]

        X_train = train[FEATURE_COLS].values
        y_train = train["target"].values
        X_test  = test[FEATURE_COLS].values
        y_test  = test["target"].values

        model = _xgb()
        model.fit(X_train, y_train)

        proba  = model.predict_proba(X_test)[:, 1]
        preds  = (proba >= 0.5).astype(int)
        acc    = accuracy_score(y_test, preds)
        auc    = roc_auc_score(y_test, proba) if len(np.unique(y_test)) > 1 else 0.5

        results.append({
            "period_start": str(test["date"].iloc[0]),
            "period_end":   str(test["date"].iloc[-1]),
            "accuracy":     round(acc, 4),
            "roc_auc":      round(auc, 4),
            "n_test":       len(test),
        })

        start += STEP_DAYS

    return {
        "folds": results,
        "mean_accuracy": round(np.mean([r["accuracy"] for r in results]), 4),
        "mean_roc_auc":  round(np.mean([r["roc_auc"]  for r in results]), 4),
    }


def train_final(df: pd.DataFrame) -> XGBClassifier:
    X = df[FEATURE_COLS].values
    y = df["target"].values
    model = _xgb()
    model.fit(X, y)
    return model


def get_shap_importance(model: XGBClassifier, df: pd.DataFrame) -> list[dict]:
    explainer = shap.TreeExplainer(model)
    shap_vals = explainer.shap_values(df[FEATURE_COLS].values)
    importance = np.abs(shap_vals).mean(axis=0)
    ranked = sorted(
        zip(FEATURE_COLS, importance.tolist()),
        key=lambda x: x[1], reverse=True
    )
    return [{"feature": f, "importance": round(v, 4)} for f, v in ranked]


def run_training(days: int = 365) -> dict:
    print(f"Fetching {days} days of data...")
    df = build_features(days=days)
    print(f"Dataset: {len(df)} rows, {df['date'].iloc[0]} → {df['date'].iloc[-1]}")

    print("Running walk-forward validation...")
    wf = walk_forward(df)
    for fold in wf["folds"]:
        print(f"  {fold['period_start']} → {fold['period_end']}  "
              f"acc={fold['accuracy']:.3f}  auc={fold['roc_auc']:.3f}")
    print(f"Mean accuracy: {wf['mean_accuracy']:.3f}  Mean AUC: {wf['mean_roc_auc']:.3f}")

    print("Training final model on all data...")
    model = train_final(df)
    shap_imp = get_shap_importance(model, df)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    metrics = {
        "walk_forward": wf,
        "shap_importance": shap_imp,
        "data_period": {
            "start": str(df["date"].iloc[0]),
            "end":   str(df["date"].iloc[-1]),
            "n_days": len(df),
        },
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"Model saved to {MODEL_PATH}")
    return metrics


def load_model() -> XGBClassifier:
    if not MODEL_PATH.exists():
        raise FileNotFoundError("Model not found. Run train.py first.")
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


if __name__ == "__main__":
    run_training(days=365)

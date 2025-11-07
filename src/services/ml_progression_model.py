# src/services/ml_progression_model.py
import os
import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "progression_lgbm.pkl")

def train_progression_model(data_csv: str = "src/data/user_progress.csv"):
    """
    사용자 누적 로그 기반 LightGBM 학습
    Columns: age, experience, goal, weight_kg, sets, reps, rest_sec, success_rate, fatigue, next_weight
    """
    df = pd.read_csv(data_csv)
    feature_cols = ["age", "experience", "goal", "weight_kg", "sets", "reps", "rest_sec", "success_rate", "fatigue"]
    df = df.dropna(subset=["next_weight"])

    X = pd.get_dummies(df[feature_cols], drop_first=True)
    y = df["next_weight"]

    model = LGBMRegressor(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.8,
        random_state=42
    )
    model.fit(X, y)
    joblib.dump(model, MODEL_PATH)
    print(f"✅ Model trained and saved at {MODEL_PATH}")


def predict_next_weight(entry: dict) -> float:
    """
    주어진 사용자/운동 상태(entry)로부터 다음 세트의 예상 무게 예측
    """
    if not os.path.exists(MODEL_PATH):
        return entry.get("weight_kg", 0)

    model = joblib.load(MODEL_PATH)
    df = pd.DataFrame([entry])
    df = pd.get_dummies(df)
    missing_cols = [c for c in model.feature_name_ if c not in df.columns]
    for col in missing_cols:
        df[col] = 0
    df = df[model.feature_name_]
    pred = model.predict(df)[0]
    return round(float(pred), 1)

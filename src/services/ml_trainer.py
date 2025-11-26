# src/services/ml_trainer.py
import lightgbm as lgb
import pandas as pd
import pickle
import os

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "exercise_model.pkl")

def train_exercise_model(df: pd.DataFrame):
    if df.empty:
        raise ValueError("훈련할 데이터가 없습니다")

    X = df[[
        "avg_weight", "avg_reps", "avg_sets",
        "volume", "exercise_count", "intensity"
    ]]
    y = df["feedback"]

    train_dataset = lgb.Dataset(X, label=y)

    params = {
        "objective": "binary",
        "learning_rate": 0.05,
        "max_depth": 5,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.7,
        "bagging_freq": 5,
        "metric": "binary_logloss",
    }

    model = lgb.train(params, train_dataset, num_boost_round=120)

    # 저장
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    return model

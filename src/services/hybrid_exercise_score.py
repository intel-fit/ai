# ============================================
# src/services/hybrid_exercise_score.py
# ============================================
import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.model_selection import train_test_split
from lightgbm import LGBMRegressor
from src import db

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "exercise_score_model.pkl")


# ------------------------------
# 1️⃣ Feature Extractor
# ------------------------------
def build_training_data(session):
    """user_exercise_recs + user info 기반 feature dataset 구성"""
    records = session.query(db.UserExerciseRec).filter(db.UserExerciseRec.feedback_score != None).all()
    data = []
    for r in records:
        user = session.query(db.User).filter(db.User.id == r.user_id).first()
        if not user:
            continue

        data.append({
            "age": user.age,
            "sex": 1 if user.sex.lower() == "male" else 0,
            "goal": goal_to_num(user.goal),
            "experience": exp_to_num(user.activity_level),
            "equip_count": len(r.exercises_json),
            "has_health_issue": int(bool(user.body_fat and user.body_fat > 30)),
            "num_exercises": len(r.exercises_json),
            "avg_sets": np.mean([e.get("sets", 0) for e in r.exercises_json]),
            "avg_reps": np.mean([e.get("reps", 0) for e in r.exercises_json]),
            "feedback_score": r.feedback_score
        })
    return pd.DataFrame(data)


def goal_to_num(goal):
    return {"hypertrophy": 0, "fat_loss": 1, "strength": 2, "functional": 3}.get(goal, 0)


def exp_to_num(x):
    if x < 1.3: return 0
    elif x < 1.5: return 1
    else: return 2


# ------------------------------
# 2️⃣ Model Training
# ------------------------------
def train_model(session):
    df = build_training_data(session)
    if df.empty:
        print("⚠️ Not enough feedback data yet to train model.")
        return None

    X = df.drop(columns=["feedback_score"])
    y = df["feedback_score"]
    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

    model = LGBMRegressor(n_estimators=300, learning_rate=0.05, num_leaves=31)
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], eval_metric="rmse", verbose=False)

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"✅ Model saved to {MODEL_PATH}")
    return model


# ------------------------------
# 3️⃣ Model Prediction
# ------------------------------
def predict_ai_score(user_ctx, plan_summary):
    """하루 루틴 기반 AI 점수 예측"""
    if not os.path.exists(MODEL_PATH):
        return 0.5  # 기본값

    model = joblib.load(MODEL_PATH)
    X = pd.DataFrame([{
        "age": user_ctx.age,
        "sex": 1 if user_ctx.sex.lower() == "male" else 0,
        "goal": goal_to_num(user_ctx.goal),
        "experience": exp_to_num(user_ctx.activity_level),
        "equip_count": len(user_ctx.available_equipment),
        "has_health_issue": int(bool(user_ctx.health_conditions)),
        "num_exercises": len(plan_summary),
        "avg_sets": np.mean([e["sets"] for e in plan_summary]),
        "avg_reps": np.mean([e["reps"] for e in plan_summary])
    }])
    return float(model.predict(X)[0])

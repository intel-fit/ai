# ===========================================
# src/services/train_exercise_model.py
# ===========================================
import os
import numpy as np
import pandas as pd
import lightgbm as lgb
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from src import db
from src.services.exercise_ml_features import build_exercise_feature_vector

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "exercise_model.pkl")


def load_training_data(session: Session):
    """
    DB에서 ExerciseSession + ExerciseSessionItem을 불러와서
    ML 학습용 dataset 생성
    """

    sessions = session.query(db.ExerciseSession).all()

    X_list = []
    y_list = []

    for sess in sessions:
        items = (
            session.query(db.ExerciseSessionItem)
            .filter(db.ExerciseSessionItem.session_id == sess.id)
            .all()
        )

        user_features = {
            "goal": "maintenance",
            "avg_intensity": sess.intensity_score or 0.5,
            "preferred_equips": [],
            "preferred_categories": [],
        }

        for it in items:
            # Feature vector 생성
            exercise_dict = {
                "exerciseId": it.exercise_id,
                "exercise_name": it.exercise_name,
                "equipments": "",
                "category": "",
                "targetMuscles": "",
                "risk_score": 0,
                "difficulty": "beginner"
            }

            X = build_exercise_feature_vector(user_features, exercise_dict)
            X_list.append(X)

            # 세션 피드백 → label 변환
            if sess.feedback == "like":
                y_list.append(1.0)
            elif sess.feedback == "dislike":
                y_list.append(0.0)
            else:
                y_list.append(0.5)

    return np.array(X_list), np.array(y_list)


def train_model(session: Session):
    """LightGBM 모델 훈련 및 저장"""
    X, y = load_training_data(session)

    if len(X) < 30:
        print("🚨 데이터가 너무 적어 학습 불가. 최소 30개 필요.")
        return

    dataset = lgb.Dataset(X, label=y)

    params = {
        "objective": "regression",
        "metric": "rmse",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 10,
    }

    model = lgb.train(params, dataset, num_boost_round=150)

    # 모델 저장
    import pickle
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    print(f"✅ 학습 완료 & 저장됨 → {MODEL_PATH}")


if __name__ == "__main__":
    engine = db.engine
    SessionLocal = db.SessionLocal
    session = SessionLocal()
    train_model(session)

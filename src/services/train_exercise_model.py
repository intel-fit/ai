import os
import numpy as np
import pandas as pd
import lightgbm as lgb
import pickle
from sqlalchemy.orm import Session
from src import db
from src.services.exercise_ml_features import build_exercise_feature_vector

# CSV 경로
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "exercise_enriched.csv")

# 모델 저장 경로
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "exercise_model.pkl")


# 1) CSV에서 운동 정보를 불러오는 함수
EX_DF = pd.read_csv(CSV_PATH)

def fetch_exercise_from_csv(ex_id: str):
    row = EX_DF[EX_DF["exerciseId"] == ex_id]
    if row.empty:
        return None
    
    r = row.iloc[0]

    return {
        "exerciseId": r["exerciseId"],
        "exercise_name": r["name"],
        "equipments": r["equipments"],
        "category": r["category"],
        "targetMuscles": r["targetMuscles"],
        "risk_score": r["risk_score"],
        "difficulty": r["difficulty"],
        "effectiveness": r["effectiveness"]
    }



# Label 구축 방식
def convert_feedback_to_label(item, session):
    """
    좋아요/싫어요 + 무게 피드백 + intensity를 label로 변환
    """
    base = 0.5

    # 세션의 전체 like/dislike
    if session.feedback == "like":
        base += 0.3
    elif session.feedback == "dislike":
        base -= 0.3

    # 개별 운동 피드백
    if item.feedback:
        if "like" in item.feedback:
            base += 0.3
        if "dislike" in item.feedback:
            base -= 0.3

        # 가벼워요 / 무거워요
        if "light" in item.feedback:
            base -= 0.1
        if "heavy" in item.feedback:
            base += 0.1

    # intensity 기반
    if session.intensity_score:
        base += (session.intensity_score - 0.5) * 0.2

    return max(0.0, min(1.0, base))



def load_training_data(session: Session):
    sessions = session.query(db.ExerciseSession).all()

    X_list = []
    y_list = []

    for sess in sessions:
        items = (
            session.query(db.ExerciseSessionItem)
            .filter(db.ExerciseSessionItem.session_id == sess.id)
            .all()
        )

        # 사용자 기본 feature (세션 기반)
        user_features = {
            "goal": sess.user.goal if sess.user and sess.user.goal else "maintenance",
            "avg_intensity": sess.intensity_score or 0.5,
            "preferred_equips": [],
            "preferred_categories": [],
        }

        for it in items:
            exercise_dict = fetch_exercise_from_csv(it.exercise_id)
            if exercise_dict is None:
                continue  # CSV에 없는 운동이면 skip

            # feature vector 생성 (추천엔진과 동일하게)
            fv = build_exercise_feature_vector(user_features, exercise_dict)
            X_list.append(fv)

            # label 생성
            label = convert_feedback_to_label(it, sess)
            y_list.append(label)

    return np.array(X_list), np.array(y_list)


def train_model(session: Session):
    X, y = load_training_data(session)

    print(f"Training samples: {len(X)}")

    if len(X) < 30:
        print("🚨 데이터가 너무 적어 학습 불가. 최소 30개 필요.")
        return

    params = {
        "objective": "regression",
        "metric": "rmse",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_data_in_leaf": 10,
    }

    dataset = lgb.Dataset(X, label=y)
    model = lgb.train(params, dataset, num_boost_round=150)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    print(f"✅ 학습 완료 & 저장됨 → {MODEL_PATH}")


if __name__ == "__main__":
    session = db.SessionLocal()
    train_model(session)

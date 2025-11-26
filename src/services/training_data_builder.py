# src/services/training_data_builder.py
from sqlalchemy.orm import Session
from src import db
from src.services.exercise_feedback_service import extract_features_from_history
import pandas as pd

def collect_training_data(session: Session):
    """
    ExerciseSession + ExerciseSessionItem 기반으로
    ML 학습용 DataFrame 생성
    """
    sessions = session.query(db.ExerciseSession).all()
    rows = []

    for sess in sessions:
        items = (
            session.query(db.ExerciseSessionItem)
            .filter(db.ExerciseSessionItem.session_id == sess.id)
            .all()
        )
        if not items:
            continue

        feat = extract_features_from_history([it.__dict__ for it in items])

        rows.append({
            "user_id": sess.user_id,
            "session_id": sess.id,
            "avg_weight": feat["avg_weight"],
            "avg_reps": feat["avg_reps"],
            "avg_sets": feat["avg_sets"],
            "volume": feat["volume"],
            "exercise_count": feat["exercise_count"],
            "intensity": sess.intensity_score or 0,
            "feedback": 1 if sess.feedback == "like" else 0,
        })

    return pd.DataFrame(rows)

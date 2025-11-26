# ===========================================
# src/services/exercise_ml_features.py
# ===========================================
import numpy as np

# 고정된 feature ordering (LightGBM 입력 순서)
FEATURE_KEYS = [
    "avg_intensity",
    "goal_code",
    "equip_match",
    "category_match",
    "muscle_overlap_score",
    "is_compound",
    "risk_score",
    "difficulty_code",
]

GOAL_MAP = {"bulk": 2, "fat_loss": 1, "maintenance": 0}

DIFFICULTY_MAP = {"beginner": 0, "intermediate": 1, "advanced": 2}


def build_exercise_feature_vector(user_features: dict, exercise: dict):
    """운동 + 사용자 프로필 → LightGBM 입력 feature 벡터"""

    # -------------------------------
    # 사용자 관련 feature
    # -------------------------------
    avg_intensity = user_features.get("avg_intensity", 0)

    goal_code = GOAL_MAP.get(user_features.get("goal", "maintenance"), 0)

    equip_match = 1 if exercise.get("equipments", "").lower() in user_features.get("preferred_equips", []) else 0
    category_match = 1 if (exercise.get("category") or "").lower() in user_features.get("preferred_categories", []) else 0

    # -------------------------------
    # 운동 metadata 기반 feature
    # -------------------------------
    target = (exercise.get("targetMuscles") or "").lower()
    focus_list = user_features.get("preferred_categories", [])

    # 운동 목표 부위가 유저 선호카테고리와 얼마나 겹치는지 (0~1)
    muscle_overlap_score = 1.0 if any(f in target for f in focus_list) else 0.0

    is_compound = 1 if (exercise.get("category") or "").lower() == "compound" else 0

    risk_score = float(exercise.get("risk_score", 0))

    difficulty_code = DIFFICULTY_MAP.get((exercise.get("difficulty", "")).lower(), 1)

    # -------------------------------
    # 벡터 생성
    # -------------------------------
    values = [
        avg_intensity,
        goal_code,
        equip_match,
        category_match,
        muscle_overlap_score,
        is_compound,
        risk_score,
        difficulty_code,
    ]

    return np.array(values, dtype=float)

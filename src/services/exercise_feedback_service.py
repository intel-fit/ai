# ===========================================
# src/services/exercise_feedback_service.py
# ===========================================
import collections
from sqlalchemy.orm import Session
import numpy as np
from src import db


# 운동 → 그룹 매핑(예시)
EXERCISE_GROUP_MAP = {
    "chest": ["bench", "press", "fly"],
    "back": ["row", "lat", "pull"],
    "legs": ["squat", "leg", "lunge"],
    "glutes": ["hip", "glute"],
    "shoulders": ["shoulder", "raise"],
    "biceps": ["curl"],
    "triceps": ["extension", "dip"],
    "core": ["crunch", "plank", "leg raise"],
}


def _infer_group(ex_name: str):
    """운동 이름에서 어느 부위인지 자동 추론"""
    name = ex_name.lower()
    for group, kws in EXERCISE_GROUP_MAP.items():
        if any(k in name for k in kws):
            return group
    return None


# ===========================================
# MAIN: 유저 피드백 프로필 생성
# ===========================================
from src import db
import collections
import numpy as np
from sqlalchemy.orm import Session

def get_user_feedback_profile(user_id: str, session: Session):
    """
    유저 전체 운동 피드백을 결합하여
    - 운동별 like/dislike
    - 운동별 heavy/light (무게 조정용)
    - 기존 ExerciseSession 기반 가중치
    - 그룹/장비 기반 선호
    - ML feature

    까지 포함한 하이브리드 피드백을 생성한다.
    """

    # ==========================================
    # ① NEW: exercise_feedback 테이블 기반 운동별 피드백 가져오기
    # ==========================================
    fb_rows = (
        session.query(db.ExerciseFeedback)
        .filter(db.ExerciseFeedback.user_id == user_id)
        .order_by(db.ExerciseFeedback.created_at.desc())
        .all()
    )

    like_exercises = set()
    dislike_exercises = set()
    heavy_feedback = set()
    light_feedback = set()

    for r in fb_rows:
        if r.feedback_type == "like":
            like_exercises.add(r.exercise_id)
        elif r.feedback_type == "dislike":
            dislike_exercises.add(r.exercise_id)
        elif r.feedback_type == "heavy":
            heavy_feedback.add(r.exercise_id)
        elif r.feedback_type == "light":
            light_feedback.add(r.exercise_id)

    # ==========================================
    # ② 기존 ExerciseSession 기반 로직(그대로 유지)
    # ==========================================
    sessions = (
        session.query(db.ExerciseSession)
        .filter(db.ExerciseSession.user_id == user_id)
        .order_by(db.ExerciseSession.created_at.desc())
        .all()
    )

    # 세션이 하나도 없으면 기본값 반환
    if not sessions and not fb_rows:
        return {
            "weights": {},
            "like_exercises": set(),
            "dislike_exercises": set(),
            "heavy_feedback": set(),
            "light_feedback": set(),
            "like_groups": set(),
            "dislike_groups": set(),
            "like_equip": set(),
            "dislike_equip": set(),
            "ml_features": {
                "goal": "maintenance",
                "avg_intensity": 0.5,
                "preferred_equips": [],
                "preferred_categories": []
            }
        }

    weights = collections.defaultdict(lambda: 1.0)
    like_groups = collections.Counter()
    dislike_groups = collections.Counter()
    like_equips = collections.Counter()
    dislike_equips = collections.Counter()
    intensities = []

    # 기존 세션 기반 가중치 계산
    for sess in sessions:
        items = (
            session.query(db.ExerciseSessionItem)
            .filter(db.ExerciseSessionItem.session_id == sess.id)
            .all()
        )

        # 세션 피드백(전체 운동에 적용되는 가중치)
        if sess.feedback == "like":
            factor = 1.20
        elif sess.feedback == "dislike":
            factor = 0.80
        else:
            factor = 1.0

        if sess.intensity_score:
            intensities.append(sess.intensity_score)

        for it in items:
            ex_name = it.exercise_name
            weights[ex_name] *= factor

            # 운동 그룹 추론 (기존 로직 그대로)
            g = _infer_group(ex_name)
            if g:
                if factor > 1.0:
                    like_groups[g] += 1
                elif factor < 1.0:
                    dislike_groups[g] += 1

            equip = (it.exercise_name or "").lower()
            if factor > 1.0:
                like_equips[equip] += 1
            elif factor < 1.0:
                dislike_equips[equip] += 1

    # ==========================================
    # ③ Machine Learning feature (기존 유지)
    # ==========================================
    avg_intensity = float(np.mean(intensities)) if intensities else 0.5

    preferred_equips = [e for e, c in like_equips.items() if c >= 1]
    preferred_categories = list(like_groups.keys())

    ml_features = {
        "goal": "maintenance", 
        "avg_intensity": avg_intensity,
        "preferred_equips": preferred_equips,
        "preferred_categories": preferred_categories
    }

    # ==========================================
    # ④ 최종 패키징: 기존 + NEW
    # ==========================================
    return {
        # 기존
        "weights": dict(weights),
        "like_groups": set(like_groups.keys()),
        "dislike_groups": set(dislike_groups.keys()),
        "like_equip": set(preferred_equips),
        "dislike_equip": set([e for e, c in dislike_equips.items() if c >= 1]),
        "ml_features": ml_features,

        # NEW (운동별 단위 피드백)
        "like_exercises": like_exercises,
        "dislike_exercises": dislike_exercises,
        "heavy_feedback": heavy_feedback,
        "light_feedback": light_feedback,
    }





def extract_features_from_history(session_items: list[dict]) -> dict:
    """
    ExerciseSessionItem 목록을 feature vector로 변환
    ML 모델 입력으로 사용됨
    """
    if not session_items:
        return {
            "avg_weight": 0,
            "avg_reps": 0,
            "avg_sets": 0,
            "volume": 0,
            "exercise_count": 0,
        }

    total_weight = sum((item.get("weight_kg") or 0) for item in session_items)
    total_reps = sum((item.get("reps") or 0) for item in session_items)
    total_sets = sum((item.get("sets") or 0) for item in session_items)

    # 총 볼륨 = weight * reps * sets
    total_volume = sum(
        (item.get("weight_kg") or 0)
        * (item.get("reps") or 0)
        * (item.get("sets") or 0)
        for item in session_items
    )

    return {
        "avg_weight": total_weight / len(session_items),
        "avg_reps": total_reps / len(session_items),
        "avg_sets": total_sets / len(session_items),
        "volume": total_volume,
        "exercise_count": len(session_items),
    }


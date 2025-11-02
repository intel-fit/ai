# src/services/health_score.py
from datetime import date
from sqlalchemy.orm import Session
from src import db

def compute_daily_score(user_id: str, target_date: date, session: Session):
    """해당 날짜의 DailyNutritionSummary / DailyExerciseSummary 기반 점수 계산"""
    nut = (
        session.query(db.DailyNutritionSummary)
        .filter_by(user_id=user_id, date=target_date)
        .first()
    )
    ex = (
        session.query(db.DailyExerciseSummary)
        .filter_by(user_id=user_id, date=target_date)
        .first()
    )

    if not nut or not ex:
        return None

    # -------------------------------
    # 1️⃣ 영양 점수 계산 (0~100)
    # -------------------------------
    # 기준치: 단백질 > 80g, 가공식품 < 30%, 나트륨 < 2300mg
    score_protein = min(100, nut.protein_g / 80 * 100)
    score_process = max(0, 100 - nut.processed_ratio * 200)
    score_sodium  = max(0, 100 - (nut.sodium_mg / 2300) * 30)
    nutrition_score = (score_protein * 0.5 + score_process * 0.3 + score_sodium * 0.2)

    # -------------------------------
    # 2️⃣ 운동 점수 계산 (0~100)
    # -------------------------------
    # 기준치: 60분 운동, 강도 3~5
    score_dur = min(100, ex.duration_min / 60 * 100)
    score_int = min(100, ex.avg_intensity / 5 * 100)
    exercise_score = (score_dur * 0.7 + score_int * 0.3)

    # -------------------------------
    # 3️⃣ 밸런스 점수 (섭취칼로리 vs 소모칼로리)
    # -------------------------------
    kcal_diff = abs(nut.kcal - ex.calories_burned)
    if kcal_diff < 300:
        balance_score = 100
    elif kcal_diff < 600:
        balance_score = 80
    elif kcal_diff < 900:
        balance_score = 60
    else:
        balance_score = 40

    total_score = round((nutrition_score * 0.5 + exercise_score * 0.3 + balance_score * 0.2), 1)

    # -------------------------------
    # DB 저장 (upsert)
    # -------------------------------
    hs = (
        session.query(db.DailyHealthScore)
        .filter_by(user_id=user_id, date=target_date)
        .first()
    )
    if not hs:
        hs = db.DailyHealthScore(user_id=user_id, date=target_date)
        session.add(hs)

    hs.nutrition_score = round(nutrition_score, 1)
    hs.exercise_score = round(exercise_score, 1)
    hs.balance_score = round(balance_score, 1)
    hs.total_score = total_score
    session.commit()

    return {
        "date": str(target_date),
        "nutrition_score": hs.nutrition_score,
        "exercise_score": hs.exercise_score,
        "balance_score": hs.balance_score,
        "total_score": hs.total_score
    }

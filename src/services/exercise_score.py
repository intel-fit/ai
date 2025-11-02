# src/services/exercise_score.py
# =======================================
# 일/주/월 운동 점수화 & 피드백 생성 모듈
# =======================================

from datetime import date, timedelta
from sqlalchemy import text
from src import db

# ------------------------------
# 1) 하루 운동 점수 계산
# ------------------------------
def calculate_daily_score(user_id: str, ref_date: date | None = None):
    """
    하루 운동 점수를 계산.
    점수는 100점 만점 기준.
    - 운동 강도(intensity)
    - 운동 시간(duration_min)
    - 목표 대비 운동 칼로리
    - 운동 빈도 보너스 (최근 7일)
    """
    ref_date = ref_date or date.today()

    with db.engine.connect() as conn:
        logs = conn.execute(
            text("SELECT * FROM exercise_log WHERE user_id=:uid AND date=:d"),
            {"uid": user_id, "d": ref_date}
        ).mappings().all()

        if not logs:
            return {"date": ref_date, "score": 0, "feedback": "운동 기록이 없습니다."}

        total_duration = sum(l["duration_min"] for l in logs)
        total_cal = sum(l["calories_burned"] for l in logs)
        avg_intensity = sum(l.get("intensity", 3) for l in logs) / len(logs)

        # 간단한 점수 공식
        duration_score = min(total_duration / 60 * 40, 40)  # 60분=40점
        cal_score = min(total_cal / 400 * 40, 40)            # 400kcal=40점
        intensity_score = (avg_intensity / 5) * 20           # 강도 1~5
        total_score = round(duration_score + cal_score + intensity_score)

        feedback = []
        if total_duration < 30:
            feedback.append("운동 시간이 조금 짧아요 ⏱️")
        if avg_intensity < 3:
            feedback.append("조금 더 강도 있게 해볼까요? 💪")
        if total_cal > 400:
            feedback.append("아주 훌륭한 운동량이에요🔥")

        return {
            "date": str(ref_date),
            "score": total_score,
            "summary": {
                "duration_min": total_duration,
                "calories_burned": total_cal,
                "avg_intensity": round(avg_intensity, 2),
            },
            "feedback": feedback or ["좋아요! 꾸준히 유지해봐요 👍"],
        }

# ------------------------------
# 2) 주간/월간 점수 요약
# ------------------------------
def summarize_period_scores(user_id: str, mode: str = "week"):
    """
    mode: 'week' 또는 'month'
    """
    today = date.today()
    start_date = today - timedelta(days=7 if mode == "week" else 30)

    with db.engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT date, duration_min, calories_burned, intensity
                FROM exercise_log
                WHERE user_id=:uid AND date BETWEEN :s AND :e
            """),
            {"uid": user_id, "s": start_date, "e": today}
        ).mappings().all()

    if not rows:
        return {"period": mode, "average_score": 0, "days_active": 0}

    # 일별 점수 계산
    daily_scores = []
    for r in rows:
        score = min(r["duration_min"]/60*40 + r["calories_burned"]/400*40 + (r.get("intensity",3)/5)*20, 100)
        daily_scores.append(score)

    avg_score = round(sum(daily_scores) / len(daily_scores))
    active_days = len(set(r["date"] for r in rows))

    feedback = []
    if avg_score >= 80:
        feedback.append("훌륭한 한 주였습니다 💪")
    elif avg_score >= 60:
        feedback.append("꾸준함이 돋보여요 😊")
    else:
        feedback.append("조금 더 자주 움직여볼까요? 🚶‍♂️")

    return {
        "period": mode,
        "start_date": str(start_date),
        "end_date": str(today),
        "average_score": avg_score,
        "days_active": active_days,
        "feedback": feedback
    }

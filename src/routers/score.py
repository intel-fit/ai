# src/routers/score.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, timedelta
from src import db

router = APIRouter(tags=["Health Score JSON"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ------------------------------------------------------------
# 1️⃣ 최근 7일 점수 JSON
# ------------------------------------------------------------
@router.get("/score/daily/{user_id}")
def get_daily_scores(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    start = today - timedelta(days=6)

    rows = (
        session.query(db.DailyHealthScore)
        .filter(db.DailyHealthScore.user_id == user_id)
        .filter(db.DailyHealthScore.date >= start)
        .order_by(db.DailyHealthScore.date)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail="No daily score data found")

    return {
        "user_id": user_id,
        "period": f"{start} ~ {today}",
        "days": len(rows),
        "daily_scores": [
            {
                "date": r.date.isoformat(),
                "nutrition": r.nutrition_score,
                "exercise": r.exercise_score,
                "balance": r.balance_score,
                "total": r.total_score,
            }
            for r in rows
        ],
    }


# ------------------------------------------------------------
# 2️⃣ 최근 4주 (월~일 기준) 주간 평균 JSON
# ------------------------------------------------------------
@router.get("/score/weekly/{user_id}")
def get_weekly_score(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    monday = today - timedelta(days=today.weekday())  # 이번주 월요일

    week_starts = [monday - timedelta(days=7 * i) for i in range(4)]
    week_starts.sort()

    weekly_result = []

    for ws in week_starts:
        we = ws + timedelta(days=6)
        rows = (
            session.query(db.DailyHealthScore)
            .filter(db.DailyHealthScore.user_id == user_id)
            .filter(db.DailyHealthScore.date >= ws)
            .filter(db.DailyHealthScore.date <= we)
            .order_by(db.DailyHealthScore.date)
            .all()
        )

        if not rows:
            continue

        def avg(lst): return sum(lst) / len(lst) if lst else 0

        weekly_result.append({
            "week_start": ws.isoformat(),
            "week_end": we.isoformat(),
            "nutrition_avg": round(avg([r.nutrition_score for r in rows]), 2),
            "exercise_avg": round(avg([r.exercise_score for r in rows]), 2),
            "balance_avg": round(avg([r.balance_score for r in rows]), 2),
            "total_avg": round(avg([r.total_score for r in rows]), 2),
        })

    return {
        "user_id": user_id,
        "weeks_count": len(weekly_result),
        "weekly_scores": weekly_result,
    }


# ------------------------------------------------------------
# 3️⃣ 최근 3개월 월간 평균 JSON
# ------------------------------------------------------------
@router.get("/score/monthly/{user_id}")
def get_monthly_score(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    this_month_start = today.replace(day=1)

    def prev_month_start(d: date) -> date:
        last_day_prev = d - timedelta(days=1)
        return last_day_prev.replace(day=1)

    month_starts = [this_month_start]
    for _ in range(2):
        month_starts.append(prev_month_start(month_starts[-1]))
    month_starts.sort()

    monthly_result = []

    for ms in month_starts:
        next_month = (ms.replace(day=28) + timedelta(days=4)).replace(day=1)
        me = next_month - timedelta(days=1)

        rows = (
            session.query(db.DailyHealthScore)
            .filter(db.DailyHealthScore.user_id == user_id)
            .filter(db.DailyHealthScore.date >= ms)
            .filter(db.DailyHealthScore.date <= me)
            .order_by(db.DailyHealthScore.date)
            .all()
        )

        if not rows:
            continue

        def avg(lst): return sum(lst) / len(lst) if lst else 0

        monthly_result.append({
            "month": ms.strftime("%Y-%m"),
            "period": f"{ms.isoformat()} ~ {me.isoformat()}",
            "nutrition_avg": round(avg([r.nutrition_score for r in rows]), 2),
            "exercise_avg": round(avg([r.exercise_score for r in rows]), 2),
            "balance_avg": round(avg([r.balance_score for r in rows]), 2),
            "total_avg": round(avg([r.total_score for r in rows]), 2),
        })

    return {
        "user_id": user_id,
        "months_count": len(monthly_result),
        "monthly_scores": monthly_result,
    }

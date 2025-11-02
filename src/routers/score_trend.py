# src/routers/score_trend.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, timedelta
from fastapi.responses import StreamingResponse
import matplotlib.pyplot as plt
import io
from src import db

router = APIRouter(tags=["Health Score Trend"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ------------------------------------------------------------
# 1️⃣ 일별 점수 트렌드 (최근 14일)
# ------------------------------------------------------------
@router.get("/score/trend/daily/{user_id}")
def daily_score_trend(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    start = today - timedelta(days=13)
    rows = (
        session.query(db.DailyHealthScore)
        .filter(db.DailyHealthScore.user_id == user_id)
        .filter(db.DailyHealthScore.date >= start)
        .order_by(db.DailyHealthScore.date)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No daily score data found")

    days = [r.date for r in rows]
    scores = [r.total_score for r in rows]

    plt.figure(figsize=(9, 5))
    plt.plot(days, scores, marker='o', color='mediumseagreen', linewidth=2)
    plt.title(f"{user_id} — 최근 14일 건강 점수 추이")
    plt.xlabel("날짜")
    plt.ylabel("점수 (0~100)")
    plt.grid(alpha=0.3)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return StreamingResponse(buf, media_type="image/png")


# ------------------------------------------------------------
# 2️⃣ 주별 평균 점수 트렌드 (최근 8주)
# ------------------------------------------------------------
@router.get("/score/trend/weekly/{user_id}")
def weekly_score_trend(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    start = today - timedelta(weeks=8)
    rows = (
        session.query(db.DailyHealthScore)
        .filter(db.DailyHealthScore.user_id == user_id)
        .filter(db.DailyHealthScore.date >= start)
        .order_by(db.DailyHealthScore.date)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No weekly score data found")

    # 주차별 평균
    week_scores = {}
    for r in rows:
        year, week, _ = r.date.isocalendar()
        key = f"{year}-W{week}"
        week_scores.setdefault(key, []).append(r.total_score)

    labels = list(week_scores.keys())
    avgs = [sum(v) / len(v) for v in week_scores.values()]

    plt.figure(figsize=(9, 5))
    plt.plot(labels, avgs, marker='o', color='steelblue', linewidth=2)
    plt.title(f"{user_id} — 최근 8주 평균 건강 점수 추이")
    plt.xlabel("주차")
    plt.ylabel("평균 점수 (0~100)")
    plt.xticks(rotation=45)
    plt.grid(alpha=0.3)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return StreamingResponse(buf, media_type="image/png")


# ------------------------------------------------------------
# 3️⃣ 월별 평균 점수 트렌드 (최근 6개월)
# ------------------------------------------------------------
@router.get("/score/trend/monthly/{user_id}")
def monthly_score_trend(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    start = today.replace(day=1) - timedelta(days=180)  # 최근 6개월
    rows = (
        session.query(db.DailyHealthScore)
        .filter(db.DailyHealthScore.user_id == user_id)
        .filter(db.DailyHealthScore.date >= start)
        .order_by(db.DailyHealthScore.date)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No monthly score data found")

    # 월별 평균
    month_scores = {}
    for r in rows:
        key = f"{r.date.year}-{r.date.month:02d}"
        month_scores.setdefault(key, []).append(r.total_score)

    labels = list(month_scores.keys())
    avgs = [sum(v) / len(v) for v in month_scores.values()]

    plt.figure(figsize=(9, 5))
    plt.plot(labels, avgs, marker='o', color='darkorange', linewidth=2)
    plt.title(f"{user_id} — 최근 6개월 건강 점수 추이")
    plt.xlabel("월")
    plt.ylabel("평균 점수 (0~100)")
    plt.grid(alpha=0.3)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return StreamingResponse(buf, media_type="image/png")

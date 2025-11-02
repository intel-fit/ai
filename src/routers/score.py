# src/routers/score.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, timedelta
from src import db

router = APIRouter(tags=["Health Score"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

@router.get("/score/daily/{user_id}")
def get_daily_scores(user_id: str, session: Session = Depends(get_db)):
    rows = (
        session.query(db.DailyHealthScore)
        .filter_by(user_id=user_id)
        .order_by(db.DailyHealthScore.date)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No scores found")
    return [
        {
            "date": r.date.isoformat(),
            "nutrition": r.nutrition_score,
            "exercise": r.exercise_score,
            "balance": r.balance_score,
            "total": r.total_score,
        }
        for r in rows
    ]

@router.get("/score/weekly/{user_id}")
def get_weekly_score(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    start = today - timedelta(days=6)
    rows = (
        session.query(db.DailyHealthScore)
        .filter(db.DailyHealthScore.user_id == user_id)
        .filter(db.DailyHealthScore.date >= start)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No data in last 7 days")

    avg_score = sum(r.total_score for r in rows) / len(rows)
    return {
        "user_id": user_id,
        "period": f"{start}~{today}",
        "days": len(rows),
        "average_total_score": round(avg_score, 1),
        "details": [
            {"date": r.date.isoformat(), "score": r.total_score} for r in rows
        ],
    }

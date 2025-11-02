# src/routers/coach.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src import db
from src.services.coach import build_weekly_coach_report
from datetime import date
import json

router = APIRouter(tags=["Coach Feedback"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

@router.get("/coach/weekly_report/{user_id}", response_model=dict)
def get_weekly_coach_report(user_id: str, session: Session = Depends(get_db)):
    user = session.query(db.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    report = build_weekly_coach_report(user_id, session)

    # DB 저장 (코치노트 기록)
    note = db.CoachNote(
        user_id=user_id,
        period=f"weekly:{date.today().isocalendar()[1]}",
        summary=report["summary"],
        action_items=json.dumps(report["action_items"], ensure_ascii=False)
    )
    session.add(note)
    session.commit()

    return report

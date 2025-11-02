# ============================================
# src/routers/exercise_feedback.py
# ============================================
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
from uuid import uuid4
from src import db
from src.schemas import ExerciseFeedbackCreate, ExerciseFeedbackUpdate

router = APIRouter(prefix="/exercise_feedback", tags=["Exercise Feedback"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ------------------------------
# 1️⃣ AI가 생성한 루틴 저장
# ------------------------------
@router.post("/log")
def log_exercise_plan(payload: ExerciseFeedbackCreate, session: Session = Depends(get_db)):
    record = db.UserExerciseRec(
        id=str(uuid4()),
        user_id=payload.user_id,
        date=payload.date,
        day=payload.day,
        focus=payload.focus,
        exercises_json=payload.exercises,
        created_at=date.today()
    )
    session.add(record)
    session.commit()
    return {"message": "✅ 운동 루틴 기록 완료", "rec_id": record.id}


# ------------------------------
# 2️⃣ 사용자 피드백 반영
# ------------------------------
@router.put("/{rec_id}")
def update_feedback(rec_id: str, payload: ExerciseFeedbackUpdate, session: Session = Depends(get_db)):
    rec = session.query(db.UserExerciseRec).filter(db.UserExerciseRec.id == rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")

    if payload.feedback_score is not None:
        rec.feedback_score = payload.feedback_score
    if payload.completed is not None:
        rec.completed = payload.completed

    session.commit()
    return {"message": "✅ 피드백이 반영되었습니다", "rec_id": rec.id}

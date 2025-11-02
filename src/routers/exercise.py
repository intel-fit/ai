# src/routers/exercise.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src import db
from src.schemas import ExerciseLogCreate, ExerciseLogOut
# 맨 위에 추가
from datetime import date as _date
from src.services.summary import recompute_daily_summaries



router = APIRouter(tags=["Exercise"])



def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()
@router.post("/log", response_model=ExerciseLogOut)
def create_exercise_log(log: ExerciseLogCreate, session: Session = Depends(get_db)):
    user = session.query(db.User).get(log.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db_log = db.ExerciseLog(**log.dict())
    session.add(db_log)
    session.commit()
    session.refresh(db_log)

    # ✅ 요약 재계산 훅
    recompute_daily_summaries(log.user_id, log.date, session)

    return db_log


@router.post("/log", response_model=ExerciseLogOut)
def create_exercise_log(log: ExerciseLogCreate, session: Session = Depends(get_db)):
    user = session.query(db.User).get(log.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db_log = db.ExerciseLog(**log.dict())
    session.add(db_log)
    session.commit()
    session.refresh(db_log)
    return db_log

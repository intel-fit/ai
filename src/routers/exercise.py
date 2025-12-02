# src/routers/exercise.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src import db
from src.schemas import ExerciseLogCreate, ExerciseLogOut
# 맨 위에 추가
from datetime import date as _date
from src.services.summary import recompute_daily_summaries
from src.services.nutrition import update_daily_goal_after_exercise



router = APIRouter(tags=["Exercise"])



def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.post("/log", response_model=ExerciseLogOut)
def create_exercise_log(log: ExerciseLogCreate, session: Session = Depends(get_db)):
    # 1) 유저 확인
    user = session.query(db.User).get(log.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 2) 로그 저장
    db_log = db.ExerciseLog(**log.dict())
    session.add(db_log)
    session.commit()
    session.refresh(db_log)

    # 3) 요약 재계산
    recompute_daily_summaries(log.user_id, log.date, session)

    # 4) 목표 칼로리 자동 업데이트 (자동 일 때만)
    update_daily_goal_after_exercise(log.user_id, log.date, session)

    return db_log


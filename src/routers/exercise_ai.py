# src/routers/exercise_ai.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.schemas import UserExerciseContext
from src.routers.exercise_feedback import get_db
from src.services.exercise_planner import generate_week_plan, generate_daily_plan

router = APIRouter(tags=["AI Exercise Planner"])

# ===============================
# 1) 주간(Weekly) 추천
# ===============================
@router.post("/ai/exercise_plan")
def ai_exercise_plan(
    ctx: UserExerciseContext,
    session: Session = Depends(get_db)
):
    """AI 기반 사용자 맞춤 주간 운동 루틴 추천"""
    return generate_week_plan(ctx, session)


# ===============================
# 2) 일일(Daily) 추천  ⭐ NEW
# ===============================
@router.post("/ai/exercise_plan/daily")
def ai_exercise_plan_daily(
    ctx: UserExerciseContext,
    session: Session = Depends(get_db)
):
    """AI 기반 사용자 맞춤 일일 운동 추천"""
    return generate_daily_plan(ctx, session)

# src/routers/exercise_ai.py
from fastapi import APIRouter
from src.schemas import UserExerciseContext
from src.services.exercise_planner import generate_week_plan

router = APIRouter(tags=["AI Exercise Planner"])

@router.post("/ai/exercise_plan")
def ai_exercise_plan(ctx: UserExerciseContext):
    """AI 기반 사용자 맞춤 운동 루틴 추천"""
    return generate_week_plan(ctx)

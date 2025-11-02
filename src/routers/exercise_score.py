# src/routers/exercise_score.py
from fastapi import APIRouter, Query
from datetime import date
from src.services.exercise_score import calculate_daily_score, summarize_period_scores

router = APIRouter(tags=["Exercise Score"])

@router.get("/exercise/score/daily")
def get_daily_exercise_score(user_id: str, ref_date: date | None = None):
    """특정 날짜의 운동 점수 계산"""
    return calculate_daily_score(user_id, ref_date)

@router.get("/exercise/score/summary")
def get_summary_exercise_score(user_id: str, mode: str = Query("week", regex="^(week|month)$")):
    """주간 또는 월간 운동 점수 요약"""
    return summarize_period_scores(user_id, mode)

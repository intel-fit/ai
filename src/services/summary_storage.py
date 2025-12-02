from datetime import date, timedelta
from sqlalchemy.orm import Session
from src.db import (
    WeeklyNutritionSummary, WeeklyExerciseSummary,
    MonthlyNutritionSummary, MonthlyExerciseSummary
)
from sqlalchemy.exc import IntegrityError


def save_weekly_nutrition(session: Session, user_id: str, ws: date, we: date, data):
    """
    data: {kcal, protein, fat, carb}
    """
    obj = WeeklyNutritionSummary(
        user_id=user_id,
        week_start=ws,
        week_end=we,
        avg_kcal=data["kcal"],
        avg_protein=data["protein"],
        avg_fat=data["fat"],
        avg_carb=data["carb"],
    )
    session.add(obj)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()


def save_weekly_exercise(session: Session, user_id: str, ws: date, we: date, data):
    obj = WeeklyExerciseSummary(
        user_id=user_id,
        week_start=ws,
        week_end=we,
        avg_duration=data["duration_min"],
        avg_calories_burned=data["calories_burned"],
        avg_intensity=data["avg_intensity"],
    )
    session.add(obj)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()


def save_monthly_nutrition(session: Session, user_id: str, month: str, data):
    obj = MonthlyNutritionSummary(
        user_id=user_id,
        month=month,
        avg_kcal=data["kcal"],
        avg_protein=data["protein"],
        avg_fat=data["fat"],
        avg_carb=data["carb"],
    )
    session.add(obj)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()

def save_monthly_exercise(session: Session, user_id: str, month: str, data):
    obj = MonthlyExerciseSummary(
        user_id=user_id,
        month=month,
        avg_duration=data["duration_min"],
        avg_calories_burned=data["calories_burned"],
        avg_intensity=data["avg_intensity"],
    )
    session.add(obj)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
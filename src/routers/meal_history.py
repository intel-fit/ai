# src/routers/meal_history.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
from src import db
from src.schemas import UserMealHistoryOut

router = APIRouter(prefix="/meal_history", tags=["Meal History"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# -------------------------------
# POST - 식단 로그 저장 (한 끼)
# -------------------------------
@router.post("/{user_id}", response_model=UserMealHistoryOut)
def save_meal_history(user_id: str, payload: dict, session: Session = Depends(get_db)):

    # payload 구조:
    # {
    #   "date": "2025-12-01",
    #   "meal_name": "아침",
    #   "items": [
    #       {"food_id": 123, "food_name": "...", "amount_g": 100, ...}
    #   ]
    # }

    hist = db.UserMealHistory(
        user_id=user_id,
        date=date.fromisoformat(payload["date"]),
        meal_name=payload["meal_name"],
        total_calories=payload.get("total_calories"),
        total_protein=payload.get("total_protein"),
        total_carbs=payload.get("total_carbs"),
        total_fat=payload.get("total_fat"),
    )
    session.add(hist)
    session.commit()
    session.refresh(hist)

    # 음식 로그 저장
    for item in payload.get("items", []):
        entry = db.UserMealHistoryItem(
            history_id=hist.id,
            food_id=item.get("food_id"),
            food_name=item["food_name"],
            amount_g=item["amount_g"],
            calories=item.get("calories"),
            protein=item.get("protein"),
            fat=item.get("fat"),
            carbs=item.get("carbs"),
        )
        session.add(entry)

    session.commit()
    session.refresh(hist)
    return hist


# -------------------------------
# GET - 특정 유저 전체 식단 로그 조회
# -------------------------------
@router.get("/{user_id}", response_model=list[UserMealHistoryOut])
def get_all_history(user_id: str, session: Session = Depends(get_db)):
    logs = (
        session.query(db.UserMealHistory)
        .filter_by(user_id=user_id)
        .order_by(db.UserMealHistory.date.desc())
        .all()
    )
    return logs


# -------------------------------
# GET - 최근 N일 로그 조회
# -------------------------------
@router.get("/{user_id}/recent/{days}", response_model=list[UserMealHistoryOut])
def get_recent_history(user_id: str, days: int, session: Session = Depends(get_db)):
    cutoff = date.today().toordinal() - days
    logs = (
        session.query(db.UserMealHistory)
        .filter(db.UserMealHistory.user_id == user_id)
        .filter(db.UserMealHistory.date >= date.fromordinal(cutoff))
        .order_by(db.UserMealHistory.date.desc())
        .all()
    )
    return logs

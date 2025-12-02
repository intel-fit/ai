# src/routers/exclusions.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src import db
from src.schemas import FoodExclusionOut

router = APIRouter(prefix="/exclusions", tags=["Food Exclusions"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# -------------------------------
# GET - 유저 제외 음식 조회
# -------------------------------
@router.get("/{user_id}", response_model=list[FoodExclusionOut])
def get_exclusions(user_id: str, session: Session = Depends(get_db)):
    return (
        session.query(db.UserFoodExclusion)
        .filter_by(user_id=user_id)
        .all()
    )


# -------------------------------
# POST - 제외 음식 등록
# -------------------------------
@router.post("/{user_id}", response_model=FoodExclusionOut)
def add_exclusion(user_id: str, food_name: str, reason: str = "taste", session: Session = Depends(get_db)):
    exclusion = db.UserFoodExclusion(
        user_id=user_id,
        food_name=food_name,
        reason=reason,
    )
    session.add(exclusion)
    session.commit()
    session.refresh(exclusion)
    return exclusion


# -------------------------------
# DELETE - 제외 음식 삭제
# -------------------------------
@router.delete("/{exclusion_id}")
def remove_exclusion(exclusion_id: int, session: Session = Depends(get_db)):
    exclusion = session.query(db.UserFoodExclusion).filter_by(id=exclusion_id).first()
    if not exclusion:
        raise HTTPException(status_code=404, detail="Exclusion not found")

    session.delete(exclusion)
    session.commit()
    return {"status": "deleted"}

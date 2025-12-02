# src/routers/preferences.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src import db
from src.schemas import FoodPreferenceOut

router = APIRouter(prefix="/preferences", tags=["Food Preferences"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# -------------------------------
# GET - 유저 선호 음식 리스트
# -------------------------------
@router.get("/{user_id}", response_model=list[FoodPreferenceOut])
def get_preferences(user_id: str, session: Session = Depends(get_db)):
    prefs = session.query(db.UserFoodPreference).filter_by(user_id=user_id).all()
    return prefs


# -------------------------------
# POST - 선호 음식 추가/업데이트 (score 자동 증가)
# -------------------------------
@router.post("/{user_id}", response_model=FoodPreferenceOut)
def add_or_update_preference(user_id: str, food_name: str, session: Session = Depends(get_db)):
    pref = (
        session.query(db.UserFoodPreference)
        .filter_by(user_id=user_id, food_name=food_name)
        .first()
    )

    if pref:
        pref.score += 1.0        # 선호 점수 증가
    else:
        pref = db.UserFoodPreference(
            user_id=user_id,
            food_name=food_name,
            score=1.0,
            source="manual",
        )
        session.add(pref)

    session.commit()
    session.refresh(pref)
    return pref


# -------------------------------
# DELETE - 특정 선호 음식 제거
# -------------------------------
@router.delete("/{pref_id}")
def remove_preference(pref_id: int, session: Session = Depends(get_db)):
    pref = session.query(db.UserFoodPreference).filter_by(id=pref_id).first()

    if not pref:
        raise HTTPException(status_code=404, detail="Preference not found")

    session.delete(pref)
    session.commit()
    return {"status": "deleted"}

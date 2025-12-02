# src/routers/profile.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src import db
from src.schemas import UserProfileBase, UserProfileOut
import json

router = APIRouter(prefix="/profile", tags=["User Profile"])


def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# -------------------------------
# GET - 프로필 조회 (없으면 자동 생성)
# -------------------------------
@router.get("/{user_id}", response_model=UserProfileOut)
def get_profile(user_id: str, session: Session = Depends(get_db)):
    profile = session.query(db.UserProfile).filter_by(user_id=user_id).first()
    if not profile:
        # UserProfile 자동 생성
        profile = db.UserProfile(user_id=user_id)
        session.add(profile)
        session.commit()
        session.refresh(profile)

    # allergies 문자열을 list 로 변환
    allergies = []
    if profile.allergies:
        try:
            allergies = json.loads(profile.allergies)
            if not isinstance(allergies, list):
                allergies = [allergies]
        except:
            allergies = [profile.allergies]

    return {
        "user_id": profile.user_id,
        "diet_style": profile.diet_style,
        "cuisine_preference": profile.cuisine_preference,
        "allergies": allergies,
        "notes": profile.notes,
    }


# -------------------------------
# PUT - 프로필 업데이트
# -------------------------------
@router.put("/{user_id}", response_model=UserProfileOut)
def update_profile(user_id: str, req: UserProfileBase, session: Session = Depends(get_db)):
    profile = session.query(db.UserProfile).filter_by(user_id=user_id).first()

    if not profile:
        profile = db.UserProfile(user_id=user_id)

    profile.diet_style = req.diet_style
    profile.cuisine_preference = req.cuisine_preference
    profile.notes = req.notes

    # allergies: list[str] → JSON string
    if isinstance(req.allergies, list):
        profile.allergies = json.dumps(req.allergies, ensure_ascii=False)
    elif isinstance(req.allergies, str):
        profile.allergies = json.dumps([req.allergies], ensure_ascii=False)
    else:
        profile.allergies = None

    session.add(profile)
    session.commit()
    session.refresh(profile)

    return {
        "user_id": profile.user_id,
        "diet_style": profile.diet_style,
        "cuisine_preference": profile.cuisine_preference,
        "allergies": req.allergies,
        "notes": profile.notes,
    }

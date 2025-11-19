# ==========================================
# src/routers/home_feedback.py
# ==========================================

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src import db
from src.services.home_feedback_service import generate_home_feedback

router = APIRouter(tags=["Home Feedback"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

@router.get("/home/feedback/{user_id}", response_model=dict)
def home_feedback(user_id: str, session: Session = Depends(get_db)):
    user = session.query(db.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = generate_home_feedback(user_id, session)
    return result

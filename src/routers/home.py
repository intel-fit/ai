# src/routers/home.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from src import db
from src.services.home_feedback_service import generate_home_feedback

router = APIRouter(tags=["Home"])

def get_db():
    s = db.SessionLocal()
    try:
        yield s
    finally:
        s.close()


@router.get("/home/feedback/{user_id}", response_model=dict)
def home_feedback(user_id: str, session: Session = Depends(get_db)):
    user = session.query(db.User).filter_by(id=user_id).first()
    if not user:
        return {"error": "User not found"}

    result = generate_home_feedback(user_id, session)
    return result

# src/routers/meal_feedback.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src import db
from src.schemas import MealFeedbackCreate
from src.services.meal_feedback_service import apply_meal_feedback

router = APIRouter(prefix="/meal_feedback", tags=["Meal Feedback"])


def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# -------------------------------
# POST - 식단 피드백 등록
# -------------------------------
@router.post("")
def give_meal_feedback(payload: MealFeedbackCreate, session: Session = Depends(get_db)):
    """
    한 끼 식단(UserMealHistory)에 대한 전체 피드백을 받는다.
    - rating: -1 (별로였다), 0 (보통), +1 (좋았다)
    - comment: 선택적인 코멘트
    이 피드백은 UserFeedback에 저장되고,
    해당 끼니에 포함된 음식들의 UserFoodPreference 점수를 조정한다.
    """

    # 유저 존재 여부 체크 (선택이지만 안전하게)
    user = session.query(db.User).filter_by(id=payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        fb = apply_meal_feedback(
            session=session,
            user_id=payload.user_id,
            history_id=payload.history_id,
            rating=payload.rating,
            comment=payload.comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply feedback: {e}")

    return {
        "status": "ok",
        "feedback_id": fb.id,
        "message": "Feedback applied and preferences updated.",
    }

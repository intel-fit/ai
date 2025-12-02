# src/services/meal_feedback_service.py

from typing import List
from sqlalchemy.orm import Session
from src import db


def apply_meal_feedback(
    session: Session,
    user_id: str,
    history_id: int,
    rating: int,
    comment: str | None = None,
):
    """
    1) UserFeedback 테이블에 식단 피드백을 저장하고
    2) 해당 끼니(UserMealHistory)의 음식들에 대해 UserFoodPreference 점수를 조정한다.
       - rating = +1 → 해당 끼니에 포함된 음식들의 선호 점수를 올림
       - rating =  0 → 로그만 남기고 점수는 조정하지 않음
       - rating = -1 → 선호 점수를 낮춤 (0 이하로 떨어지지 않게)
    """

    if rating not in (-1, 0, 1):
        raise ValueError("rating must be -1, 0, or +1")

    # 1️⃣ 끼니 존재 & 소유자 확인
    history = (
        session.query(db.UserMealHistory)
        .filter(db.UserMealHistory.id == history_id)
        .filter(db.UserMealHistory.user_id == user_id)
        .first()
    )
    if not history:
        raise ValueError("Meal history not found for this user")

    # 2️⃣ UserFeedback row 생성
    feedback = db.UserFeedback(
        user_id=user_id,
        history_id=history_id,
        rating=rating,
        comment=comment,
    )
    session.add(feedback)
    session.commit()
    session.refresh(feedback)

    # 3️⃣ rating에 따라 UserFoodPreference 점수 조정
    if rating != 0:
        # 끼니에 포함된 음식들
        items: List[db.UserMealHistoryItem] = list(history.items)

        for item in items:
            food_name = item.food_name
            if not food_name:
                continue

            pref = (
                session.query(db.UserFoodPreference)
                .filter_by(user_id=user_id, food_name=food_name)
                .first()
            )

            if not pref:
                # 아직 선호도 row 없으면 생성
                pref = db.UserFoodPreference(
                    user_id=user_id,
                    food_name=food_name,
                    score=0.0,
                    source="feedback",
                )
                session.add(pref)
                session.flush()  # id 생성만

            if rating == 1:
                # 좋아요 → 점수 증가
                pref.score += 1.0
            elif rating == -1:
                # 싫어요 → 점수 감소 (0 밑으로는 안내려감)
                pref.score = max(0.0, pref.score - 1.0)

            session.add(pref)

        session.commit()

    return feedback

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from src import db
from src.services import nutrition

router = APIRouter(tags=["Nutrition Target"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

@router.post("/nutrition/daily_target", response_model=dict)
def get_daily_nutrition_target(
    user_id: str,
    session: Session = Depends(get_db)
):
    """
    AI 추천 식단 없이도,
    사용자의 목표(TDEE, macros)를 기반으로 일일 영양 목표만 계산해서 반환하는 API.
    """

    # 1️⃣ 사용자 조회
    user = session.query(db.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2️⃣ BMR 기반 TDEE 계산
    if user.body_fat:
        bmr = nutrition.calculate_bmr_katch_mcardle(user.weight, user.body_fat)
    else:
        bmr = nutrition.calculate_bmr_harris_benedict(
            user.weight, user.height, user.age, user.sex
        )

    tdee = nutrition.calculate_tdee(bmr, getattr(user, "activity_level", 1.2))

    # 3️⃣ 목표 칼로리 (goal에 따라 cut/bulk/maintain)
    goal = getattr(user, "goal", "maintain")
    target_kcal = nutrition.calculate_goal_calories(tdee, goal)

    # 4️⃣ 목표 매크로 계산
    protein, fat, carb = nutrition.calculate_macros(
        user.weight, target_kcal, goal, getattr(user, "skeletal_muscle", None)
    )

    # 5️⃣ 반환
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "user_id": user_id,
        "goal": goal,
        "tdee": round(tdee, 1),
        "target_kcal": round(target_kcal, 1),
        "target_protein": round(protein, 1),
        "target_fat": round(fat, 1),
        "target_carbs": round(carb, 1)
    }

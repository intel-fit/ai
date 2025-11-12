# src/routers/recommendation.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from src import db
from src.services import nutrition
from src.services.ai_meal_generator_gemini import generate_realistic_meal_plan
import json
import random

router = APIRouter(tags=["Meal Recommendation"])

# ----------------------------------------------------------
# DB 연결
# ----------------------------------------------------------
def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ----------------------------------------------------------
# 🍱 AI 식단 추천 (일일 / 주간, 프론트 호환 유지)
# ----------------------------------------------------------
@router.post("/recommend_daily_meal", response_model=dict)
def recommend_daily_meal(
    user_id: str,
    meals_per_day: int = 3,
    goal: str = "maintain",
    period: str = "daily",                       # ✅ 일일 / 주간 식단 선택 가능
    excluded_foods: list[str] | None = None,     # ✅ 프론트에서 X 버튼 누른 음식
    session: Session = Depends(get_db)
):
    """
    현실적인 AI 식단 추천 (Gemini 기반)
    - 기존 recommend_daily_meal 구조 유지
    - 일일 / 주간 식단 모두 지원
    - 선호/비선호 음식 자동 반영
    """

    # 1️⃣ 사용자 조회
    user = session.query(db.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2️⃣ BMR / TDEE 계산
    if user.body_fat:
        bmr = nutrition.calculate_bmr_katch_mcardle(user.weight, user.body_fat)
    else:
        bmr = nutrition.calculate_bmr_harris_benedict(user.weight, user.height, user.age, user.sex)

    tdee = nutrition.calculate_tdee(bmr, getattr(user, "activity_level", 1.2))
    goal = getattr(user, "goal", goal)
    target_kcal = nutrition.calculate_goal_calories(tdee, goal)

    protein_target, fat_target, carbs_target = nutrition.calculate_macros(
        user.weight, target_kcal, goal, getattr(user, "skeletal_muscle", None)
    )

    # 3️⃣ 선호 / 비선호 음식 로드
    preferred_foods, disliked_foods = [], []

    if hasattr(user, "preferred_foods") and user.preferred_foods:
        if isinstance(user.preferred_foods, str):
            try:
                preferred_foods = json.loads(user.preferred_foods)
            except Exception:
                preferred_foods = [user.preferred_foods]
        elif isinstance(user.preferred_foods, list):
            preferred_foods = user.preferred_foods

    if hasattr(user, "excluded_foods") and user.excluded_foods:
        if isinstance(user.excluded_foods, str):
            try:
                disliked_foods = json.loads(user.excluded_foods)
            except Exception:
                disliked_foods = [user.excluded_foods]
        elif isinstance(user.excluded_foods, list):
            disliked_foods = user.excluded_foods

    # 프론트 입력(제외 음식) 반영
    if excluded_foods:
        disliked_foods = list(set(disliked_foods + excluded_foods))

    # 4️⃣ 맞춤 코멘트 생성
    prefer_str = ", ".join(preferred_foods) if preferred_foods else ""
    dislike_str = ", ".join(disliked_foods) if disliked_foods else ""
    user_name = getattr(user, "name", user_id)

    if prefer_str and dislike_str:
        comment_line = f"{user_name}님은 {dislike_str}을(를) 피하고 {prefer_str}을(를) 선호하는 분이에요."
    elif dislike_str:
        comment_line = f"{user_name}님은 {dislike_str}을(를) 피하는 분이에요."
    elif prefer_str:
        comment_line = f"{user_name}님은 {prefer_str}을(를) 선호하는 분이에요."
    else:
        comment_line = f"{user_name}님의 개인 맞춤 식단 추천입니다."

    custom_comment = f"🍽️ {comment_line}\n아래는 {'일일' if period=='daily' else '주간'} 식단 추천입니다."

    # 5️⃣ Gemini 기반 식단 생성
    ai_plan = generate_realistic_meal_plan(
        user=user,
        tdee=target_kcal,
        macros={"protein": protein_target, "fat": fat_target, "carb": carbs_target},
        meals_per_day=meals_per_day,
        preferred_foods=preferred_foods,
        excluded_foods=disliked_foods,
    )

    # 6️⃣ 주간 모드 지원
    if period == "weekly":
        ai_plan["request_type"] = "weekly"
        ai_plan["days"] = [
            {
                "day": f"Day {i+1}",
                "meals": ai_plan.get("meals", []),
            }
            for i in range(7)
        ]
        # 중복 최소화 처리
        all_foods = []
        for d in ai_plan["days"]:
            for meal in d["meals"]:
                for f in meal["foods"]:
                    all_foods.append(f["name"])
        unique_foods = list(set(all_foods))
        random.shuffle(unique_foods)
        for i, d in enumerate(ai_plan["days"]):
            for meal in d["meals"]:
                for f in meal["foods"]:
                    if unique_foods:
                        f["name"] = unique_foods[(i + hash(f["name"])) % len(unique_foods)]

    # 7️⃣ 프론트 호환형 반환 구조
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "user_id": user_id,
        "goal": goal,
        "meals_per_day": meals_per_day,
        "target_daily_calories": round(target_kcal, 1),
        "target_protein": round(protein_target, 1),
        "target_fat": round(fat_target, 1),
        "target_carbs": round(carbs_target, 1),
        "comment": custom_comment.strip(),
        "ai_meal_plan": ai_plan,     # ✅ AI 식단 전체 구조 추가 (기존 meals 대체)
    }

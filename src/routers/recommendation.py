# src/routers/recommendation.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
import random
from src import db
from src.services import nutrition



router = APIRouter(tags=["Meal Recommendation"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

@router.post("/recommend_daily_meal", response_model=dict)
def recommend_daily_meal(
    user_id: str,
    meals_per_day: int = 3,
    goal: str = "maintain",
    preferred_foods: list[int] | None = None,
    excluded_foods: list[int] | None = None,
    session: Session = Depends(get_db)
):
    # 1️⃣ 사용자 조회
    user = session.query(db.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2️⃣ BMR/TDEE 계산
    if user.body_fat is not None:
        bmr = nutrition.calculate_bmr_katch_mcardle(user.weight, user.body_fat)
    else:
        bmr = nutrition.calculate_bmr_harris_benedict(user.weight, user.height, user.age, user.sex)

    tdee = nutrition.calculate_tdee(bmr, getattr(user, "activity_level", 1.2))
    target_kcal = nutrition.calculate_goal_calories(tdee, goal)

    # 3️⃣ 목표 매크로 계산
    protein_target, fat_target, carbs_target = nutrition.calculate_macros(
        user.weight, target_kcal, goal, getattr(user, "skeletal_muscle", None)
    )

    # 4️⃣ 끼니별 목표
    meal_ratios = [1/meals_per_day]*meals_per_day
    meal_targets = []
    for i, ratio in enumerate(meal_ratios):
        meal_targets.append({
            "meal_type": f"meal_{i+1}",
            "target_calories": target_kcal * ratio,
            "target_protein": protein_target * ratio,
            "target_fat": fat_target * ratio,
            "target_carbs": carbs_target * ratio
        })

    # 5️⃣ DB에서 음식 불러오기
    query = session.query(db.Food)
    if excluded_foods:
        query = query.filter(~db.Food.id.in_(excluded_foods))
    all_foods = query.all()
    if not all_foods:
        raise HTTPException(status_code=404, detail="No foods available in database")

    # 6️⃣ 선호 음식
    preferred_foods_data = []
    if preferred_foods:
        preferred_foods_data = session.query(db.Food).filter(db.Food.id.in_(preferred_foods)).all()

    # 7️⃣ 끼니별 식단 구성 (단백질 우선 + 칼로리 균형 최적화)
    daily_plan = []
    remaining_foods = all_foods.copy()

    for meal in meal_targets:
        target_cals = meal["target_calories"]
        target_prot = meal["target_protein"]
        target_fat = meal["target_fat"]
        target_carbs = meal["target_carbs"]

        selected_foods = []
        total_cal = total_prot = total_fat = total_carbs = 0

        while remaining_foods and total_cal < target_cals * 0.95:
            # 단백질 부족 우선 후보군
            prot_deficit = target_prot - total_prot
            high_prot_foods = [f for f in remaining_foods if f.protein and (f.protein <= prot_deficit*1.2)]
            candidates = high_prot_foods or remaining_foods

            # 선호 음식 포함 확률 40%
            if preferred_foods_data and random.random() < 0.4:
                food = random.choice(preferred_foods_data)
            else:
                food = random.choice(candidates)

            if food in selected_foods:
                continue

            # 추가 후 목표 초과 방지
            new_cal = total_cal + (food.calories or 0)
            new_fat = total_fat + (food.fat or 0)
            new_carbs = total_carbs + (food.carbs or 0)

            if new_cal > target_cals * 1.05:
                remaining_foods.remove(food)
                continue
            if new_fat > target_fat * 1.05:
                remaining_foods.remove(food)
                continue
            if new_carbs > target_carbs * 1.05:
                remaining_foods.remove(food)
                continue

            selected_foods.append(food)
            total_cal = new_cal
            total_prot += food.protein or 0
            total_fat = new_fat
            total_carbs = new_carbs

            if len(selected_foods) >= 5:
                break

        daily_plan.append({
            "meal_type": meal["meal_type"],
            "target_calories": round(target_cals,1),
            "actual_calories": round(total_cal,1),
            "target_protein": round(target_prot,1),
            "actual_protein": round(total_prot,1),
            "target_fat": round(target_fat,1),
            "actual_fat": round(total_fat,1),
            "target_carbs": round(target_carbs,1),
            "actual_carbs": round(total_carbs,1),
            "foods": [
                {
                    "id": f.id,
                    "name": f.name,
                    "calories": f.calories,
                    "protein": f.protein,
                    "fat": f.fat,
                    "carbs": f.carbs
                } for f in selected_foods
            ]
        })

    # 8️⃣ 반환
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "user_id": user_id,
        "goal": goal,
        "meals_per_day": meals_per_day,
        "target_daily_calories": round(target_kcal,1),
        "target_protein": round(protein_target,1),
        "target_fat": round(fat_target,1),
        "target_carbs": round(carbs_target,1),
        "meals": daily_plan
    }

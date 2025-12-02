# src/services/meal_history_writer.py

from datetime import date
from sqlalchemy.orm import Session
from src import db


def save_ai_meal_plan_to_history(
    session: Session,
    user_id: str,
    ai_plan: dict
):
    """
    Gemini가 생성한 식단(ai_plan)을 UserMealHistory / UserMealHistoryItem 구조로 저장.
    ai_plan 구조는 generate_realistic_meal_plan 의 출력과 동일하다고 가정.
    """

    meals = ai_plan.get("meals", [])
    today = date.today()

    saved_history_ids = []

    for m in meals:
        meal_type = m.get("meal_type", "meal")

        # 1) 끼니 저장
        history_entry = db.UserMealHistory(
            user_id=user_id,
            date=today,
            meal_name=meal_type,
            total_calories=0,
            total_protein=0,
            total_carbs=0,
            total_fat=0,
        )
        session.add(history_entry)
        session.commit()
        session.refresh(history_entry)

        total_c = total_p = total_f = total_car = 0.0

        # 2) 음식 저장
        for food in m.get("foods", []):
            name = food.get("name", "unknown")
            amount = food.get("amount_g", 0)

            calories = float(food.get("calories", 0))
            protein = float(food.get("protein", 0))
            fat = float(food.get("fat", 0))
            carbs = float(food.get("carb", 0) or food.get("carbs", 0))

            item = db.UserMealHistoryItem(
                history_id=history_entry.id,
                food_id=None,  # 실제 FoodDB의 id가 필요하면 이후 매칭 가능
                food_name=name,
                amount_g=amount,
                calories=calories,
                protein=protein,
                fat=fat,
                carbs=carbs,
            )
            session.add(item)

            total_c += calories
            total_p += protein
            total_f += fat
            total_car += carbs

        # 3) 끼니 총 영양소 업데이트
        history_entry.total_calories = total_c
        history_entry.total_protein = total_p
        history_entry.total_fat = total_f
        history_entry.total_carbs = total_car
        session.add(history_entry)

        saved_history_ids.append(history_entry.id)

    session.commit()
    return saved_history_ids

# src/services/summary.py
from datetime import date
from sqlalchemy.orm import Session
from src import db
from src.services.health_score import compute_daily_score


# 간단한 탄수화물 소스 태깅 (MealPlanner와 일관)
_CARB_TAGS = {
    "rice_grain": ["밥", "현미", "잡곡", "귀리", "보리", "퀴노아", "수수"],
    "noodle":     ["면", "국수", "파스타", "칼국수", "라면"],
    "bread":      ["빵", "베이글", "토스트", "식빵", "치아바타", "바게트"],
    "tuber":      ["고구마", "감자"],
    "konjac":     ["곤약밥"],
}

def _carb_source_tag(name: str) -> str:
    name = str(name or "")
    for tag, kws in _CARB_TAGS.items():
        if any(kw in name for kw in kws):
            return tag
    return "other"

def recompute_daily_summaries(user_id: str, target_date: date, session: Session):
    """해당 user의 target_date에 대해 섭취/운동 요약을 재계산하여 upsert."""
    # ---------- 섭취 요약 ----------
    meals = (
        session.query(db.MealLog)
        .filter_by(user_id=user_id, date=target_date)
        .all()
    )

    kcal = prot = fat = carb = fiber = sugar = sodium = 0.0
    total_grams = processed_grams = 0.0
    main_sources = set()

    for meal in meals:
        for mi in meal.items:
            food = session.query(db.Food).get(mi.food_id)
            if not food: 
                continue
            # 실제 섭취량 비율
            base = food.weight or 100.0
            ratio = (mi.quantity_g or 0.0) / base

            kcal   += (food.calories or 0.0) * ratio
            prot   += (food.protein  or 0.0) * ratio
            fat    += (food.fat      or 0.0) * ratio
            carb   += (food.carbs    or 0.0) * ratio
            fiber  += (food.fiber    or 0.0) * ratio
            sugar  += (food.sugar    or 0.0) * ratio
            sodium += (food.sodium   or 0.0) * ratio

            # 초가공 비중 (가공도 4 이상인 항목의 그램 비중)
            total_grams += (mi.quantity_g or 0.0)
            if (food.processing_level or 0) >= 4:
                processed_grams += (mi.quantity_g or 0.0)

            # 메인 소스 다양성(간단히 이름 키워드로 식별)
            tag = _carb_source_tag(food.name)
            if tag != "other":
                main_sources.add(tag)

    processed_ratio = (processed_grams / total_grams) if total_grams > 0 else 0.0

    nut = (
        session.query(db.DailyNutritionSummary)
        .filter_by(user_id=user_id, date=target_date)
        .first()
    )
    if not nut:
        nut = db.DailyNutritionSummary(
            user_id=user_id, date=target_date
        )
        session.add(nut)

    nut.kcal = round(kcal, 1)
    nut.protein_g = round(prot, 1)
    nut.fat_g = round(fat, 1)
    nut.carb_g = round(carb, 1)
    nut.fiber_g = round(fiber, 1)
    nut.sugar_g = round(sugar, 1)
    nut.sodium_mg = round(sodium, 1)
    nut.processed_ratio = round(processed_ratio, 3)
    nut.distinct_main_sources = len(main_sources)

    # ---------- 운동 요약 ----------
    ex_logs = (
        session.query(db.ExerciseLog)
        .filter_by(user_id=user_id, date=target_date)
        .all()
    )
    duration = sum((l.duration_min or 0.0) for l in ex_logs)
    burned   = sum((l.calories_burned or 0.0) for l in ex_logs)
    avg_int  = (sum((l.intensity or 0.0) for l in ex_logs) / len(ex_logs)) if ex_logs else 0.0

    ex = (
        session.query(db.DailyExerciseSummary)
        .filter_by(user_id=user_id, date=target_date)
        .first()
    )
    if not ex:
        ex = db.DailyExerciseSummary(user_id=user_id, date=target_date)
        session.add(ex)

    ex.duration_min = round(duration, 1)
    ex.calories_burned = round(burned, 1)
    ex.avg_intensity = round(avg_int, 2)

    session.commit()
    
    # 마지막에 추가
    compute_daily_score(user_id, target_date, session)

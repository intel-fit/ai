from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse
from src import db
from src.services.meal_planner import MealPlanner
from src.services import nutrition
import os
from src.services.meal_logger import append_meal_log

router = APIRouter(tags=["AI Healthy Meal Plan"])
planner = MealPlanner()  # 하루 + 주간 모두 처리

# -----------------------
# DB 세션
# -----------------------
def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

# -----------------------
# 사용자별 칼로리/매크로 계산
# -----------------------
def _calc_targets(user):
    """사용자 프로필을 기반으로 목표 칼로리와 탄단지 계산"""
    if user.body_fat:
        bmr = nutrition.calculate_bmr_katch_mcardle(user.weight, user.body_fat)
    else:
        bmr = nutrition.calculate_bmr_harris_benedict(
            user.weight, user.height, user.age, user.sex
        )
    tdee = nutrition.calculate_tdee(bmr, user.activity_level or 1.2)
    goal_cal = nutrition.calculate_goal_calories(tdee, user.goal)
    p, f, c = nutrition.calculate_macros(
        user.weight, goal_cal, user.goal, user.skeletal_muscle
    )
    return goal_cal, p, f, c

# -----------------------
# 하루 식단 생성
# -----------------------
@router.get("/generate_daily_plan", response_model=dict)
def generate_daily_plan(user_id: str, meals_per_day: int = 3, session: Session = Depends(get_db)):
    """일간 식단 생성 (AI 품질 기반)"""
    
    user = session.query(db.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    plan = planner.plan_day(user, meals_per_day, _calc_targets)

    append_meal_log(user_id, plan)
    return {
        "user_id": user_id,
        "goal": user.goal,
        "meals_per_day": meals_per_day,
        "daily_plan": plan
    }

# -----------------------
# 주간 식단 생성
# -----------------------
@router.get("/generate_weekly_plan", response_model=dict)
def generate_weekly_plan(user_id: str, meals_per_day: int = 3, days: int = 7, session: Session = Depends(get_db)):
    """7일치 AI 품질 기반 주간 식단 생성"""
    user = session.query(db.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    week_plan = []
    total = {"kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0, "avg_quality": 0}

    for day in range(days):
        daily = planner.plan_day(user, meals_per_day, _calc_targets)
        week_plan.append({
            "day": day + 1,
            "daily_plan": daily
        })

        total["kcal"] += daily["actual_daily"]["kcal"]
        total["protein_g"] += daily["actual_daily"]["protein_g"]
        total["fat_g"] += daily["actual_daily"]["fat_g"]
        total["carb_g"] += daily["actual_daily"]["carb_g"]
        total["avg_quality"] += daily.get("avg_quality", 60)

    weekly_avg = {k: total[k] / days for k in total}

    return {
        "user_id": user_id,
        "goal": user.goal,
        "meals_per_day": meals_per_day,
        "days": days,
        "weekly_average": weekly_avg,
        "weekly_plan": week_plan
    }

# -----------------------
# 주간 식단 시각화 (선택)
# -----------------------
@router.get("/visualize_weekly_plan")
def visualize_weekly_plan(user_id: str, meals_per_day: int = 3, days: int = 7, session: Session = Depends(get_db)):
    """주간 식단을 그래프로 시각화 (PNG 반환)"""
    import matplotlib.pyplot as plt

    user = session.query(db.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 하루 단위 식단 반복 생성
    week_data = [planner.plan_day(user, meals_per_day, _calc_targets) for _ in range(days)]

    days_range = range(1, days + 1)
    kcal = [day["actual_daily"]["kcal"] for day in week_data]
    protein = [day["actual_daily"]["protein_g"] for day in week_data]
    fat = [day["actual_daily"]["fat_g"] for day in week_data]
    carb = [day["actual_daily"]["carb_g"] for day in week_data]
    quality = [day.get("avg_quality", 0) for day in week_data]

    plt.figure(figsize=(10, 6))
    plt.plot(days_range, kcal, label="Calories (kcal)", marker="o")
    plt.plot(days_range, protein, label="Protein (g)", marker="o")
    plt.plot(days_range, fat, label="Fat (g)", marker="o")
    plt.plot(days_range, carb, label="Carbs (g)", marker="o")
    plt.plot(days_range, quality, label="Quality Score", marker="*")
    plt.title("Weekly Nutrition Trend")
    plt.xlabel("Day")
    plt.ylabel("Amount")
    plt.legend()
    plt.grid(True)

    os.makedirs("outputs", exist_ok=True)
    output_path = "outputs/weekly_plan_chart.png"
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()

    if not os.path.exists(output_path):
        raise HTTPException(status_code=500, detail="Visualization failed")

    return FileResponse(output_path, media_type="image/png", filename="weekly_plan_chart.png")

# src/routers/user.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src import db
from src.schemas import UserCreate, UserOut
from src.services.nutrition import (
    calculate_bmr_katch_mcardle,
    calculate_bmr_harris_benedict,
    calculate_tdee,
    calculate_goal_calories,
    calculate_macros,
    adjust_activity_level,
    weekly_goal_nutrition,
    adjust_daily_activity,
    get_weekly_trend,
    get_monthly_trend
)
from datetime import date, timedelta, datetime
from fastapi.responses import StreamingResponse
import matplotlib.pyplot as plt
import io
from datetime import date


router = APIRouter(tags=["User"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

# ----------------------
# 사용자 생성
# ----------------------
@router.post("/create", response_model=UserOut)
def create_user(user: UserCreate, session: Session = Depends(get_db)):
    db_user = db.User(**user.dict())
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

# ----------------------
# 사용자 TDEE 계산
# ----------------------
@router.get("/{user_id}/tdee")
def get_user_tdee(user_id: str, session: Session = Depends(get_db)):
    user = session.query(db.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 체지방 기반 BMR
    if user.body_fat is not None:
        bmr = calculate_bmr_katch_mcardle(user.weight, user.body_fat)
    else:
        bmr = calculate_bmr_harris_benedict(user.weight, user.height, user.age, user.sex)
    
    # 오늘 기준 활동계수
    activity_level = adjust_activity_level(user.exercise_logs, reference_date=date.today())
    tdee = calculate_tdee(bmr, activity_level)
    goal_cal = calculate_goal_calories(tdee, user.goal)
    
    # 매크로 계산 (단백질/지방/탄수)
    protein_g, fat_g, carbs_g = calculate_macros(user.weight, goal_cal, user.goal, user.skeletal_muscle)
    
    return {
        "user": user.name,
        "bmr": round(bmr, 2),
        "tdee": round(tdee, 2),
        "goal_calories": round(goal_cal, 2),
        "protein_g": round(protein_g, 1),
        "fat_g": round(fat_g, 1),
        "carbs_g": round(carbs_g, 1),
        "goal": user.goal
    }

# ----------------------
# 주간 목표 칼로리 / 매크로
# ----------------------
@router.get("/{user_id}/weekly")
def get_weekly_nutrition(user_id: str, session: Session = Depends(get_db)):
    user = session.query(db.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())

    # BMR 계산
    if user.body_fat is not None:
        bmr = calculate_bmr_katch_mcardle(user.weight, user.body_fat)
    else:
        bmr = calculate_bmr_harris_benedict(user.weight, user.height, user.age, user.sex)

    week_data = []
    for i in range(7):
        # 이번주 요일
        this_week_day = this_monday + timedelta(days=i)
        # 저번주 동일 요일
        last_week_day = this_week_day - timedelta(days=7)

        # 저번주 동일 요일 운동 기록
        logs = [log for log in user.exercise_logs if log.date == last_week_day]
        calories_burned = sum(log.calories_burned for log in logs) if logs else 0

        # TDEE = BMR + 저번주 해당 요일 운동 칼로리
        tdee = bmr + calories_burned
        goal_cal = calculate_goal_calories(tdee, user.goal)
        protein_g, fat_g, carbs_g = calculate_macros(user.weight, goal_cal, user.goal, user.skeletal_muscle)

        week_data.append({
            "date": this_week_day.isoformat(),
            "goal_calories": round(goal_cal, 2),
            "protein_g": round(protein_g, 1),
            "fat_g": round(fat_g, 1),
            "carbs_g": round(carbs_g, 1),
        })

    return week_data

# ----------------------
# 사용자 주별 트렌드
# ----------------------
@router.get("/{user_id}/trend/weekly")
def get_user_weekly_trend(user_id: str, session: Session = Depends(get_db)):
    user = session.query(db.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return get_weekly_trend(user)

# ----------------------
# 사용자 월별 트렌드
# ----------------------
@router.get("/{user_id}/trend/monthly")
def get_user_monthly_trend(user_id: str, session: Session = Depends(get_db)):
    user = session.query(db.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return get_monthly_trend(user)


# ----------------------
# 주별 그래프
# ----------------------
@router.get("/{user_id}/weekly-graph")
def weekly_graph(user_id: str, session: Session = Depends(get_db)):
    user = session.query(db.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    trends = get_weekly_trend(user)

    if not trends:
        raise HTTPException(status_code=404, detail="No weekly trend data")

    labels = [f"{t['week_start'][5:]}~{t['week_end'][5:]}" for t in trends]  # MM-DD~MM-DD
    goal_calories = [t["avg_goal_calories"] for t in trends]

    plt.figure(figsize=(10,5))
    plt.plot(labels, goal_calories, marker='o', color='orange', label="Avg Goal Calories")
    plt.title(f"Weekly Calorie Trend for {user.name}")
    plt.xlabel("Week")
    plt.ylabel("Avg Goal Calories")
    plt.xticks(rotation=45)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return StreamingResponse(buf, media_type="image/png")


# ----------------------
# 월별 그래프
# ----------------------
@router.get("/{user_id}/monthly-graph")
def monthly_graph(user_id: str, session: Session = Depends(get_db)):
    user = session.query(db.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    trends = get_monthly_trend(user)

    if not trends:
        raise HTTPException(status_code=404, detail="No monthly trend data")

    labels = [t["month"] for t in trends]
    goal_calories = [t["avg_goal_calories"] for t in trends]

    plt.figure(figsize=(10,5))
    plt.plot(labels, goal_calories, marker='o', color='green', label="Avg Goal Calories")
    plt.title(f"Monthly Calorie Trend for {user.name}")
    plt.xlabel("Month")
    plt.ylabel("Avg Goal Calories")
    plt.xticks(rotation=45)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return StreamingResponse(buf, media_type="image/png")


@router.get("/{user_id}/weekly-nutrition-graph")
def weekly_nutrition_graph(user_id: str, session: Session = Depends(get_db)):
    user = session.query(db.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    trends = get_weekly_trend(user)

    if not trends:
        raise HTTPException(status_code=404, detail="No weekly trend data")

    labels = [f"{t['week_start'][5:]}~{t['week_end'][5:]}" for t in trends]
    protein = [t["avg_protein_g"] for t in trends]
    fat = [t["avg_fat_g"] for t in trends]
    carbs = [t["avg_carbs_g"] for t in trends]

    plt.figure(figsize=(10,5))
    plt.plot(labels, protein, marker='o', label="Protein (g)", color='blue')
    plt.plot(labels, fat, marker='o', label="Fat (g)", color='red')
    plt.plot(labels, carbs, marker='o', label="Carbs (g)", color='green')
    plt.title(f"Weekly Nutrition Trend for {user.name}")
    plt.xlabel("Week")
    plt.ylabel("Grams")
    plt.xticks(rotation=45)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return StreamingResponse(buf, media_type="image/png")


@router.get("/{user_id}/monthly-nutrition-graph")
def monthly_nutrition_graph(user_id: str, session: Session = Depends(get_db)):
    user = session.query(db.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    trends = get_monthly_trend(user)

    if not trends:
        raise HTTPException(status_code=404, detail="No monthly trend data")

    labels = [t["month"] for t in trends]

    # 월별 단백질/지방/탄수는 주별 trend 데이터를 평균해서 계산
    protein = []
    fat = []
    carbs = []

    for month in labels:
        month_start = date.fromisoformat(f"{month}-01")
        month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)
        daily_data = adjust_daily_activity(user)
        month_logs = [d for d in daily_data if month_start <= date.fromisoformat(d["date"]) <= month_end]

        if month_logs:
            protein.append(sum(d["protein_g"] for d in month_logs)/len(month_logs))
            fat.append(sum(d["fat_g"] for d in month_logs)/len(month_logs))
            carbs.append(sum(d["carbs_g"] for d in month_logs)/len(month_logs))
        else:
            protein.append(0)
            fat.append(0)
            carbs.append(0)

    plt.figure(figsize=(10,5))
    plt.plot(labels, protein, marker='o', label="Protein (g)", color='blue')
    plt.plot(labels, fat, marker='o', label="Fat (g)", color='red')
    plt.plot(labels, carbs, marker='o', label="Carbs (g)", color='green')
    plt.title(f"Monthly Nutrition Trend for {user.name}")
    plt.xlabel("Month")
    plt.ylabel("Grams")
    plt.xticks(rotation=45)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return StreamingResponse(buf, media_type="image/png")

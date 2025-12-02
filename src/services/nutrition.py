# src/services/nutrition.py
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from src.services.ml_predictor import predict_next_week_activity, predict_goal_calories_ml
import numpy as np
from src import db

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

def calculate_bmr_katch_mcardle(weight: float, body_fat: float) -> float:
    """
    Katch-McArdle 공식 (체지방 기반)
    body_fat: % 값 (예: 20)
    """
    lean_mass = weight * (1 - body_fat / 100)
    return 370 + 21.6 * lean_mass

def calculate_bmr_harris_benedict(weight: float, height: float, age: int, sex: str) -> float:
    """
    Harris-Benedict 공식 (체지방 정보 없을 때)
    """
    if sex.lower() == "male":
        return 88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age)
    else:
        return 447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)

def calculate_tdee(bmr: float, activity_level: float) -> float:
    return bmr * activity_level

def calculate_goal_calories(tdee: float, goal: str) -> float:
    """
    목표(goal)에 따라 TDEE 조정
    DIET, BULK, LEAN_MASS, MUSCLE_GAIN, MAINTENANCE
    """

    goal = goal.upper()

    if goal == "DIET":
        return tdee * 0.80  # 감량
    elif goal == "BULK":
        return tdee * 1.20  # 벌크업
    elif goal == "LEAN_MASS":
        return tdee * 1.05  # 린매스업
    elif goal == "MUSCLE_GAIN":
        return tdee * 1.10  # 근증량
    elif goal == "MAINTENANCE":
        return tdee

    # fallback
    return tdee


# 목표 단백질 계산 (체중, 목표에 따라)
def calculate_protein(user_weight: float, goal: str) -> float:
    if goal == "bulk":
        return user_weight * 2.0
    elif goal == "lean":
        return user_weight * 2.2
    elif goal == "diet":
        return user_weight * 2.5
    return user_weight * 2.0  # 기본값

# 목표 지방 계산 (총칼로리 대비 비율)
def calculate_fat(goal_cal: float, goal: str) -> float:
    if goal == "bulk":
        fat_ratio = 0.25
    elif goal == "lean":
        fat_ratio = 0.30
    elif goal == "diet":
        fat_ratio = 0.25
    else:
        fat_ratio = 0.25
    return (goal_cal * fat_ratio) / 9

# 남은 칼로리로 탄수화물 계산
def calculate_carbs(goal_cal: float, protein_g: float, fat_g: float) -> float:
    calories_from_protein = protein_g * 4
    calories_from_fat = fat_g * 9
    remaining_cal = goal_cal - (calories_from_protein + calories_from_fat)
    return remaining_cal / 4


def adjust_activity_level(exercise_logs, reference_date: date):
    """
    reference_date 기준, 과거 같은 요일의 운동 기록을 가져와 활동계수 계산
    """
    # reference_date의 요일에 맞는 로그 필터 (저번주 같은 요일)
    target_date = reference_date - timedelta(days=7)
    logs_on_day = [log for log in exercise_logs if log.date == target_date]

    if not logs_on_day:
        return 1.2

    avg_calories = sum(log.calories_burned for log in logs_on_day) / len(logs_on_day)

    if avg_calories < 200:
        return 1.2
    elif avg_calories < 400:
        return 1.4
    elif avg_calories < 600:
        return 1.6
    elif avg_calories < 800:
        return 1.8
    else:
        return 1.9

def calculate_macros(weight, goal_calories, goal, skeletal_muscle=None):
    goal = goal.upper()

    protein_factor_map = {
        "DIET": 2.3,
        "BULK": 2.0,
        "LEAN_MASS": 2.1,
        "MUSCLE_GAIN": 2.0,
        "MAINTENANCE": 1.8,
    }

    protein_per_kg = protein_factor_map.get(goal, 1.8)

    if skeletal_muscle:
        protein_g = skeletal_muscle * protein_per_kg
    else:
        protein_g = weight * protein_per_kg

    protein_cal = protein_g * 4

    fat_ratio_map = {
        "DIET": 0.25,
        "BULK": 0.25,
        "LEAN_MASS": 0.20,
        "MUSCLE_GAIN": 0.20,
        "MAINTENANCE": 0.30,
    }

    fat_ratio = fat_ratio_map.get(goal, 0.25)

    fat_g = (goal_calories * fat_ratio) / 9
    fat_cal = fat_g * 9

    carbs_cal = goal_calories - (protein_cal + fat_cal)
    carbs_g = carbs_cal / 4

    return round(protein_g, 1), round(fat_g, 1), round(carbs_g, 1)





def adjust_daily_activity(user):
    """
    저번주 요일별 운동 기록 기반으로 이번주 목표 칼로리 및 매크로 계산
    (운동 강도 가중치 포함)
    """
    today = date.today()
    this_week_monday = today - timedelta(days=today.weekday())
    last_week_monday = this_week_monday - timedelta(days=7)
    last_week_sunday = last_week_monday + timedelta(days=6)

    if user.body_fat is not None:
        bmr = calculate_bmr_katch_mcardle(user.weight, user.body_fat)
    else:
        bmr = calculate_bmr_harris_benedict(user.weight, user.height, user.age, user.sex)

    week_data = []
    for i in range(7):
        last_week_day = last_week_monday + timedelta(days=i)
        this_week_day = this_week_monday + timedelta(days=i)

        logs = [log for log in user.exercise_logs if log.date == last_week_day]

        if logs:
            # 평균 칼로리와 강도
            avg_calories = sum(log.calories_burned for log in logs) / len(logs)
            avg_intensity = sum(log.intensity or 1 for log in logs) / len(logs)
            intensity_factor = intensity_weight(round(avg_intensity))
        else:
            avg_calories = 0
            intensity_factor = 1.0

        # 이번주 목표 = BMR + 운동칼로리 * 강도 가중치
        total_cal = bmr + avg_calories * intensity_factor
        goal_cal = calculate_goal_calories(total_cal, user.goal)

        protein_g, fat_g, carbs_g = calculate_macros(
            user.weight, goal_cal, user.goal, user.skeletal_muscle
        )

        week_data.append({
            "date": this_week_day.isoformat(),
            "goal_calories": round(goal_cal, 2),
            "protein_g": round(protein_g, 1),
            "fat_g": round(fat_g, 1),
            "carbs_g": round(carbs_g, 1),
            "avg_intensity": round(avg_intensity, 1) if logs else 0,
            "calories_burned": round(avg_calories, 1),
        })

    return week_data

def weekly_goal_nutrition(user):
    """
    ML 기반 저번주 운동 기록 + 강도 기반으로 이번주 목표 칼로리 예측
    """
    today = date.today()
    this_week_monday = today - timedelta(days=today.weekday())

    ml_predicted_goal = predict_goal_calories_ml(user)
    ml_daily_activity = predict_next_week_activity(user)

    week_data = []
    for i in range(7):
        this_week_day = this_week_monday + timedelta(days=i)
        last_week_day = this_week_day - timedelta(days=7)

        logs = [log for log in user.exercise_logs if log.date == last_week_day]
        calories_burned = sum(log.calories_burned for log in logs) if logs else 0
        avg_intensity = np.mean([log.intensity or 0 for log in logs]) if logs else 0

        # BMR 계산
        if user.body_fat is not None:
            bmr = calculate_bmr_katch_mcardle(user.weight, user.body_fat)
        else:
            bmr = calculate_bmr_harris_benedict(user.weight, user.height, user.age, user.sex)

        # ML 예측값 우선 사용, 없으면 기존 로직
        if ml_predicted_goal:
            goal_cal = ml_predicted_goal + ml_daily_activity[i]
        else:
            tdee = bmr + calories_burned
            goal_cal = calculate_goal_calories(tdee, user.goal)

        protein_g, fat_g, carbs_g = calculate_macros(user.weight, goal_cal, user.goal, user.skeletal_muscle)

        week_data.append({
            "date": this_week_day.isoformat(),
            "goal_calories": round(goal_cal, 2),
            "protein_g": round(protein_g, 1),
            "fat_g": round(fat_g, 1),
            "carbs_g": round(carbs_g, 1),
            "avg_intensity": round(avg_intensity, 1)
        })

    return week_data

def get_weekly_trend(user):
    """
    최근 4주 동안의 주별 평균 목표 칼로리 및 매크로 변화 (ML 기반 예측 반영)
    """
    today = date.today()
    trends = []

    for i in range(4):
        week_end = today - timedelta(days=today.weekday() + i * 7)
        week_start = week_end - timedelta(days=6)

        # 해당 주 운동 로그 필터
        logs = [
            log for log in user.exercise_logs
            if week_start <= log.date <= week_end
        ]
        if not logs:
            continue

        # ML 기반 다음 주 예측
        ml_pred_goal = predict_goal_calories_ml(user)
        ml_pred_activity = predict_next_week_activity(user)

        # 해당 주 평균 계산
        total_cal_burned = sum(log.calories_burned for log in logs)
        avg_intensity = np.mean([log.intensity or 0 for log in logs])

        # BMR 계산
        if user.body_fat is not None:
            bmr = calculate_bmr_katch_mcardle(user.weight, user.body_fat)
        else:
            bmr = calculate_bmr_harris_benedict(user.weight, user.height, user.age, user.sex)

        # ML 기반 보정
        if ml_pred_goal:
            avg_goal_cal = ml_pred_goal + np.mean(ml_pred_activity)
        else:
            tdee = bmr + (total_cal_burned / 7)
            avg_goal_cal = calculate_goal_calories(tdee, user.goal)

        protein_g, fat_g, carbs_g = calculate_macros(user.weight, avg_goal_cal, user.goal, user.skeletal_muscle)

        trends.append({
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "avg_goal_calories": round(avg_goal_cal, 1),
            "avg_protein_g": round(protein_g, 1),
            "avg_fat_g": round(fat_g, 1),
            "avg_carbs_g": round(carbs_g, 1),
            "avg_intensity": round(avg_intensity, 1),
        })

    return list(reversed(trends))  # 오래된 주 → 최신 주


def get_monthly_trend(user):
    """
    최근 3개월 동안의 월별 운동량 및 목표 칼로리 변화 (ML 기반)
    """
    today = date.today()
    trends = []

    for i in range(3):
        month_start = (today.replace(day=1) - relativedelta(months=i))
        next_month_start = (month_start + relativedelta(months=1))

        logs = [
            log for log in user.exercise_logs
            if month_start <= log.date < next_month_start
        ]
        if not logs:
            continue

        total_burned = sum(log.calories_burned for log in logs)
        avg_intensity = np.mean([log.intensity or 0 for log in logs])

        # BMR 계산
        if user.body_fat is not None:
            bmr = calculate_bmr_katch_mcardle(user.weight, user.body_fat)
        else:
            bmr = calculate_bmr_harris_benedict(user.weight, user.height, user.age, user.sex)

        # ML 기반 다음달 예측
        ml_pred_goal = predict_goal_calories_ml(user)
        ml_pred_activity = predict_next_week_activity(user)

        if ml_pred_goal:
            avg_goal_cal = ml_pred_goal + np.mean(ml_pred_activity)
        else:
            tdee = bmr + (total_burned / max(1, len(logs)))
            avg_goal_cal = calculate_goal_calories(tdee, user.goal)

        trends.append({
            "month": month_start.strftime("%Y-%m"),
            "total_exercise_cal": round(total_burned, 1),
            "avg_goal_calories": round(avg_goal_cal, 1),
            "avg_intensity": round(avg_intensity, 1),
        })

    return list(reversed(trends))

def update_daily_goal_after_exercise(user_id: str, target_date: date, session):
    """
    운동 로그가 추가된 특정 날짜의 자동 목표만 다시 계산하여 업데이트.
    수동 설정(is_manual=True)인 날짜는 절대 변경되지 않음.
    """

    # 1) user 조회
    user = session.query(db.User).get(user_id)
    if not user:
        return

    # 2) 날짜별 목표 조회
    goal = (
        session.query(db.DailyNutritionGoal)
        .filter_by(user_id=user_id, date=target_date)
        .first()
    )
    if not goal or goal.is_manual:
        return  # 없거나 manual이면 종료

    # 3) 최신 운동 요약 가져오기
    daily_ex = (
        session.query(db.DailyExerciseSummary)
        .filter_by(user_id=user_id, date=target_date)
        .first()
    )
    if daily_ex:
        session.refresh(daily_ex)

    burned = daily_ex.calories_burned if daily_ex else 0

    # 4) TDEE 새로 계산
    if user.body_fat is not None:
        bmr = calculate_bmr_katch_mcardle(user.weight, user.body_fat)
    else:
        bmr = calculate_bmr_harris_benedict(user.weight, user.height, user.age, user.sex)

    new_tdee = calculate_tdee(bmr, user.activity_level) + burned
    new_target_calorie = calculate_goal_calories(new_tdee, user.goal)

    protein_g, fat_g, carbs_g = calculate_macros(
        weight=user.weight,
        goal_calories=new_target_calorie,
        goal=user.goal,
        skeletal_muscle=user.skeletal_muscle
    )

    # 5) DB 업데이트
    goal.target_calorie = new_target_calorie
    goal.target_protein = protein_g
    goal.target_fat = fat_g
    goal.target_carb = carbs_g
    goal.updated_at = datetime.utcnow()

    session.flush()
    session.commit()


def calculate_macros_from_manual_goal(total_calorie: float, goal: str):
    """
    사용자가 직접 입력한 칼로리(total_calorie)를 기반으로
    목표(goal)에 따라 탄단지 비율을 나누어 g 단위로 반환.
    """

    goal = goal.upper()

    ratio_map = {
        "DIET":        (0.35, 0.20, 0.45),  # 단백질 높게, 지방 낮게
        "BULK":        (0.28, 0.22, 0.50),  # 탄수 비중 높게
        "LEAN_MASS":   (0.33, 0.22, 0.45),
        "MUSCLE_GAIN": (0.30, 0.20, 0.50),
        "MAINTENANCE": (0.30, 0.30, 0.40),
    }

    pct_p, pct_f, pct_c = ratio_map.get(goal, ratio_map["MAINTENANCE"])

    protein_g = round((total_calorie * pct_p) / 4, 1)
    fat_g     = round((total_calorie * pct_f) / 9, 1)
    carbs_g   = round((total_calorie * pct_c) / 4, 1)

    return protein_g, fat_g, carbs_g

# src/services/ml_predictor.py
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import date, timedelta

def calculate_goal_calories(tdee: float, goal: str) -> float:
    goal = goal.lower()
    if goal == "diet":
        return tdee * 0.8
    elif goal == "bulk":
        return tdee * 1.2
    elif goal == "lean":
        return tdee * 1.05
    return tdee


def predict_next_week_activity(user):
    """
    최근 운동 기록 기반으로 다음 주 예상 활동량(칼로리)을 예측.
    간단한 Linear Regression 사용.
    """
    today = date.today()
    four_weeks_ago = today - timedelta(days=28)

    logs = [log for log in user.exercise_logs if log.date >= four_weeks_ago]
    if len(logs) < 3:
        avg = np.mean([log.calories_burned for log in logs]) if logs else 300
        return [avg] * 7

    weekly_data = {}
    for log in logs:
        week_num = log.date.isocalendar()[1]
        weekly_data.setdefault(week_num, []).append(log.calories_burned)
    weekly_sums = [sum(v) for v in weekly_data.values()]

    X = np.arange(len(weekly_sums)).reshape(-1, 1)
    y = np.array(weekly_sums)
    model = LinearRegression().fit(X, y)

    next_week_pred = model.predict([[len(weekly_sums)]])[0]
    daily_estimate = next_week_pred / 7

    return [daily_estimate] * 7


def predict_goal_calories_ml(user):
    """
    최근 운동 강도 및 칼로리 기반으로 다음 주 목표 칼로리 예측 (Linear Regression)
    """
    today = date.today()
    four_weeks_ago = today - timedelta(days=28)

    logs = [log for log in user.exercise_logs if log.date >= four_weeks_ago]
    if len(logs) < 5:
        return None

    # 평균 강도와 소모 칼로리 기반 학습
    X = np.array([[log.intensity or 0, log.calories_burned] for log in logs])
    y = np.array([log.calories_burned for log in logs])

    model = LinearRegression()
    model.fit(X, y)

    # 최근 강도 평균으로 다음주 예측
    avg_intensity = np.mean([log.intensity or 0 for log in logs])
    avg_calories = np.mean([log.calories_burned for log in logs])
    predicted_calories = model.predict([[avg_intensity, avg_calories]])[0]

    # 목표에 따라 조정 (bulk/diet/lean)
    goal_adjusted = calculate_goal_calories(predicted_calories, user.goal)
    return round(goal_adjusted, 2)

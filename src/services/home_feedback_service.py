# ==========================================
# src/services/home_feedback_service.py
# ==========================================

from datetime import date, timedelta
from sqlalchemy.orm import Session
from src.db import (
    User,
    DailyNutritionSummary,
    DailyExerciseSummary,
    DailyHealthScore,
)
import statistics
import json
import os
import requests


# ==========================
# 1) 오늘 데이터 기반 기본 한줄 헤드라인
# ==========================
def simple_headline_builder(user_id: str, session: Session):
    today = date.today()

    today_nut = (
        session.query(DailyNutritionSummary)
        .filter(DailyNutritionSummary.user_id == user_id)
        .filter(DailyNutritionSummary.date == today)
        .first()
    )

    today_ex = (
        session.query(DailyExerciseSummary)
        .filter(DailyExerciseSummary.user_id == user_id)
        .filter(DailyExerciseSummary.date == today)
        .first()
    )

    headline = None
    code = None

    # -------- 운동 기준 ----------
    if today_ex and today_ex.duration_min > 0:
        if today_ex.duration_min >= 60:
            headline = "오늘도 1시간 이상 운동했어요! 꾸준함이 가장 큰 무기예요 🔥"
            code = "EX_LONG"
        elif today_ex.duration_min >= 30:
            headline = "오늘의 운동, 30분 이상 완주! 좋은 페이스예요 💪"
            code = "EX_MED"
        else:
            headline = "짧아도 운동한 하루! 속도를 내기 위한 첫 걸음이에요 🏃‍♂️"
            code = "EX_SHORT"

    # -------- 식단 기준 ----------
    elif today_nut:
        if today_nut.protein_g >= 90:
            headline = "단백질 충전 완료! 회복과 성장에 도움이 돼요 🍗"
            code = "FOOD_HIGH_PROTEIN"
        elif today_nut.kcal < 1300:
            headline = "오늘 섭취량이 낮아요. 에너지가 부족할 수 있어요 ⚡"
            code = "FOOD_LOW_KCAL"
        else:
            headline = "오늘 식단은 안정적이에요. 균형이 잘 잡혀가고 있어요 🙂"
            code = "FOOD_GOOD"

    # -------- 데이터 없음 ----------
    else:
        headline = "아직 기록이 없어요. 오늘의 첫 기록을 만들어볼까요? ✨"
        code = "NO_DATA"

    return {"headline": headline, "code": code}


# ==========================
# 2) 최근 3일간 자동 패턴 감지
# ==========================
def detect_3day_patterns(user_id: str, session: Session):
    today = date.today()
    start = today - timedelta(days=2)

    nuts = (
        session.query(DailyNutritionSummary)
        .filter(DailyNutritionSummary.user_id == user_id)
        .filter(DailyNutritionSummary.date >= start)
        .order_by(DailyNutritionSummary.date)
        .all()
    )
    exes = (
        session.query(DailyExerciseSummary)
        .filter(DailyExerciseSummary.user_id == user_id)
        .filter(DailyExerciseSummary.date >= start)
        .order_by(DailyExerciseSummary.date)
        .all()
    )

    patterns = []
    actions = []

    # ---------- 단백질 부족 ----------
    if nuts and all(n.protein_g < 70 for n in nuts):
        patterns.append("최근 3일간 단백질이 꾸준히 부족해요.")
        actions.append("그릭요거트, 닭가슴살, 두부 같은 단백질원을 끼니마다 추가하세요.")
        primary = "LOW_PROTEIN"

    # ---------- 고칼로리 패턴 ----------
    elif nuts and all(n.kcal > 2300 for n in nuts):
        patterns.append("최근 3일 동안 섭취 칼로리가 높게 유지되고 있어요.")
        actions.append("간식/음료 칼로리를 한 번 점검해보는 것도 좋아요.")
        primary = "HIGH_KCAL"

    # ---------- 운동 부족 ----------
    elif exes and all(e.duration_min < 10 for e in exes):
        patterns.append("최근 3일간 거의 운동하지 못했어요.")
        actions.append("단 10분이라도 스트레칭 + 코어 루틴을 실행해보세요.")
        primary = "NO_EXERCISE"

    # ---------- 운동 꾸준 ----------
    elif exes and all(e.duration_min >= 20 for e in exes):
        patterns.append("최근 3일간 꾸준히 운동하고 있어요! 좋은 흐름이 이어지고 있어요.")
        actions.append("지금처럼 20~40분 루틴을 유지하면 변화가 더 빨라져요!")
        primary = "GOOD_EX"

    else:
        primary = "NONE"

    return {
        "patterns": patterns,
        "actions": actions,
        "primary": primary,
    }


# ==========================
# 3) Gemini 기반 감성 한줄 AI 피드백
# ==========================
def ai_one_liner(user_name: str, health_score: float, patterns: list):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "AI 피드백을 생성할 수 없어요 (API Key 없음)."

    pattern_text = ", ".join(patterns) if patterns else "특별한 패턴 없음"

    prompt = f"""
당신은 한국인 운동 코치 AI입니다.
아래 정보를 바탕으로 사용자에게 감성적이고 동기부여되는 '한 줄 피드백'을 만들어주세요.

- 사용자 이름: {user_name}
- 최근 건강 점수: {health_score}
- 최근 3일 패턴: {pattern_text}

조건:
- 반드시 1문장
- 밝고 긍정적인 톤
- 한국어 존댓말
"""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.0-flash:generateContent"
    )

    body = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    response = requests.post(url, params={"key": api_key}, json=body)
    try:
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        text = "오늘도 작지만 의미 있는 변화가 이어지고 있어요 😊"

    return text.strip()


# ==========================
# 4) 전체 홈 피드백 통합 생성기
# ==========================
def generate_home_feedback(user_id: str, session: Session):
    user = session.query(User).filter_by(id=user_id).first()
    if not user:
        return {"error": "User not found"}

    # ① 기본 한 줄 헤드라인
    base = simple_headline_builder(user_id, session)

    # ② 자동 패턴 감지
    pat = detect_3day_patterns(user_id, session)

    # ③ 최근 건강 점수
    recent_score = (
        session.query(DailyHealthScore)
        .filter(DailyHealthScore.user_id == user_id)
        .order_by(DailyHealthScore.date.desc())
        .first()
    )
    health_score = recent_score.total_score if recent_score else None

    # ④ AI 감성 피드백
    ai_line = ai_one_liner(
        user_name=user.name,
        health_score=health_score,
        patterns=pat["patterns"],
    )

    # ⑤ 최종 결과 조립
    return {
        "headline": base["headline"],
        "base_code": base["code"],
        "patterns": pat["patterns"],
        "actions": pat["actions"],
        "primary_pattern": pat["primary"],
        "ai_one_liner": ai_line,
        "health_score": health_score,
    }

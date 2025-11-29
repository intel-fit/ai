# src/routers/chat_coach.py

import os
import json
import requests
from datetime import date, timedelta, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.utils.memory_utils import (
    load_memory,
    append_short_term,
    update_mid_term_summary,
    update_long_term_memory,
)
from src.utils.llm_utils import call_gemini


from src import db

router = APIRouter(tags=["Chat Coach"])

# =========================
# DB 세션 의존성
# =========================
def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# =========================
# 요청 스키마
# =========================
class ChatCoachRequest(BaseModel):
    user_id: str
    message: str
    mode: str | None = "auto"         # "auto" | "nutrition" | "exercise"
    coach_style: str | None = "default"  # "pro" | "friend" | "soft" | "drill" | ...





# =========================
#  유저 데이터 수집 유틸
# =========================
def load_user_core(session: Session, user_id: str) -> dict:
    user = session.query(db.User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    core = {
        "user_id": user.id,
        "name": user.name,
        "age": user.age,
        "sex": user.sex,
        "height_cm": user.height,
        "weight_kg": user.weight,
        "body_fat_pct": user.body_fat,
        "skeletal_muscle_kg": user.skeletal_muscle,
        "activity_level": user.activity_level,
        "goal": user.goal,  # "fat_loss", "hypertrophy", "maintenance" 등
    }
    return core


def load_latest_bodycomp(session: Session, user_id: str) -> dict | None:
    """
    최신 인바디/체성분 기록 (BodyCompLog) 1개
    """
    if not hasattr(db, "BodyCompLog"):
        return None

    row = (
        session.query(db.BodyCompLog)
        .filter_by(user_id=user_id)
        .order_by(db.BodyCompLog.date.desc())
        .first()
    )
    if not row:
        return None

    return {
        "date": row.date.isoformat(),
        "weight_kg": row.weight_kg,
        "body_fat_pct": row.body_fat_pct,
        "smm_kg": row.smm_kg,
        "note": row.note,
    }


def load_today_goal(session: Session, user_id: str) -> dict | None:
    """
    오늘 기준 DailyNutritionGoal (우리가 앞에서 만들어둔 테이블)
    없으면 None 반환
    """
    if not hasattr(db, "DailyNutritionGoal"):
        return None

    today = date.today()

    row = (
        session.query(db.DailyNutritionGoal)
        .filter_by(user_id=user_id, date=today)
        .first()
    )
    if not row:
        return None

    return {
        "date": today.isoformat(),
        "target_calorie": row.target_calorie,
        "target_protein": row.target_protein,
        "target_fat": row.target_fat,
        "target_carb": row.target_carb,
    }


def load_recent_nutrition_exercise(session: Session, user_id: str) -> dict:
    """
    최근 7일 영양/운동 요약 (DailyNutritionSummary + DailyExerciseSummary)
    """
    today = date.today()
    start = today - timedelta(days=6)

    if hasattr(db, "DailyNutritionSummary"):
        rows_nut = (
            session.query(db.DailyNutritionSummary)
            .filter(db.DailyNutritionSummary.user_id == user_id)
            .filter(db.DailyNutritionSummary.date >= start)
            .order_by(db.DailyNutritionSummary.date)
            .all()
        )
    else:
        rows_nut = []

    if hasattr(db, "DailyExerciseSummary"):
        rows_ex = (
            session.query(db.DailyExerciseSummary)
            .filter(db.DailyExerciseSummary.user_id == user_id)
            .filter(db.DailyExerciseSummary.date >= start)
            .order_by(db.DailyExerciseSummary.date)
            .all()
        )
    else:
        rows_ex = []

    # 날짜별로 merge
    day_map: dict[str, dict] = {}
    for r in rows_nut:
        d = r.date.isoformat()
        day_map.setdefault(d, {})
        day_map[d]["nutrition"] = {
            "kcal": r.kcal,
            "protein_g": r.protein_g,
            "fat_g": r.fat_g,
            "carb_g": r.carb_g,
            "fiber_g": getattr(r, "fiber_g", 0),
            "sugar_g": getattr(r, "sugar_g", 0),
            "sodium_mg": getattr(r, "sodium_mg", 0),
            "processed_ratio": r.processed_ratio,
            "distinct_main_sources": r.distinct_main_sources,
        }

    for r in rows_ex:
        d = r.date.isoformat()
        day_map.setdefault(d, {})
        day_map[d]["exercise"] = {
            "duration_min": r.duration_min,
            "calories_burned": r.calories_burned,
            "avg_intensity": r.avg_intensity,
        }

    # 7일 모두 채우기 (없는 날은 0 채우기)
    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        ds = d.isoformat()
        row = day_map.get(ds, {})
        days.append(
            {
                "date": ds,
                "nutrition": row.get(
                    "nutrition",
                    {
                        "kcal": 0,
                        "protein_g": 0,
                        "fat_g": 0,
                        "carb_g": 0,
                        "fiber_g": 0,
                        "sugar_g": 0,
                        "sodium_mg": 0,
                        "processed_ratio": 0,
                        "distinct_main_sources": 0,
                    },
                ),
                "exercise": row.get(
                    "exercise",
                    {
                        "duration_min": 0,
                        "calories_burned": 0,
                        "avg_intensity": 0,
                    },
                ),
            }
        )

    return {
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "days": days,
    }


def load_recent_health_scores(session: Session, user_id: str) -> dict | None:
    """
    최근 14일 DailyHealthScore (전체 점수 + nutrition/exercise/balance)
    """
    if not hasattr(db, "DailyHealthScore"):
        return None

    today = date.today()
    start = today - timedelta(days=13)

    rows = (
        session.query(db.DailyHealthScore)
        .filter(db.DailyHealthScore.user_id == user_id)
        .filter(db.DailyHealthScore.date >= start)
        .order_by(db.DailyHealthScore.date)
        .all()
    )

    if not rows:
        return None

    scores = []
    for r in rows:
        scores.append(
            {
                "date": r.date.isoformat(),
                "nutrition_score": r.nutrition_score,
                "exercise_score": r.exercise_score,
                "balance_score": r.balance_score,
                "total_score": r.total_score,
            }
        )

    return {
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "scores": scores,
    }

def detect_user_emotion(message: str) -> str:
    """
    Gemini로 사용자 메시지 감정 분석
    return: "stress" | "fatigue" | "frustration" | "motivation" | "sad" | "neutral"
    """
    emo_prompt = f"""
다음 사용자의 문장을 감정으로 분석해라.
가능한 감정 라벨: ["stress", "fatigue", "frustration", "motivation", "sad", "neutral"]

문장: "{message}"

반환 형식: 감정 라벨만 하나 출력. 다른 말 절대 금지.
"""

    try:
        emotion = call_gemini(emo_prompt).strip().lower()
    except:
        emotion = "neutral"

    # 안전 필터링
    valid = ["stress", "fatigue", "frustration", "motivation", "sad", "neutral"]
    if emotion not in valid:
        emotion = "neutral"

    return emotion


# =========================
# 프롬프트 생성
# =========================
def build_system_prompt(mode: str, coach_style: str | None, emotion: str | None) -> str:
    """
    모드 + 코치 스타일에 따라 역할/말투를 결정.
    coach_style 예시:
      - "pro"    : 전문 PT 코치 스타일
      - "friend" : 친구같이 편한 스타일
      - "soft"   : 부드럽고 위로 중심
      - "drill"  : 강하게 채찍질하는 스타일
      - 그 외/None: 기본 중립 스타일
    """
    # 1) 공통 베이스
    base = """
너는 한국어를 잘하는 개인 건강 코치 AI다.
사용자의 '프로필', '최근 식단/운동 기록', '건강 점수'를 기반으로
현실적이고 구체적인 피드백을 제공해라.

반드시 다음을 지켜라:
- 사용자의 목표(goal)를 항상 고려해서 조언해라.
- 최근 7일 섭취량/운동량에서 눈에 띄는 패턴을 찾아 구체적으로 언급해라.
- 근거가 되는 숫자(칼로리, 단백질 g, 운동시간 등)를 적당히 인용해라.
- 너무 추상적으로 말하지 말고, 오늘/이번주에 바로 실천할 수 있는 액션 아이템을 제안해라.
- 질문이 모호하면, 추가로 무엇을 알고 싶은지 되묻고, 그 후에 답을 이어가라.
"""
    # 감정 기반 톤 수정
    if emotion == "fatigue":
        base += """
[감정 감지: '피곤함']
- 먼저 사용자의 피로감을 공감해라.
- 오늘은 부담을 줄이는 방향으로 조언해라.
- 작은 목표 1~2개만 제시해라.
"""
    elif emotion == "stress":
        base += """
[감정 감지: '스트레스']
- 먼저 사용자의 걱정이나 불안에 공감해라.
- 너무 많은 요구를 하지 말고, 현실적이고 차분하게 안내해라.
"""
    elif emotion == "sad":
        base += """
[감정 감지: '슬픔']
- 격려, 공감 중심으로 조언해라.
- 오늘 할 수 있는 가벼운 목표를 제안해라.
"""
    elif emotion == "frustration":
        base += """
[감정 감지: '좌절']
- 좌절한 이유를 인정해주고 공감해라.
- 실패 분석 후, 다시 시작할 수 있는 간단한 루틴을 제안해라.
"""
    elif emotion == "motivation":
        base += """
[감정 감지: '의욕']
- 도전적인 루틴과 강도를 조금 높인 조언을 해도 된다.
- 긍정적인 강화(Coaching reinforcement)를 강조해라.
"""
    else:
        base += """
[감정 감지: '중립']
- 보통의 톤으로 응답해라.
"""

    # 2) 모드에 따른 포커스
    if mode == "nutrition":
        base += """
지금 모드는 '영양/식단 코치 모드'이다.
- 식단, 영양소, 칼로리, TDEE, 다이어트/벌크 전략에 초점을 맞춰라.
- 운동에 대한 이야기는 간단히만 언급하고, 식단 관련 조언을 중심으로 답해라.
"""
    elif mode == "exercise":
        base += """
지금 모드는 '운동 코치 모드'이다.
- 운동 빈도, 강도, 루틴 구성, 회복, 부상 예방에 초점을 맞춰라.
- 식단 관련 코멘트는 간단히만 언급하고, 운동 관련 조언을 중심으로 답해라.
"""
    else:
        base += """
지금 모드는 '종합 코치 모드(auto)'이다.
- 질문 내용을 보고 식단/운동 중 어느 쪽이 중요한지 판단해서 비중을 나눠라.
"""

    # 3) 코치 스타일에 따른 말투/성향 설정
    style = (coach_style or "default").lower()

    if style == "pro":
        base += """
[코치 스타일: 전문 PT 코치]
- 말투는 전문적이지만 딱딱하지 않게, 존중하면서도 단호하게 말해라.
- 운동/식단 지식을 근거로 '왜 이런 계획이 좋은지' 설명해라.
- "지금 상태라면 ~~하는 게 가장 효율적이야"처럼 방향을 명확히 제시해라.
"""
    elif style == "friend":
        base += """
[코치 스타일: 친구형 코치]
- 말투는 편한 반말, 친한 친구처럼 이야기해라.
- "솔직히", "내가 보기엔", "이 정도면 잘하고 있는 거야" 같은 표현을 적당히 섞어라.
- 너무 혼내기보다는, 응원 + 살짝 잔소리 느낌으로 조언해라.
"""
    elif style == "soft":
        base += """
[코치 스타일: 부드러운 멘토형]
- 말투는 부드럽고 다정하게, 사용자의 감정을 먼저 공감해라.
- "그동안 노력한 것부터 먼저 인정해줄게", "조금씩만 바꿔보자" 같은 표현을 사용해라.
- 부담스럽지 않은 작은 변화부터 제안해라.
"""
    elif style == "drill":
        base += """
[코치 스타일: 강한 코치(드릴 형식)]
- 말투는 직설적이고 강한 편이지만, 인격 모독이나 비하 표현은 절대 쓰지 마라.
- "목표가 분명하면, 지금처럼 하면 안 돼", "이 정도는 해줘야지" 같은 식으로 동기부여를 해라.
- 대신 해결책과 구체적인 행동 계획을 항상 함께 제시해라.
"""
    else:
        base += """
[코치 스타일: 기본 중립형]
- 말투는 친절한 반말, 너무 딱딱하지도, 너무 가볍지도 않게 유지해라.
"""



    # 4) 답변 형식 가이드
    base += """
답변 형식:
1) 한 줄 요약
2) 현재 상태 분석 (숫자/패턴 언급)
3) 오늘부터 실천할 액션 플랜 (bullet 형식)
4) 추가로 점검하면 좋은 것 (선택)

반말/존댓말은 섞지 말고, 자연스러운 반말 톤으로 이야기해라.
"""
    return base.strip()


def build_full_prompt(
    system_prompt: str,
    profile_core: dict,
    bodycomp: dict | None,
    today_goal: dict | None,
    recent_logs: dict,
    recent_scores: dict | None,
    user_message: str,
    memory_data: dict,
) -> str:
    """
    LLM에 넘길 최종 프롬프트 문자열.
    """
    blocks = {
        "user_profile": profile_core,
        "latest_body_comp": bodycomp,
        "today_nutrition_goal": today_goal,
        "recent_7days_logs": recent_logs,
        "recent_14days_health_scores": recent_scores,
        "user_memory": memory_data,
    }

    # JSON으로 직렬화 (한글 안깨지게 ensure_ascii=False)
    context_json = json.dumps(blocks, ensure_ascii=False, indent=2)

    final_prompt = f"""
{system_prompt}

====================[USER CONTEXT JSON]====================
{context_json}
===========================================================

위의 JSON은 사용자의 실제 기록이다. 반드시 참고해서 답변해라.

이제 사용자의 질문은 다음과 같다:

[USER_QUESTION]
{user_message}
"""

    return final_prompt.strip()


# =========================
# 메인 라우터
# =========================
@router.post("/chat/coach", response_class=JSONResponse)
def chat_coach(req: ChatCoachRequest, session: Session = Depends(get_db)):
    # 0. 감정 분석 (새롭게 추가)
    user_emotion = detect_user_emotion(req.message)

    # 0-1. 메모리 로딩
    memory_data = load_memory(session, req.user_id)

    # 0-2. 단기 메모리 추가
    append_short_term(session, req.user_id, req.message, user_emotion)

    # 0-3. 장기 메모리 갱신 시도
    update_long_term_memory(session, req.user_id, req.message)
    # 1. 유저 코어 데이터
    profile_core = load_user_core(session, req.user_id)

    # 2. 최신 인바디 / 체성분
    bodycomp = load_latest_bodycomp(session, req.user_id)

    # 3. 오늘 목표 영양 (있으면)
    today_goal = load_today_goal(session, req.user_id)

    # 4. 최근 7일 섭취/운동 요약
    recent_logs = load_recent_nutrition_exercise(session, req.user_id)

    # 5. 최근 14일 건강 점수
    recent_scores = load_recent_health_scores(session, req.user_id)

    # 6. 시스템 프롬프트 + 전체 프롬프트 구성 (코치 스타일 반영)
    system_prompt = build_system_prompt(req.mode or "auto", req.coach_style or "default", user_emotion)
    full_prompt = build_full_prompt(
        system_prompt=system_prompt,
        profile_core=profile_core,
        bodycomp=bodycomp,
        today_goal=today_goal,
        recent_logs=recent_logs,
        recent_scores=recent_scores,
        user_message=req.message,
        memory_data=memory_data,
    )

    # 7. Gemini 호출
    reply = call_gemini(full_prompt)
    update_mid_term_summary(session, req.user_id, memory_data)

    # 8. 응답
    return JSONResponse(
        content={
            "user_id": req.user_id,
            "mode": req.mode or "auto",
            "coach_style": req.coach_style or "default",
            "emotion_detected": user_emotion,
            "reply": reply,
            "debug": {
                "system_prompt_preview": system_prompt[:300],
                "has_bodycomp": bodycomp is not None,
                "has_today_goal": today_goal is not None,
                "has_recent_scores": recent_scores is not None,
            },
        }
    )

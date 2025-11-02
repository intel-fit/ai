# src/routers/chat_coach.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src import db
from datetime import date, timedelta
import os, requests, json
from src.services.coach import build_weekly_coach_report

router = APIRouter(tags=["AI Coach Chat"])

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("Gemini API key not set in .env")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

# ---------------------------------------------------------------
# 💬 AI 코치 대화 (건강점수 + 리포트 기반)
# ---------------------------------------------------------------
@router.post("/chat/coach", response_model=dict)
def chat_with_coach(user_id: str, message: str, session: Session = Depends(get_db)):
    """
    AI가 최근 점수, 건강 리포트, 인바디, 식단/운동 통계를 종합해 문맥형 답변 제공.
    """

    # -----------------------
    # 1️⃣ 유저 정보
    # -----------------------
    user = session.query(db.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # -----------------------
    # 2️⃣ 주간 리포트 / 점수
    # -----------------------
    report = build_weekly_coach_report(user_id, session)
    metrics = report.get("metrics", {})
    score = metrics.get("health_score", None)

    # 최근 점수 트렌드 (3일치)
    scores = (
        session.query(db.DailyHealthScore)
        .filter_by(user_id=user_id)
        .order_by(db.DailyHealthScore.date.desc())
        .limit(3)
        .all()
    )
    score_text = ""
    if scores:
        score_text = " / ".join([f"{s.date.strftime('%m-%d')} : {s.total_score:.1f}" for s in reversed(scores)])
        latest_score = scores[0].total_score
    else:
        latest_score = None

    # -----------------------
    # 3️⃣ 최신 인바디 (선택)
    # -----------------------
    latest_inbody = (
        session.query(db.BodyCompLog)
        .filter_by(user_id=user_id)
        .order_by(db.BodyCompLog.date.desc())
        .first()
    )
    inbody_str = (
        f"체중 {latest_inbody.weight_kg}kg, 체지방률 {latest_inbody.body_fat_pct}%, 골격근량 {latest_inbody.smm_kg}kg"
        if latest_inbody else "인바디 데이터 없음"
    )

    # -----------------------
    # 4️⃣ AI 프롬프트 구성
    # -----------------------
    system_prompt = f"""
당신은 사용자의 개인 트레이너이자 AI 피트니스 코치입니다.
아래 데이터를 참고해 사용자에게 정확하고 친절하게 대답하세요.

[사용자 프로필]
- 이름: {user.name}, 나이: {user.age}, 성별: {user.sex}
- 목표: {user.goal}
- 활동계수: {user.activity_level}
- 최신 인바디: {inbody_str}

[최근 건강 점수 요약]
- 최근 3일 점수: {score_text or "데이터 없음"}
- 이번 주 평균 점수: {score or "N/A"}점

[최근 7일 요약 데이터]
- 평균 섭취 칼로리: {metrics.get("avg_kcal", "N/A")} kcal
- 단백질: {metrics.get("avg_protein", "N/A")} g, 지방: {metrics.get("avg_fat", "N/A")} g, 탄수화물: {metrics.get("avg_carb", "N/A")} g
- 운동일수: {metrics.get("exercise_days", "N/A")}일, 평균 운동시간: {metrics.get("avg_ex_duration", "N/A")}분, 강도: {metrics.get("avg_ex_intensity", "N/A")}
- 초가공 비율: {metrics.get("processed_ratio", "N/A")}, 평균 나트륨: {metrics.get("avg_sodium_mg", "N/A")} mg

[지시사항]
- 실제 데이터 기반으로 답하세요. 근거 없는 말은 하지 마세요.
- 질문이 점수나 상태 관련이면 수치와 함께 비교 설명을 제공합니다.
- 목표 개선 관련이면 다음 행동 3가지를 구체적으로 제시하세요.
- 말투는 전문 코치이지만 친근하게. 존댓말로.
- 답변은 한국어로 작성하세요.
"""

    user_prompt = f"사용자 질문: {message}"

    payload = {
        "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}]
    }

    headers = {"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY}
    response = requests.post(GEMINI_URL, headers=headers, json=payload)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Gemini API error: {response.text}")

    raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"]

    return {
        "user_id": user_id,
        "question": message,
        "ai_reply": raw_text,
        "context": {
            "latest_score": latest_score,
            "weekly_score": score,
            "avg_protein": metrics.get("avg_protein"),
            "exercise_days": metrics.get("exercise_days")
        }
    }

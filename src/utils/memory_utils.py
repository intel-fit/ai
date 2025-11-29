# src/memory_utils.py

import json
from sqlalchemy.orm import Session
from src.db import Memory
from datetime import datetime


# ---------------------------
# 기본 로딩 함수
# ---------------------------
def load_memory(session: Session, user_id: str) -> dict:
    rows = (
        session.query(Memory)
        .filter(Memory.user_id == user_id)
        .order_by(Memory.id)
        .all()
    )

    mem = {
        "short_term": [],
        "mid_term": {},
        "long_term": {}
    }

    for row in rows:
        data = row.get_json()
        if not data:
            continue

        if row.memory_type == "short":
            mem["short_term"].append({"id": row.id, **data})

        elif row.memory_type == "mid":
            mem["mid_term"].update(data)

        elif row.memory_type == "long":
            mem["long_term"].update(data)

    return mem


# ---------------------------
# 저장 함수
# ---------------------------
def save_memory(session: Session, user_id: str, memory_type: str, data: dict):
    row = Memory(
        user_id=user_id,
        memory_type=memory_type,
        content=json.dumps(data, ensure_ascii=False),
    )
    session.add(row)
    session.commit()

# ============================================================
#  MESSAGE SUMMARIZER (LLM)
# ============================================================
def summarize_message(message: str) -> str:
    """
    사용자의 메시지를 1줄로 강하게 요약.
    단기 메모리 축적 폭발 방지 + LLM 프롬프트 효율 증가 목적.
    """

    prompt = f"""
다음 사용자의 말을 핵심 의미 1줄로 요약해라.
불필요한 감탄사/군더더기/중복 제거.

문장: "{message}"

조건:
- 최대 1줄
- 120자 이내
- 핵심 정보만
"""

    try:
        summary = call_gemini(prompt).strip()
        if len(summary) > 120:
            summary = summary[:120]
    except Exception:
        summary = message[:120]

    return summary


# ---------------------------
# 단기 메모리 추가 (감정 + 메시지)
# ---------------------------
def append_short_term(session: Session, user_id: str, message: str, emotion: str):
    summary = summarize_message(message)
    data = {
        "timestamp": datetime.utcnow().isoformat(),
        "summary": summary,
        "emotion": emotion,
    }
    save_memory(session, user_id, "short", data)

    # short_term 너무 길어지면 자동 요약
    _auto_shorten_short_term(session, user_id)


def _auto_shorten_short_term(session: Session, user_id: str, max_items: int = 10):
    """
    short-term이 10개 초과하면 오래된 것 삭제.
    """
    rows = (
        session.query(Memory)
        .filter_by(user_id=user_id, memory_type="short")
        .order_by(Memory.id)
        .all()
    )

    if len(rows) <= max_items:
        return

    to_delete = rows[:-max_items]
    for r in to_delete:
        session.delete(r)
    session.commit()

# ---------------------------
# 중기 메모리 업데이트
# ---------------------------
def update_mid_term_summary(session: Session, user_id: str, memory_data: dict):
    short_list = memory_data.get("short_term", [])
    if len(short_list) < 8:
        return  # 8개 이상 쌓였을 때만 요약

    messages = [m["summary"] for m in short_list]

    prompt = f"""
다음은 사용자의 최근 단기 대화 요약 리스트이다.
이 대화들의 핵심 패턴/감정/반복되는 주제만 5줄 이내로 압축 요약해라.

대화 요약들:
{json.dumps(messages, ensure_ascii=False)}

조건:
- 5줄 이하
- 핵심 습관/불만/목표/문제/감정 패턴만 남김
"""

    try:
        summary = call_gemini(prompt).strip()
    except:
        summary = "최근 대화 요약 생성 실패."

    # mid-term 저장
    save_memory(session, user_id, "mid", {"summary": summary})

    # short-term 삭제
    for item in short_list:
        row = session.query(Memory).get(item["id"])
        if row:
            session.delete(row)
    session.commit()



# ---------------------------
# 장기 메모리 업데이트
# ---------------------------
def update_long_term_memory(session: Session, user_id: str, message: str):
    """
    사용자가 지속 호소한 문제나 장기 습관/제약 인식.
    """
    patterns = {
        "무릎": "knee_issue",
        "허리": "back_issue",
        "못해": "confidence_low",
        "주말": "weekend_activity_low",
        "피곤": "fatigue_trend",
        "과식": "overeating_tendency",
        "목표": "goal_related_statement"
    }

    stored = {}

    for k, tag in patterns.items():
        if k in message:
            stored[tag] = True

    if stored:
        save_memory(session, user_id, "long", stored)


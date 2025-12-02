# src/services/ai_meal_generator_gemini.py

import os
import json
import requests
from fastapi import HTTPException

# ✅ Gemini API 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("Gemini API key not set in .env")

# ✅ 안정적으로 작동하는 v1beta REST 엔드포인트 (chat_coach.py와 동일)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


# ----------------------------------------------------------
# 🍱 Gemini 기반 현실적 식단 생성기 (REST 호출 방식)
# ----------------------------------------------------------
def generate_realistic_meal_plan(
    user,
    tdee: float,
    macros: dict,
    meals_per_day: int = 3,
    preferred_foods: list[str] | None = None,
    excluded_foods: list[str] | None = None,
    candidate_foods: list[dict] | None = None,   # ✅ 새로 추가
):
    """
    현실적인 식단을 Gemini 2.0 Flash 모델로 생성합니다.
    기존 SDK 대신 REST API로 안정적으로 호출합니다.
    """

    # 선호 / 비선호 텍스트 구성
    prefer_text = ", ".join(preferred_foods or []) or "없음"
    exclude_text = ", ".join(excluded_foods or []) or "없음"

    # 후보 음식 리스트 텍스트 구성 (점수 엔진에서 올라온 상위 음식들)
    if candidate_foods:
        lines = []
        # 너무 길어지지 않도록 상위 50개만 사용
        for c in candidate_foods[:50]:
            name = c.get("name", "이름없음")
            kcal = c.get("calories", 0.0)
            protein = c.get("protein", 0.0)
            fat = c.get("fat", 0.0)
            carbs = c.get("carbs", 0.0)
            score = c.get("score", 0.0)
            lines.append(
                f"- {name} (약 {kcal:.0f}kcal, 단백질 {protein:.1f}g, 지방 {fat:.1f}g, 탄수화물 {carbs:.1f}g, 건강점수 {score:.1f})"
            )
        candidates_text = "\n".join(lines)
    else:
        candidates_text = "별도 후보 리스트 없음 (일반적인 건강식 위주로 구성하세요.)"

    # ----------------------------------------------------------
    # 🧠 프롬프트 구성
    # ----------------------------------------------------------
    prompt = f"""
    당신은 피트니스 전문 영양사입니다.
    아래의 사용자 정보를 참고하여 한국인이 실제 먹을 수 있는 하루 식단을 JSON으로 작성하세요.

    [사용자 정보]
    - 성별: {user.sex}
    - 나이: {user.age}세
    - 키: {user.height}cm
    - 몸무게: {user.weight}kg
    - 목표: {user.goal} (예: lean / bulk / maintain)
    - 하루 권장 섭취 칼로리: {tdee:.0f} kcal
    - 목표 매크로: 단백질 {macros['protein']:.1f}g, 지방 {macros['fat']:.1f}g, 탄수화물 {macros['carb']:.1f}g
    - 하루 식사 횟수: {meals_per_day} 끼

    [사용자 선호 음식]
    {prefer_text}

    [사용자 비선호 음식 및 제외할 재료]
    {exclude_text}

    [추천 후보 음식 리스트]
    {candidates_text}

    가능하면 위의 후보 음식들만 사용해서 식단을 구성하세요.
    특히 건강점수가 높은 음식들을 우선 사용하고,
    후보에 없는 음식 이름은 가급적 사용하지 마세요.

    [식단 구성 규칙]
    1. 현실적으로 구할 수 있는 식재료를 사용하세요. (닭가슴살, 연어, 계란, 현미밥 등)
    2. 소스류, 과자, 음료, 디저트, 보충제, 영양제 등은 절대 포함하지 마세요.
    3. 각 끼니에는 3~4개의 음식이 포함되어야 합니다.
    4. 각 음식은 다음 정보를 포함합니다:
       - name: 음식 이름
       - amount_g: 대략적인 양 (g)
       - calories: 칼로리 (kcal)
       - protein: 단백질 (g)
       - fat: 지방 (g)
       - carb: 탄수화물 (g)
    5. JSON만 출력하세요. 설명이나 코드블록(````json`)은 포함하지 마세요.

    [출력 예시]
    {{
      "goal": "lean",
      "total_kcal": 2250,
      "meals": [
        {{
          "meal_type": "meal_1",
          "foods": [
            {{"name": "닭가슴살 150g", "amount_g": 150, "calories": 220, "protein": 31, "fat": 3, "carb": 0}},
            {{"name": "현미밥 150g", "amount_g": 150, "calories": 240, "protein": 5, "fat": 1, "carb": 54}},
            {{"name": "브로콜리 100g", "amount_g": 100, "calories": 30, "protein": 3, "fat": 0, "carb": 6}}
          ]
        }},
        ...
      ]
    }}
    """

    # ----------------------------------------------------------
    # 🛰️ Gemini API 호출
    # ----------------------------------------------------------
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY,
    }

    response = requests.post(GEMINI_URL, headers=headers, json=payload)

    if response.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Gemini API 호출 실패: {response.text}",
        )

    # ----------------------------------------------------------
    # 📦 결과 파싱
    # ----------------------------------------------------------
    try:
        raw_text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Gemini가 종종 markdown 형태(````json ... ````)로 반환 → 정리
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("```json").strip("```").strip()

        # JSON 파싱 시도
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        parsed_json = raw_text[start:end]
        meal_plan = json.loads(parsed_json)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gemini 응답 파싱 실패: {str(e)}\n응답 원문: {raw_text[:400]}...",
        )

    return meal_plan

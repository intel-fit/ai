from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from src import db
from src.usda_api import search_usda_food
from src.schemas import FoodOut, MealLogOut, MealItemOut
import os
import json
import re
import requests
from dotenv import load_dotenv
from datetime import datetime
from typing import List,  Optional
# 맨 위에 추가
from src.services.summary import recompute_daily_summaries
import hashlib
from io import BytesIO
from PIL import Image
# ⬇️ import 블록 바로 아래에 추가
from googletrans import Translator
translator = Translator()
_translate_cache = {}

def ko(name_en: str) -> str:
    if not name_en:
        return name_en
    try:
        if name_en in _translate_cache:
            return _translate_cache[name_en]
        txt = translator.translate(name_en, src="en", dest="ko").text
        _translate_cache[name_en] = txt
        return txt
    except Exception:
        # 번역 실패 시 영어 그대로 반환
        return name_en





load_dotenv()
router = APIRouter(tags=["Food"])

# ----------------------
# DB 연결
# ----------------------
def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

# ----------------------
# Gemini API 설정
# ----------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("Gemini API key not set in .env")

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# ----------------------
# Azure Computer Vision 설정
# ----------------------
AZURE_CV_KEY = os.getenv("AZURE_COMPUTER_VISION_KEY")
AZURE_CV_ENDPOINT = os.getenv("AZURE_COMPUTER_VISION_ENDPOINT")
if not AZURE_CV_KEY or not AZURE_CV_ENDPOINT:
    raise RuntimeError("Azure Computer Vision API info not set in .env")

AZURE_ANALYZE_URL = (
    f"{AZURE_CV_ENDPOINT}/vision/v3.2/analyze"
    "?visualFeatures=Description,Tags,Objects,Categories"
)


# ----------------------
# 음식 검색 (DB + USDA)
# ----------------------
@router.get("/search", response_model=list[FoodOut])
def search_food(name: str, session: Session = Depends(get_db)):
    results = session.query(db.Food).filter(db.Food.name.contains(name)).all()
    if results:
        return results

    usda_data = search_usda_food(name)
    if usda_data and "foods" in usda_data:
        added_foods = []
        for item in usda_data["foods"]:
            food = db.Food(
                name=item.get("description"),
                calories=item.get("foodNutrients", [{}])[0].get("value", 0),
                carbs=0,
                protein=0,
                fat=0,
                company="해당없음",
                weight=100.0  # ✅ 기본값
            )
            session.add(food)
            added_foods.append(food)
        session.commit()
        return added_foods

    return [{"name": name, "direct_input_needed": True}]

# ----------------------
# 수동 입력 음식 추가
# ----------------------
class ManualFoodInput(BaseModel):
    name: str
    weight: float = 100.0
    calories: float = 0
    carbs: float = 0
    protein: float = 0
    fat: float = 0

@router.post("/add_manual_food", response_model=FoodOut)
def add_manual_food(food_input: ManualFoodInput, session: Session = Depends(get_db)):
    food = db.Food(
        name=food_input.name,
        calories=food_input.calories,
        carbs=food_input.carbs,
        protein=food_input.protein,
        fat=food_input.fat,
        weight=food_input.weight,
        company="직접입력"
    )
    session.add(food)
    session.commit()
    session.refresh(food)
    return food

# ----------------------
# AI 인식 (이미지 업로드)
# ----------------------
@router.post("/upload_food", response_model=dict)
async def upload_food(file: UploadFile = File(...), session: Session = Depends(get_db)):
    """
    ✅ 개선 버전: Azure + Gemini 기반 AI 음식 인식 (다중 음식 + 리사이즈 + 캐싱)
    - 큰 이미지 자동 리사이즈 (800px 기준)
    - 동일 이미지 해시로 캐싱 (DB에 이미 있으면 재요청 X)
    - Azure Objects 분석으로 다중 음식 감지
    """
    # 1️⃣ 이미지 읽기
    img_bytes = await file.read()
    if not img_bytes or len(img_bytes) < 1024:
        raise HTTPException(status_code=400, detail="Empty or invalid image file (0 bytes)")

    # 2️⃣ 이미지 캐싱용 해시 계산 (SHA256)
    img_hash = hashlib.sha256(img_bytes).hexdigest()
    existing_foods = session.query(db.Food).filter_by(company=img_hash).all()
    if existing_foods:
        print(f"[CACHE HIT] 동일 이미지 해시: {img_hash}")
        return {
            "ai_result": [
              {
                "name_en": f.name,
                "name_ko": ko(f.name),
                "calories": f.calories,
                "carbs": f.carbs,
                "protein": f.protein,
                "fat": f.fat,
                "weight": f.weight,
                "total_weight": 350,
                "total_calories": round(f.calories * (350 / (f.weight or 100.0)), 2)
              }
              for f in existing_foods
            ]
        }

    # 3️⃣ 리사이즈 (너무 큰 이미지 비용 절감)
    try:
        image = Image.open(BytesIO(img_bytes))
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")  # ✅ RGBA, P 모드 모두 JPEG 가능하게 변환
        image.thumbnail((800, 800))

        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        img_bytes = buffer.getvalue()
        buffer.close()
        del image

    except Exception as e:
        print(f"[WARN] Image resize skipped: {e}")

    print(f"[DEBUG] Uploaded file name: {file.filename}")
    print(f"[DEBUG] Uploaded file type: {file.content_type}")
    print(f"[DEBUG] Byte size before Azure: {len(img_bytes)}")


    # 4️⃣ Azure Vision 요청 (다중 visualFeatures)
    headers = {"Ocp-Apim-Subscription-Key": AZURE_CV_KEY, "Content-Type": "application/octet-stream"}
    response = requests.post(AZURE_ANALYZE_URL, headers=headers, data=img_bytes)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Azure CV API failed: {response.text}")

    azure_result = response.json()
    description = azure_result.get("description", {}).get("captions", [{}])[0].get("text", "")
    tags = [t.get("name") for t in azure_result.get("tags", []) if t.get("name")]
    objects = azure_result.get("objects", [])
    categories = [c.get("name") for c in azure_result.get("categories", []) if c.get("name")]

    if not description and not tags:
        raise HTTPException(status_code=400, detail="Azure CV returned insufficient info")

    object_names = [o.get("object") for o in objects if o.get("object")]
    print(f"[Azure→Gemini] Description: {description}")
    print(f"[Azure→Gemini] Tags: {tags}")
    print(f"[Azure→Gemini] Objects: {object_names}")
    print(f"[Azure→Gemini] Categories: {categories}")

    # 5️⃣ Gemini 프롬프트 (한글 + 총중량 포함)
    if len(object_names) > 1:
        prompt = f"""
        You are a food recognition and nutrition estimation expert.
        The image below was analyzed by Azure Computer Vision.
        Detected foods: {', '.join(object_names)}
        Tags: {', '.join(tags)}
        Description: {description}

        Your goal:
        Estimate the nutritional information for the **entire visible food** in the photo,
        not per serving — but for the total portion in the image.

        For each food detected, return a JSON array containing:
        [
          {{
            "name": "Fried Chicken",
            "calories": 250,           # per 100g
            "carbs": 10,
            "protein": 22,
            "fat": 14,
            "weight": 100,             # base unit
            "total_weight": 980,       # total weight visible in the image (grams)
            "total_calories": 2450     # total calories for that visible portion
          }}
        ]

        Rules:
        - Provide reasonable estimates for the total visible portion in grams.
        - If the food is clearly a single portion (like one hamburger), estimate the total burger weight.
        - If it’s a shared food (like fried chicken pieces), sum all visible items.
        - Do NOT use “per serving” — use the **photo total**.
        """

    else:
        prompt = f"""
        You are a food recognition and nutrition estimation expert.

        Azure Computer Vision detected:
        - Description: {description}
        - Tags: {', '.join(tags)}
        - Objects: {', '.join(object_names)}
        - Categories: {', '.join(categories)}

        Estimate:
        1. The food name in English.
        2. Nutritional values per 100g.
        3. The **total visible portion** in the image (total_weight, in grams).
        4. The total calories for that visible portion.

        Return strictly as JSON:
        {{
        "name": "Korean Fried Chicken",
        "calories": 290,
        "carbs": 15,
        "protein": 25,
        "fat": 18,
        "weight": 100,
        "total_weight": 950,
        "total_calories": 2755
        }}

        Rules:
        - total_weight = estimated total visible amount in the photo (grams).
        - total_calories = total calories for that portion.
        - Do NOT assume one serving (no “1인분”). Estimate the real total portion size shown.
        """


    # 6️⃣ Gemini 호출
    headers = {"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    gemini_response = requests.post(GEMINI_URL, headers=headers, json=payload)
    if gemini_response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Gemini API failed: {gemini_response.text}")

    raw_text = gemini_response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    if not raw_text:
        raise HTTPException(status_code=400, detail="Gemini returned empty response")

    # 7️⃣ JSON 파싱 (단일 or 다중)
    json_match = re.search(r"```json\s*(\[.*?\]|\{.*?\})\s*```", raw_text, re.DOTALL)
    fallback_match = re.search(r"(\[.*\]|\{.*\})", raw_text, re.DOTALL)
    json_text = json_match.group(1) if json_match else (fallback_match.group(1) if fallback_match else None)
    if not json_text:
        raise HTTPException(status_code=400, detail="Gemini result could not be parsed")

    try:
        result = json.loads(json_text)
    except Exception:
        raise HTTPException(status_code=400, detail="Gemini JSON parsing failed")

    # 8️⃣ DB 저장 (다중 음식 지원)
    saved_foods = []
    if isinstance(result, list):  # 여러 음식
        for item in result:
            if not isinstance(item, dict) or "name" not in item:
                continue
            existing_food = session.query(db.Food).filter_by(name=item["name"], company=img_hash).first()
            if existing_food:
                saved_foods.append(existing_food)
                continue
            food_item = db.Food(
                name=item.get("name", "Unknown"),
                company=img_hash,  # 해시를 company에 저장해서 캐싱 키로 사용
                calories=item.get("calories", 0),
                carbs=item.get("carbs", 0),
                protein=item.get("protein", 0),
                fat=item.get("fat", 0),
                weight=item.get("weight", 100.0)
            )
            session.add(food_item)
            saved_foods.append(food_item)
    else:  # 단일 음식
        existing_food = session.query(db.Food).filter_by(name=result["name"], company=img_hash).first()
        if existing_food:
            saved_foods.append(existing_food)
        else:
            food_item = db.Food(
                name=result.get("name", "Unknown"),
                company=img_hash,
                calories=result.get("calories", 0),
                carbs=result.get("carbs", 0),
                protein=result.get("protein", 0),
                fat=result.get("fat", 0),
                weight=result.get("weight", 100.0)
            )
            session.add(food_item)
            saved_foods.append(food_item)

    session.commit()
    print(f"[DEBUG] Uploaded file name: {file.filename}")
    print(f"[DEBUG] Uploaded file type: {file.content_type}")

    


    return {
    "ai_result": [
        {
            "name": f.name,
            "name_ko": ko(f.name),
            "calories": f.calories,
            "carbs": f.carbs,
            "protein": f.protein,
            "fat": f.fat,
            "weight": f.weight,
            "total_weight": getattr(f, "total_weight", None),  # ✅ AI가 준 값
            "total_calories": getattr(f, "total_calories", None)  # ✅ AI가 준 값

        }
        for f in saved_foods
    ]
}


# ----------------------
# 음식 추가 (끼니별)
# ----------------------
@router.post("/add_food_to_meal", response_model=dict)
async def add_food_to_meal(
    
    user_id: str = Form(...),
    date: str = Form(...),
    quantity_g: float | None = Form(None, gt=0),
    servings: float | None = Form(None, gt=0),
    meal_id: int | None = Form(None),
    meal_name: str | None = Form(None),   # 프론트에서 주는 끼니 이름
    time_taken: str | None = Form(None),  # 끼니 먹은 시간
    food_id: int | None = Form(None),
    manual_food: str | None = Form(None),
    file: UploadFile | None = File(None),
    session: Session = Depends(get_db)
):
    ai_total_weight: float | None = None
    ai_total_calories: float | None = None
    # 1️⃣ 끼니 선택 or 생성
    # 1️⃣ 끼니 선택 또는 생성
    if meal_id:
        meal = session.query(db.MealLog).filter_by(id=meal_id, user_id=user_id).first()
        if not meal:
            raise HTTPException(status_code=404, detail="Meal ID not found")

        # 시간 수정 요청이 있을 경우 업데이트
        if time_taken:
            meal.time_taken = time_taken
            session.commit()

    else:
        if not meal_name:
            raise HTTPException(status_code=400, detail="meal_name is required when meal_id is not provided.")

        meal_date = datetime.strptime(date, "%Y-%m-%d").date()

        # 같은 날짜 + 같은 이름의 끼니 있는지 확인
        meal = (
            session.query(db.MealLog)
            .filter_by(user_id=user_id, date=meal_date, meal_name=meal_name)
            .first()
        )

        # 없으면 새로 생성
        if not meal:
            meal = db.MealLog(
                user_id=user_id,
                date=meal_date,
                meal_name=meal_name,
                time_taken=time_taken,     # 새로 생성이면 같이 저장
            )
            session.add(meal)
            session.commit()
            session.refresh(meal)

        else:
            # 끼니는 있는데 시간만 새로 들어온 경우 → 업데이트
            if time_taken:
                meal.time_taken = time_taken
                session.commit()

    # 끼니 정보 디버깅
    print(f"[Meal] id={meal.id}, name={meal.meal_name}, time={meal.time_taken}")


    # 2️⃣ 음식 처리
    food_item = None

    if food_id:
        food_item = session.query(db.Food).get(food_id)
        if not food_item:
            raise HTTPException(status_code=404, detail="Food ID not found")

    elif manual_food:
        try:
            mf_data = json.loads(manual_food)
            mf = ManualFoodInput(**mf_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"manual_food must be valid JSON: {str(e)}")
        food_item = db.Food(
            name=mf.name,
            calories=mf.calories,
            carbs=mf.carbs,
            protein=mf.protein,
            fat=mf.fat,
            weight=mf.weight,
            company="직접입력"
        )
        session.add(food_item)
        session.commit()
        session.refresh(food_item)
        # ✅ 요약 재계산 훅
        recompute_daily_summaries(user_id, meal.date, session)

    elif file:
        # 1️⃣ 이미지 읽기
        img_bytes = await file.read()
        if not img_bytes or len(img_bytes) < 1024:
            raise HTTPException(status_code=400, detail="Empty or invalid image file (0 bytes)")

        # 2️⃣ 해시 캐싱 (같은 사진 여러 번 올릴 때 API 중복 방지)
        img_hash = hashlib.sha256(img_bytes).hexdigest()
        existing_foods = session.query(db.Food).filter_by(company=img_hash).all()
        if existing_foods:
            print(f"[CACHE HIT:add_food_to_meal] 동일 이미지: {img_hash}")
            food_item = existing_foods[0]  # 대표 음식 하나만 등록
        else:
            # 3️⃣ 리사이즈 (Azure 비용 절감)
            try:
                image = Image.open(BytesIO(img_bytes))
                image.thumbnail((800, 800))
                buffer = BytesIO()
                image.save(buffer, format="JPEG", quality=90)
                img_bytes = buffer.getvalue()
                buffer.close()
                del image

            except Exception as e:
                print(f"[WARN] 이미지 리사이즈 스킵: {e}")

            # 4️⃣ Azure Vision 호출
            headers = {"Ocp-Apim-Subscription-Key": AZURE_CV_KEY, "Content-Type": "application/octet-stream"}
            response = requests.post(AZURE_ANALYZE_URL, headers=headers, data=img_bytes)
            if response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Azure CV API failed: {response.text}")

            azure_result = response.json()
            description = azure_result.get("description", {}).get("captions", [{}])[0].get("text", "")
            tags = [tag.get("name") for tag in azure_result.get("tags", []) if tag.get("name")]
            objects = [obj.get("object") for obj in azure_result.get("objects", []) if obj.get("object")]
            categories = [cat.get("name") for cat in azure_result.get("categories", []) if cat.get("name")]

            if not description and not tags and not objects:
                raise HTTPException(status_code=400, detail="Azure CV returned insufficient info")

            print(f"[Azure→Gemini:add_food_to_meal] Description: {description}")
            print(f"[Azure→Gemini:add_food_to_meal] Tags: {tags}")
            print(f"[Azure→Gemini:add_food_to_meal] Objects: {objects}")

            # 5️⃣ Gemini 프롬프트 (다중 음식 대응)
            if len(objects) > 1:
                prompt = f"""
                You are a food recognition and nutrition estimation expert.
                The image was analyzed by Azure Computer Vision.
                Detected foods: {', '.join(objects)}
                Tags: {', '.join(tags)}
                Description: {description}

                Estimate the total visible portion (not per serving) for each food detected.
                Return a JSON array with the following fields:

                [
                  {{
                    "name": "Fried Chicken",
                    "calories": 250,      # per 100g
                    "carbs": 10,
                    "protein": 22,
                    "fat": 14,
                    "weight": 100,
                    "total_weight": 980,  # total visible weight (g)
                    "total_calories": 2450
                  }}
                ]

                Rules:
                - total_weight: estimated **actual total weight of food visible in the image (grams)**.
                - total_calories: total calories for that full portion.
                - Do not assume one serving or 350g. Use the real portion visible in the image.
                """
            else:
                prompt = f"""
                You are a food recognition and nutrition estimation expert.

                Azure Computer Vision detected:
                - Description: {description}
                - Tags: {', '.join(tags)}
                - Objects: {', '.join(objects)}
                - Categories: {', '.join(categories)}

                Estimate the food's name (in English),
                nutrients per 100g,
                and the total visible amount of food in the image.

                Return JSON like:
                {{
                "name": "Korean Fried Chicken",
                "calories": 290,
                "carbs": 15,
                "protein": 25,
                "fat": 18,
                "weight": 100,
                "total_weight": 950,
                "total_calories": 2755
                }}

                Rules:
                - total_weight = estimated total visible portion in the photo (grams).
                - total_calories = total calories for that total portion.
                - Do not use a fixed serving size (like 350g); base it on the photo.
                """

            headers = {"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY}
            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            gemini_response = requests.post(GEMINI_URL, headers=headers, json=payload)
            if gemini_response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Gemini API failed: {gemini_response.text}")

            raw_text = gemini_response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            json_match = re.search(r"```json\s*(\[.*?\]|\{.*?\})\s*```", raw_text, re.DOTALL)
            fallback_match = re.search(r"(\[.*\]|\{.*\})", raw_text, re.DOTALL)
            json_text = json_match.group(1) if json_match else (fallback_match.group(1) if fallback_match else None)
            if not json_text:
                raise HTTPException(status_code=400, detail="Gemini result could not be parsed")

            try:
                result = json.loads(json_text)
            except:
                raise HTTPException(status_code=400, detail="Gemini JSON parsing failed")

            # 6️⃣ DB 저장 (다중 음식 지원)
            if isinstance(result, list):
                # 여러 음식 중 첫 번째만 등록 (UI에서 선택 기능이 생기면 확장)
                first = result[0]
                food_item = db.Food(
                    name=first.get("name", "Unknown"),
                    company=img_hash,
                    calories=first.get("calories", 0),
                    carbs=first.get("carbs", 0),
                    protein=first.get("protein", 0),
                    fat=first.get("fat", 0),
                    weight=first.get("weight", 100.0)
                )
                # ⬇️ AI가 준 1인분 총중량(없으면 350g)
                ai_total_weight = float(first.get("total_weight")) if first.get("total_weight") else None
            else:
                food_item = db.Food(
                    name=result.get("name", "Unknown"),
                    company=img_hash,
                    calories=result.get("calories", 0),
                    carbs=result.get("carbs", 0),
                    protein=result.get("protein", 0),
                    fat=result.get("fat", 0),
                    weight=result.get("weight", 100.0)
                )
                # ⬇️ AI가 준 1인분 총중량(없으면 350g)
                ai_total_weight = float(first.get("total_weight")) if first.get("total_weight") else None

            session.add(food_item)
            session.commit()
            session.refresh(food_item)

            if isinstance(result, list):
                first = result[0]
                ai_total_calories = (
                    float(first.get("total_calories"))
                    if first.get("total_calories")
                    else round(float(food_item.calories) * (ai_total_weight / (food_item.weight or 100.0)), 2)
                    if ai_total_weight else None
                )
            else:
                ai_total_calories = (
                    float(result.get("total_calories"))
                    if result.get("total_calories")
                    else round(float(food_item.calories) * (ai_total_weight / (food_item.weight or 100.0)), 2)
                    if ai_total_weight else None
                )


            print(f"[AI 1인분] {food_item.name} : {ai_total_weight} g ≈ {ai_total_calories} kcal")

        # ✅ 요약 재계산 훅
        recompute_daily_summaries(user_id, meal.date, session)

    base_weight = getattr(food_item, "serving_size_g", None) or food_item.weight or 100.0

    # 두 값 모두 입력 시 오류
    if quantity_g and servings:
        raise HTTPException(status_code=400, detail="Please provide only one of 'quantity_g' or 'servings', not both.")

    # 두 값 모두 비어 있으면 → 기본값: 1인분 기준
    if not quantity_g and not servings:
        servings = 1
        quantity_g = base_weight

    # 인분 입력 시 → 중량 자동 계산
    elif servings and not quantity_g:
        quantity_g = servings * base_weight

    # 중량 입력 시 → 인분 자동 계산
    elif quantity_g and not servings:
        servings = quantity_g / base_weight




    # 3️⃣ MealItem 추가
    meal_item = db.MealItem(meal_id=meal.id, food_id=food_item.id, quantity_g=quantity_g)
    session.add(meal_item)
    session.commit()
    session.refresh(meal_item)

    # ✅ ratio 계산
    ratio = quantity_g / (getattr(food_item, "serving_size_g", None) or food_item.weight or 100.0)


    # ✅ 요약 재계산 훅
    recompute_daily_summaries(user_id, meal.date, session)

    # ✅ 실제 섭취량 비율 계산 (조회 로직과 동일하게)
    # ✅ 섭취량 계산 로직 (serving_size_g 반영)
    # ✅ 섭취량 계산 (중량 or 인분 중 하나만 입력)
    # ✅ 섭취량 계산 (서빙 단위 연동 및 기본값 처리)
    

    # ✅ 음식 전체 영양정보 반환
    return {
        "meal_id": meal.id,
        "meal_name": meal.meal_name,
        "time_taken": meal.time_taken,
        "food_added": {
            "id": food_item.id,
            "name": food_item.name,
            "name_ko": ko(food_item.name),
            "company": food_item.company,
            "calories_per_100g": food_item.calories,
            "carbs_per_100g": food_item.carbs,
            "protein_per_100g": food_item.protein,
            "fat_per_100g": food_item.fat,
            "base_weight": food_item.weight,
            "serving_size_g": base_weight,        # ✅ 1인분 기준 중량
            "servings": round(servings, 2),       # ✅ 실제 인분 수
            "quantity_g": round(quantity_g, 1),   # ✅ 실제 g 단위 중량

            # ⬇️ 여기 추가: AI 1인분 기준(파일 업로드로 추가했을 때만 값이 있음)
            "total_weight": ai_total_weight,      # 예: 350.0 또는 None
            "total_calories": ai_total_calories,  # 예: 1120.0 또는 None
            # ✅ 실제 섭취량 반영 값
            "calories_total": food_item.calories * ratio,
            "carbs_total": food_item.carbs * ratio,
            "protein_total": food_item.protein * ratio,
            "fat_total": food_item.fat * ratio
        },
        "quantity_g": quantity_g
    }




@router.get("/get_meals", response_model=List[MealLogOut])
def get_meals(user_id: str, date: str, session: Session = Depends(get_db)):
    meal_date = datetime.strptime(date, "%Y-%m-%d").date()
    meals = session.query(db.MealLog)\
    .filter_by(user_id=user_id, date=meal_date)\
    .order_by(db.MealLog.meal_name.asc())\
    .all()

    result = []

    for meal in meals:
        items_out = []
        for mi in meal.items:
            food = session.query(db.Food).get(mi.food_id)
            base_weight = food.weight or 100.0
            ratio = mi.quantity_g / base_weight

            items_out.append(MealItemOut(
                meal_item_id=mi.id,
                food_id=food.id,
                food_name=food.name,
                quantity_g=mi.quantity_g,
                calories=food.calories * ratio,
                carbs=food.carbs * ratio,
                protein=food.protein * ratio,
                fat=food.fat * ratio
            ))
        result.append(MealLogOut(
            meal_id=meal.id,
            meal_name=meal.meal_name,
            time_taken=meal.time_taken,
            items=items_out
        ))
    return result


#음식 삭제 API 추가 (MealItem 단위 삭제)
@router.delete("/delete_meal_item", response_model=dict)
def delete_meal_item(
    meal_item_id: int,
    user_id: str,
    session: Session = Depends(get_db)
):
    meal_item = session.query(db.MealItem).get(meal_item_id)
    if not meal_item:
        raise HTTPException(status_code=404, detail="Meal item not found")

    meal = session.query(db.MealLog).get(meal_item.meal_id)
    if not meal or meal.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    session.delete(meal_item)
    session.commit()

    return {"status": "success", "deleted_meal_item_id": meal_item_id}

#음식 수정 API 
@router.put("/update_meal_item", response_model=dict)
def update_meal_item(
    meal_item_id: int,
    user_id: str,
    quantity_g: float | None = Form(None),
    servings: float | None = Form(None),
    session: Session = Depends(get_db)
):
    meal_item = session.query(db.MealItem).get(meal_item_id)
    if not meal_item:
        raise HTTPException(status_code=404, detail="Meal item not found")

    meal = session.query(db.MealLog).get(meal_item.meal_id)
    if not meal or meal.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    food = session.query(db.Food).get(meal_item.food_id)
    base_weight = food.weight or 100.0

    # 둘 다 들어오면 오류
    if quantity_g and servings:
        raise HTTPException(status_code=400, detail="Provide only one of quantity_g or servings")

    # g 수정
    if quantity_g:
        meal_item.quantity_g = quantity_g

    # 인분 수정
    elif servings:
        meal_item.quantity_g = servings * base_weight

    else:
        raise HTTPException(status_code=400, detail="No update value provided")

    session.commit()

    # 누적 요약 재계산
    recompute_daily_summaries(user_id, meal.date, session)

    return {
        "status": "updated",
        "meal_item_id": meal_item.id,
        "new_quantity_g": meal_item.quantity_g
    }


#끼니 삭제 기능 (Meal 자체 삭제)
@router.delete("/delete_meal", response_model=dict)
def delete_meal(
    meal_id: int,
    user_id: str,
    session: Session = Depends(get_db)
):
    meal = session.query(db.MealLog).get(meal_id)
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    if meal.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not allowed")

    session.delete(meal)
    session.commit()

    return {"status": "deleted", "meal_id": meal_id}

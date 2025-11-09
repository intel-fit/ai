from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from src import db
from src.usda_api import search_usda_food
from src.schemas import FoodOut
import os
import json
import re
import requests
from dotenv import load_dotenv
from datetime import datetime
from typing import List
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
        image.thumbnail((800, 800))  # 최대 800px로 축소
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        img_bytes = buffer.getvalue()
    except Exception as e:
        print(f"[WARN] Image resize skipped: {e}")

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
        You are a nutrition expert and food recognition specialist.
        The image was analyzed by Azure Computer Vision.
        Detected foods: {', '.join(object_names)}
        Tags: {', '.join(tags)}
        Description: {description}

        For each food, return a JSON array with fields:
        - name (English)
        - calories, carbs, protein, fat (per 100g)
        - weight (100)
        - total_weight (serving size in grams)
        - total_calories (per serving)

        Example:
        [
          {{
            "name": "Grilled Salmon",
            "calories": 208,
            "carbs": 0,
            "protein": 20,
            "fat": 13,
            "weight": 100,
            "total_weight": 180,
            "total_calories": 374
          }}
        ]
        """
    else:
        prompt = f"""
        You are a nutrition expert and food recognition specialist.

        Azure Computer Vision detected:
        - Description: {description}
        - Tags: {', '.join(tags)}
        - Objects: {', '.join(object_names)}
        - Categories: {', '.join(categories)}

        Estimate the food's English name, nutrients per 100g, and a typical serving size.

        Return this JSON:
        {{
        "name": "Grilled Salmon",
        "calories": 208,
        "carbs": 0,
        "protein": 20,
        "fat": 13,
        "weight": 100,
        "total_weight": 180,
        "total_calories": 374
        }}
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
            "total_weight": getattr(f, "total_weight", 350),
            "total_calories": round(f.calories * (getattr(f, "total_weight", 350) / (f.weight or 100.0)), 2)
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
    quantity_g: float = Form(..., gt=0),
    meal_id: int | None = Form(None),
    food_id: int | None = Form(None),
    manual_food: str | None = Form(None),
    file: UploadFile | None = File(None),
    session: Session = Depends(get_db)
):
    ai_total_weight: float | None = None
    ai_total_calories: float | None = None
    # 1️⃣ 끼니 선택 or 생성
    if meal_id:
        meal = session.query(db.MealLog).filter_by(id=meal_id, user_id=user_id).first()
        if not meal:
            raise HTTPException(status_code=404, detail="Meal ID not found")
    else:
        meal_date = datetime.strptime(date, "%Y-%m-%d").date()
        last_meal = (
            session.query(db.MealLog)
            .filter_by(user_id=user_id, date=meal_date)
            .order_by(db.MealLog.meal_number.desc())
            .first()
        )
        next_number = 1 if not last_meal else last_meal.meal_number + 1
        meal = db.MealLog(user_id=user_id, date=meal_date, meal_number=next_number)
        session.add(meal)
        session.commit()
        session.refresh(meal)
        # ✅ 요약 재계산 훅
        recompute_daily_summaries(user_id, meal.date, session)

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
                너는 한국 음식을 포함한 전 세계 요리에 대한 영양 전문가이자 음식 인식 전문가야.

                이 이미지는 Azure Computer Vision으로 분석된 음식 사진이야.
                감지된 음식 객체 목록: {', '.join(objects)}
                태그: {', '.join(tags)}
                설명: {description}

                각 음식에 대해 다음 정보를 추정해서 JSON 배열로 반환해줘:
                ```json
                [
                  {{
                    "name": "음식명 (한국어)",
                    "calories": 0,
                    "carbs": 0,
                    "protein": 0,
                    "fat": 0,
                    "weight": 100,
                    "total_weight": 0,
                    "total_calories": 0
                  }}
                ]
                ```
                규칙:
                - 모든 음식 이름은 반드시 한국어로.
                - 영양성분은 100g 기준으로 작성.
                - total_weight는 1인분 기준 (예: 밥 250g, 김치찌개 350g 등).
                - total_calories는 1인분 기준 총 칼로리.
                """
            else:
                prompt = f"""
                너는 한국 음식을 포함한 전 세계 요리에 대한 영양 전문가이자 음식 인식 전문가야.

                다음은 Azure Computer Vision의 분석 결과야:
                - 설명: {description}
                - 태그: {', '.join(tags)}
                - 감지된 객체: {', '.join(objects)}
                - 카테고리: {', '.join(categories)}

                이를 기반으로 실제 음식의 이름(한국어로),
                100g 기준 영양성분, 그리고 1인분 기준 총중량(total_weight)을 추정해.

                반드시 아래 JSON 형식으로 반환해:
                ```json
                {{
                  "name": "음식명 (한국어)",
                  "calories": 0,
                  "carbs": 0,
                  "protein": 0,
                  "fat": 0,
                  "weight": 100,
                  "total_weight": 0,
                  "total_calories": 0
                }}
                ```
                규칙:
                - name은 반드시 한국어로 (예: 햄버거, 비빔밥, 된장찌개).
                - weight는 100g 기준.
                - total_weight는 1인분 기준 추정.
                - total_calories는 1인분 기준 총 칼로리.
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
                ai_total_weight = float(first.get("total_weight", 350))
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
                ai_total_weight = float(first.get("total_weight", 350))

            session.add(food_item)
            session.commit()
            session.refresh(food_item)

            # ⬇️ AI 1인분 총칼로리 계산
            #    (100g 기준 칼로리 × (AI총중량 / 기준무게))
            base_w = food_item.weight or 100.0
            ai_total_calories = round(float(food_item.calories) * (ai_total_weight / base_w), 2)

            print(f"[AI 1인분] {food_item.name} : {ai_total_weight} g ≈ {ai_total_calories} kcal")

        # ✅ 요약 재계산 훅
        recompute_daily_summaries(user_id, meal.date, session)



    # 3️⃣ MealItem 추가
    meal_item = db.MealItem(meal_id=meal.id, food_id=food_item.id, quantity_g=quantity_g)
    session.add(meal_item)
    session.commit()
    session.refresh(meal_item)

    # ✅ 요약 재계산 훅
    recompute_daily_summaries(user_id, meal.date, session)

    # ✅ 실제 섭취량 비율 계산 (조회 로직과 동일하게)
    ratio = quantity_g / (food_item.weight or 100.0)

    # ✅ 음식 전체 영양정보 반환
    return {
        "meal_id": meal.id,
        "meal_number": meal.meal_number,
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


# ----------------------
# 끼니 조회
# ----------------------
class MealItemOut(BaseModel):
    food_id: int
    food_name: str
    quantity_g: float
    calories: float
    carbs: float
    protein: float
    fat: float

class MealLogOut(BaseModel):
    meal_id: int
    meal_number: int
    items: List[MealItemOut]

@router.get("/get_meals", response_model=List[MealLogOut])
def get_meals(user_id: str, date: str, session: Session = Depends(get_db)):
    meal_date = datetime.strptime(date, "%Y-%m-%d").date()
    meals = session.query(db.MealLog).filter_by(user_id=user_id, date=meal_date).order_by(db.MealLog.meal_number).all()
    result = []

    for meal in meals:
        items_out = []
        for mi in meal.items:
            food = session.query(db.Food).get(mi.food_id)
            ratio = mi.quantity_g / (food.weight or 100.0)  # ✅ 실제 섭취량 비율 계산
            items_out.append(MealItemOut(
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
            meal_number=meal.meal_number,
            items=items_out
        ))
    return result



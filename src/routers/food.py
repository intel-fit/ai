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

AZURE_ANALYZE_URL = f"{AZURE_CV_ENDPOINT}/vision/v3.2/analyze?visualFeatures=Description"

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
    img_bytes = await file.read()

    # Azure CV 호출
    headers = {"Ocp-Apim-Subscription-Key": AZURE_CV_KEY, "Content-Type": "application/octet-stream"}
    response = requests.post(AZURE_ANALYZE_URL, headers=headers, data=img_bytes)
    if response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Azure CV API failed: {response.text}")
    description = response.json().get("description", {}).get("captions", [{}])[0].get("text", "")
    if not description:
        raise HTTPException(status_code=400, detail="No description found from image")

    # Gemini 호출 (✅ weight 포함)
    headers = {"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY}
    prompt = (
        f"You are a nutrition expert. I have identified the following food from an image: '{description}'. "
        f"Return a **JSON object** with keys: name, calories, carbs, protein, fat, weight. "
        f"Weight should represent the base amount (in grams) used for the nutrient data, typically 100g."
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    gemini_response = requests.post(GEMINI_URL, headers=headers, json=payload)
    if gemini_response.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Gemini API failed: {gemini_response.text}")

    raw_text = gemini_response.json()["candidates"][0]["content"]["parts"][0]["text"]
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    fallback_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    json_text = json_match.group(1) if json_match else (fallback_match.group(0) if fallback_match else None)
    if not json_text:
        raise HTTPException(status_code=400, detail="Gemini result could not be parsed")

    try:
        result = json.loads(json_text)
    except:
        raise HTTPException(status_code=400, detail="Gemini JSON parsing failed")

    # DB 저장
    if isinstance(result, dict) and "name" in result:
        existing_food = session.query(db.Food).filter_by(name=result["name"], company="AI인식").first()
        if existing_food:
            food_item = existing_food
        else:
            food_item = db.Food(
                name=result.get("name", "Unknown"),
                company="AI인식",
                calories=result.get("calories", 0),
                carbs=result.get("carbs", 0),
                protein=result.get("protein", 0),
                fat=result.get("fat", 0),
                weight=result.get("weight", 100.0)  # ✅ 추가
            )
            session.add(food_item)
            session.commit()
            session.refresh(food_item)
    else:
        raise HTTPException(status_code=400, detail="Gemini result could not be parsed")

    return {"ai_result": result}

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
        img_bytes = await file.read()
        headers = {"Ocp-Apim-Subscription-Key": AZURE_CV_KEY, "Content-Type": "application/octet-stream"}
        response = requests.post(AZURE_ANALYZE_URL, headers=headers, data=img_bytes)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Azure CV API failed: {response.text}")
        description = response.json().get("description", {}).get("captions", [{}])[0].get("text", "")
        if not description:
            raise HTTPException(status_code=400, detail="No description from image")

        # Gemini 호출 (✅ weight 포함)
        headers = {"Content-Type": "application/json", "X-goog-api-key": GEMINI_API_KEY}
        prompt = (
            f"You are a nutrition expert. I have identified the following food from an image: '{description}'. "
            f"Return a **JSON object** with keys: name, calories, carbs, protein, fat, weight."
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        gemini_response = requests.post(GEMINI_URL, headers=headers, json=payload)
        if gemini_response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Gemini API failed: {gemini_response.text}")
        raw_text = gemini_response.json()["candidates"][0]["content"]["parts"][0]["text"]
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
        fallback_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        json_text = json_match.group(1) if json_match else (fallback_match.group(0) if fallback_match else None)
        if not json_text:
            raise HTTPException(status_code=400, detail="Gemini result could not be parsed")

        try:
            result = json.loads(json_text)
        except:
            raise HTTPException(status_code=400, detail="Gemini JSON parsing failed")

        existing_food = session.query(db.Food).filter_by(name=result["name"], company="AI인식").first()
        if existing_food:
            food_item = existing_food
        else:
            food_item = db.Food(
                name=result.get("name", "Unknown"),
                company="AI인식",
                calories=result.get("calories", 0),
                carbs=result.get("carbs", 0),
                protein=result.get("protein", 0),
                fat=result.get("fat", 0),
                weight=result.get("weight", 100.0)  # ✅ 추가
            )
            session.add(food_item)
            session.commit()
            session.refresh(food_item)
            # ✅ 요약 재계산 훅
            recompute_daily_summaries(user_id, meal.date, session)
    else:
        raise HTTPException(status_code=400, detail="No food info provided")

    # 3️⃣ MealItem 추가
    meal_item = db.MealItem(meal_id=meal.id, food_id=food_item.id, quantity_g=quantity_g)
    session.add(meal_item)
    session.commit()
    session.refresh(meal_item)
    # ✅ 요약 재계산 훅
    recompute_daily_summaries(user_id, meal.date, session)
    return {
        "meal_id": meal.id,
        "meal_number": meal.meal_number,
        "food_added": food_item.name,
        "quantity_g": quantity_g,
        "food_id": food_item.id
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



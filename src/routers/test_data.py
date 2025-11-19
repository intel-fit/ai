# src/routers/test_data.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date, timedelta
from src import db
from src.services.nutrition import calculate_macros
from src.services.summary import recompute_daily_summaries  # ✅ 추가

router = APIRouter(tags=["TestData"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

@router.post("/init_test_user")
def init_test_user(session: Session = Depends(get_db)):
    # --------------------------
    # 1️⃣ 테스트 유저 생성
    # --------------------------
    user_id = "testuser1"
    existing = session.query(db.User).filter_by(id=user_id).first()
    if existing:
        session.delete(existing)
        session.commit()

    test_user = db.User(
        id=user_id,
        name="Test User",
        age=25,
        sex="male",
        height=175,
        weight=70,
        body_fat=15,
        skeletal_muscle=30,
        goal="lean",
        activity_level=1.3,
    )
    session.add(test_user)
    session.commit()

    # --------------------------
    # 2️⃣ 운동 로그 (최근 7일)
    # --------------------------
    today = date.today()
    for i in range(7):
        log_date = today - timedelta(days=i)
        log = db.ExerciseLog(
            user_id=user_id,
            date=log_date,
            duration_min=60,
            calories_burned=250 + i * 50,
            intensity=2.0 + i * 0.2,
        )
        session.add(log)

    # --------------------------
    # 3️⃣ 식단 로그 (단순 샘플 3끼 × 7일)
    # --------------------------
    sample_meal_names = ["아침", "점심", "저녁"]
    sample_foods = [
        {"name": "닭가슴살", "calories": 165, "protein": 31, "fat": 3.6, "carbs": 0, "weight": 100},
        {"name": "현미밥", "calories": 150, "protein": 3, "fat": 1, "carbs": 32, "weight": 100},
        {"name": "고구마", "calories": 130, "protein": 2, "fat": 0.1, "carbs": 30, "weight": 100},
        {"name": "샐러드", "calories": 80, "protein": 2, "fat": 5, "carbs": 6, "weight": 100},
    ]

    # DB에 음식이 없으면 추가
    for f in sample_foods:
        exists = session.query(db.Food).filter_by(name=f["name"]).first()
        if not exists:
            food = db.Food(
                name=f["name"],
                calories=f["calories"],
                protein=f["protein"],
                fat=f["fat"],
                carbs=f["carbs"],
                weight=f["weight"],
                company="테스트식품",
                processing_level=2,
            )
            session.add(food)
    session.commit()

    foods = {f.name: f for f in session.query(db.Food).all()}


    # 7일치 식단 생성 (매일 3끼)
    for i in range(7):
        log_date = today - timedelta(days=i)

        for idx, meal_name in enumerate(sample_meal_names):
            meal = db.MealLog(
                user_id=user_id,
                date=log_date,
                meal_name=meal_name,  # ✔ 문자열 기반 끼니명
                time_taken=f"{8+idx}:00"  # 아침 08:00 / 점심 09:00 / 저녁 10:00 예시
            )
            session.add(meal)
            session.commit()

            # 음식 3개씩 넣기
            for fname in ["닭가슴살", "현미밥", "샐러드"]:
                f = foods[fname]
                item = db.MealItem(
                    meal_id=meal.id,
                    food_id=f.id,
                    quantity_g=100,
                )
                session.add(item)

            session.commit()

        # 🟩 하루 요약 재계산
        recompute_daily_summaries(user_id, log_date, session)

    return {"msg": "테스트 유저, 7일 운동 + 식단 + 요약 생성 완료 ✅"}

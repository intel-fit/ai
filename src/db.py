# src/db.py
import os
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, ForeignKey, UniqueConstraint, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship



# DB 경로
DB_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "food_db.sqlite")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# SQLAlchemy 세팅
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ----------------------
# Food 모델
# ----------------------
class Food(Base):
    __tablename__ = "foods"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    company = Column(String, index=True, nullable=False, default="해당없음")
    calories = Column(Float, default=0.0)
    carbs = Column(Float, default=0.0)
    protein = Column(Float, default=0.0)
    fat = Column(Float, default=0.0)
    fiber = Column(Float, default=0.0)
    sugar = Column(Float, default=0.0)
    sodium = Column(Float, default=0.0)
    weight = Column(Float, default=100.0)
    glycemic_index = Column(Float, default=50.0)
    processing_level = Column(Integer, default=1)
    __table_args__ = (UniqueConstraint('name', 'company', name='_name_company_uc'),)

# ----------------------
# User 모델
# ----------------------
class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    sex = Column(String, nullable=False)
    height = Column(Float, nullable=False)
    weight = Column(Float, nullable=False)
    body_fat = Column(Float, nullable=True)
    skeletal_muscle = Column(Float, nullable=True)
    activity_level = Column(Float, default=1.2)
    goal = Column(String, default="maintenance")
    
    exercise_logs = relationship("ExerciseLog", back_populates="user")
    meal_logs = relationship("MealLog", back_populates="user", cascade="all, delete-orphan")

# ----------------------
# ExerciseLog 모델
# ----------------------
class ExerciseLog(Base):
    __tablename__ = "exercise_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"))
    date = Column(Date, nullable=False)
    duration_min = Column(Float, nullable=False)
    calories_burned = Column(Float, nullable=False)
    intensity = Column(Float, nullable=True)
    
    user = relationship("User", back_populates="exercise_logs")

# ----------------------
# 끼니 단위 MealLog
# ----------------------
class MealLog(Base):
    __tablename__ = "meal_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    meal_name = Column(String, nullable=False)   # 예: 아침 / 점심 / 저녁 / 간식
    time_taken = Column(String, nullable=True)   # 예: "09:30"

    user = relationship("User", back_populates="meal_logs")
    items = relationship("MealItem", back_populates="meal", cascade="all, delete-orphan")


# ----------------------
# MealItem (각 끼니 안의 음식 단위)
# ----------------------
class MealItem(Base):
    __tablename__ = "meal_items"

    id = Column(Integer, primary_key=True, index=True)
    meal_id = Column(Integer, ForeignKey("meal_logs.id"), nullable=False)
    food_id = Column(Integer, ForeignKey("foods.id"), nullable=False)
    quantity_g = Column(Float, default=100.0)  # 섭취 중량(g)

    meal = relationship("MealLog", back_populates="items")
    food = relationship("Food")



# 바디컴프(인바디) 로그
class BodyCompLog(Base):
    __tablename__ = "body_comp_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    date = Column(Date, nullable=False, index=True)
    weight_kg = Column(Float, nullable=True)
    body_fat_pct = Column(Float, nullable=True)
    smm_kg = Column(Float, nullable=True)  # skeletal muscle mass
    note = Column(String, default="")

# 일일 식단 요약(섭취)
class DailyNutritionSummary(Base):
    __tablename__ = "daily_nutrition_summary"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    date = Column(Date, nullable=False, index=True)
    kcal = Column(Float, default=0)
    protein_g = Column(Float, default=0)
    fat_g = Column(Float, default=0)
    carb_g = Column(Float, default=0)
    fiber_g = Column(Float, default=0)
    sugar_g = Column(Float, default=0)
    sodium_mg = Column(Float, default=0)
    processed_ratio = Column(Float, default=0)  # 초가공 비중(0~1)
    distinct_main_sources = Column(Integer, default=0)  # 탄수 소스 다양성

# 일일 운동 요약(소모)
class DailyExerciseSummary(Base):
    __tablename__ = "daily_exercise_summary"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    date = Column(Date, nullable=False, index=True)
    duration_min = Column(Float, default=0)
    calories_burned = Column(Float, default=0)
    avg_intensity = Column(Float, default=0)

# 코치 노트(요약 피드백)
class CoachNote(Base):
    __tablename__ = "coach_notes"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    period = Column(String, nullable=False)  # 'daily:YYYY-MM-DD', 'weekly:YYYY-WW'
    summary = Column(String)                 # 자연어 요약
    action_items = Column(String)            # 할 일/권고 리스트(문자열 JSON)


# ----------------------
# Daily Health Score (AI 평가 점수)
# ----------------------
class DailyHealthScore(Base):
    __tablename__ = "daily_health_scores"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    date = Column(Date, nullable=False, index=True)
    nutrition_score = Column(Float, default=0.0)
    exercise_score = Column(Float, default=0.0)
    balance_score = Column(Float, default=0.0)
    total_score = Column(Float, default=0.0)

# ----------------------
# 운동 추천 기록 (AI 루틴)
# ----------------------
from sqlalchemy import Boolean, JSON

class UserExerciseRec(Base):
    __tablename__ = "user_exercise_recs"
    id = Column(String, primary_key=True, index=True)  # UUID
    user_id = Column(String, ForeignKey("users.id"), index=True)
    date = Column(Date, nullable=False)
    day = Column(Integer, nullable=False)
    focus = Column(String, nullable=False)
    exercises_json = Column(JSON, nullable=False)  # 추천된 운동 리스트 (dict 배열)
    feedback_score = Column(Float, nullable=True)  # 1~5점
    completed = Column(Boolean, default=False)     # 수행 여부
    created_at = Column(Date, nullable=False)

# ----------------------
# DB 초기화
# ----------------------
def init_db():
    inspector = inspect(engine)

    # Food 테이블 확인
    if not inspector.has_table("foods"):
        Food.__table__.create(bind=engine)

    # ----------------------
    # 삭제 후 재생성할 테이블 리스트
    # ----------------------
    tables_to_reset = [User, ExerciseLog, MealLog, MealItem]

    for table in tables_to_reset:
        if inspector.has_table(table.__tablename__):
            table.__table__.drop(bind=engine)
        table.__table__.create(bind=engine)

    # ✅ 신규 요약/인바디/노트 테이블은 드랍하지 않고 없으면 생성
    for table in [BodyCompLog, DailyNutritionSummary, DailyExerciseSummary, CoachNote]:
        if not inspector.has_table(table.__tablename__):
            table.__table__.create(bind=engine)

    for table in [BodyCompLog, DailyNutritionSummary, DailyExerciseSummary, CoachNote, DailyHealthScore]:
        if not inspector.has_table(table.__tablename__):
            table.__table__.create(bind=engine)
    
    if not inspector.has_table("user_exercise_recs"):
        UserExerciseRec.__table__.create(bind=engine)


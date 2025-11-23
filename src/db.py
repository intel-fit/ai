# src/db.py (FINAL VERSION)
import os
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Date, ForeignKey,
    UniqueConstraint, inspect, DateTime, Text, Boolean, JSON
)
from datetime import datetime, date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import uuid


# ----------------------
# DB PATH 설정
# ----------------------
DB_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "food_db.sqlite")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ----------------------
# Food
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
# User
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
# ExerciseLog (daily)
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
# MealLog
# ----------------------
class MealLog(Base):
    __tablename__ = "meal_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    meal_name = Column(String, nullable=False)
    time_taken = Column(String, nullable=True)

    user = relationship("User", back_populates="meal_logs")
    items = relationship("MealItem", back_populates="meal", cascade="all, delete-orphan")

# ----------------------
# MealItem
# ----------------------
class MealItem(Base):
    __tablename__ = "meal_items"

    id = Column(Integer, primary_key=True, index=True)
    meal_id = Column(Integer, ForeignKey("meal_logs.id"), nullable=False)
    food_id = Column(Integer, ForeignKey("foods.id"), nullable=False)
    quantity_g = Column(Float, default=100.0)

    meal = relationship("MealLog", back_populates="items")
    food = relationship("Food")

# ----------------------
# Body Composition Log
# ----------------------
class BodyCompLog(Base):
    __tablename__ = "body_comp_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    date = Column(Date, nullable=False, index=True)
    weight_kg = Column(Float, nullable=True)
    body_fat_pct = Column(Float, nullable=True)
    smm_kg = Column(Float, nullable=True)
    note = Column(String, default="")

# ----------------------
# Daily Nutrition Summary
# ----------------------
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
    processed_ratio = Column(Float, default=0)
    distinct_main_sources = Column(Integer, default=0)

# ----------------------
# Daily Exercise Summary
# ----------------------
class DailyExerciseSummary(Base):
    __tablename__ = "daily_exercise_summary"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    date = Column(Date, nullable=False, index=True)
    duration_min = Column(Float, default=0)
    calories_burned = Column(Float, default=0)
    avg_intensity = Column(Float, default=0)

# ----------------------
# Coach Notes
# ----------------------
class CoachNote(Base):
    __tablename__ = "coach_notes"
    id = Column(Integer, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
    period = Column(String, nullable=False)
    summary = Column(String)
    action_items = Column(String)

# ----------------------
# DailyHealthScore
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
# UserExerciseRec (AI 루틴 기록)
# ----------------------
class UserExerciseRec(Base):
    __tablename__ = "user_exercise_recs"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), index=True)
    date = Column(Date, nullable=False)
    day = Column(Integer, nullable=False)
    focus = Column(String, nullable=False)
    exercises_json = Column(JSON, nullable=False)
    feedback_score = Column(Float, nullable=True)
    completed = Column(Boolean, default=False)
    created_at = Column(Date, nullable=False)

# ==================================================
# NEW — Exercise Session + Items (User performed logs)
# ==================================================
class ExerciseSession(Base):
    __tablename__ = "exercise_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    date = Column(Date, default=date.today)
    session_name = Column(String)
    duration_min = Column(Float)
    intensity_score = Column(Float)
    feedback = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class ExerciseSessionItem(Base):
    __tablename__ = "exercise_session_items"


    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("exercise_sessions.id"), nullable=False)

    exercise_id = Column(String, nullable=False)
    exercise_name = Column(String, nullable=False)

    weight_kg = Column(Float, nullable=True)
    reps = Column(Integer, nullable=True)
    sets = Column(Integer, nullable=True)
    warmup_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

# ----------------------
# init_db()
# ----------------------
def init_db():
    inspector = inspect(engine)

    # 필수 테이블 존재 확인 및 생성
    base_tables = [Food, User, ExerciseLog, MealLog, MealItem]
    for table in base_tables:
        if not inspector.has_table(table.__tablename__):
            table.__table__.create(bind=engine)

    # 요약/코치/헬스스코어
    for table in [BodyCompLog, DailyNutritionSummary, DailyExerciseSummary, CoachNote, DailyHealthScore]:
        if not inspector.has_table(table.__tablename__):
            table.__table__.create(bind=engine)

    # AI 추천
    if not inspector.has_table("user_exercise_recs"):
        UserExerciseRec.__table__.create(bind=engine)

    # NEW — Exercise Sessions
    if not inspector.has_table("exercise_sessions"):
        ExerciseSession.__table__.create(bind=engine)

    if not inspector.has_table("exercise_session_items"):
        ExerciseSessionItem.__table__.create(bind=engine)

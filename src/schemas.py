from typing import Optional
from pydantic import BaseModel, field_validator
from datetime import date
from typing import Optional
from datetime import datetime




# ----------------------
# AI 운동 추천 관련 스키마
# ----------------------
from typing import Literal, List, Optional, Dict, Any
from pydantic import BaseModel, Field

Goal = Literal["fat_loss", "hypertrophy", "strength", "functional"]
Experience = Literal["beginner", "intermediate", "advanced"]
Environment = Literal["home", "gym"]

class InBodyRegion(BaseModel):
    """부위별 근육·지방 비율 지표"""
    muscle_score: Optional[float] = None  # 근육량 부족 → 음수
    fat_score: Optional[float] = None     # 체지방 과다 → 양수

class InBodySnapshot(BaseModel):
    """인바디 주요 부위별 점수"""
    arms: InBodyRegion = InBodyRegion()
    chest: InBodyRegion = InBodyRegion()
    back: InBodyRegion = InBodyRegion()
    shoulders: InBodyRegion = InBodyRegion()
    legs: InBodyRegion = InBodyRegion()
    glutes: InBodyRegion = InBodyRegion()
    core: InBodyRegion = InBodyRegion()

class UserExerciseContext(BaseModel):
    """AI 운동 루틴 추천을 위한 전체 사용자 프로필"""
    user_id: str
    age: int
    sex: Literal["male", "female"]
    goal: Goal = "hypertrophy"
    experience: Experience = "beginner"
    environment: Environment = "gym"
    available_equipment: List[str] = []
    health_conditions: List[str] = []  # ["허리통증", "무릎통증"] 등
    plan_days: int = Field(ge=1, le=7, default=7)
    inbody: InBodySnapshot = InBodySnapshot()

    target_time_min: Optional[int] = Field(default=None, ge=10, le=180)
    weight_kg: Optional[float] = Field(default=70.0, ge=30, le=200)

class FoodBase(BaseModel):
    name: str
    calories: float
    carbs: float
    protein: float
    fat: float
    fiber: float = 0.0
    sugar: float = 0.0
    sodium: float = 0.0
    weight: float = 100.0
    glycemic_index: float = 50.0
    processing_level: int = 1
    company: str = ""  # 업체명
    weight: float = 100.0 

class FoodCreate(FoodBase):
    pass

class FoodOut(FoodBase):
    id: int

    class Config:
        from_attributes = True

class UserBase(BaseModel):
    name: str
    age: int
    sex: str
    height: float
    weight: float
    body_fat: Optional[float] = None    # ⬅️ Optional 처리
    skeletal_muscle: Optional[float] = None   # ⬅️ Optional 처리
    activity_level: float = 1.2
    goal: str = "maintenance"

class UserCreate(UserBase):
    id: str

class UserOut(UserBase):
    id: str
    class Config:
        from_attributes = True


class ExerciseLogCreate(BaseModel):
    user_id: str
    date: date
    duration_min: float
    calories_burned: float
    intensity: int | None = None

    @field_validator("intensity")
    def validate_intensity(cls, v):
        if v is not None and not (1 <= v <= 5):
            raise ValueError("intensity must be between 1 and 5")
        return v
class ExerciseLogOut(ExerciseLogCreate):
    id: int


# ----------------------
# 끼니 단위 관련
# ----------------------
from typing import List

class MealItemBase(BaseModel):
    food_id: int
    quantity_g: float

class MealItemCreate(MealItemBase):
    pass

class MealItemOut(BaseModel):
    meal_item_id: int
    food_id: int
    food_name: str
    quantity_g: float
    calories: float
    carbs: float
    protein: float
    fat: float

    class Config:
        from_attributes = True

class MealLogBase(BaseModel):
    date: date
    meal_name: str
    time_taken: Optional[str] = None

class MealLogCreate(MealLogBase):
    pass

class MealLogOut(BaseModel):
    meal_id: int
    meal_name: str
    time_taken: Optional[str]
    items: List[MealItemOut]

    class Config:
        from_attributes = True


class ExerciseFeedbackCreate(BaseModel):
    user_id: str
    date: date
    day: int
    focus: str
    exercises: List[Dict[str, Any]]  # generate_week_plan 결과 중 하루분


class ExerciseFeedbackUpdate(BaseModel):
    feedback_score: float | None = None  # 1~5점
    completed: bool | None = None

class ExerciseFeedbackIn(BaseModel):
    user_id: str
    exercise_id: str
    exercise_name: str
    category: Optional[str] = None
    target_group: Optional[str] = None

    sets: Optional[int] = None
    reps: Optional[int] = None
    duration_sec: Optional[int] = None

    feedback: str    # "like" or "dislike"

class ExerciseFeedbackOut(BaseModel):
    status: str

class ExerciseSessionItemInput(BaseModel):
    exercise_id: str          # 운동 고유 ID
    name: str                 # 운동 이름
    weight: float
    reps: int
    sets: int
    warmup: Optional[list] = None
    feedback: List[str] = []


class ExerciseSessionInput(BaseModel):
    user_id: str
    session_name: str
    duration_min: float
    intensity: int                   # 1~5 점
    feedback: str                    # "like" | "dislike"
    items: List[ExerciseSessionItemInput]


class SubscriptionStatus(BaseModel):
    has_active_subscription: bool
    status: Optional[str] = None
    current_period_end: Optional[datetime] = None
    stripe_subscription_id: Optional[str] = None

class ManualCalorieInput(BaseModel):
    target_calorie: int

class ManualGoalRequest(BaseModel):
    user_id: str
    target_calorie: float
    date: Optional[str] = None   # ← 하루 manual에 필요

class MealNameUpdateRequest(BaseModel):
    meal_id: int
    user_id: str
    meal_name: str

class MealDateUpdateRequest(BaseModel):
    meal_id: int
    user_id: str
    date: str   # YYYY-MM-DD

class MealTimeUpdateRequest(BaseModel):
    meal_id: int
    user_id: str
    time_taken: str   # HH:MM


class MealItemInput(BaseModel):
    food_id: int
    food_name: Optional[str] = None
    quantity_g: float
    calories: float
    carbs: float
    protein: float
    fat: float

class MealCreateRequest(BaseModel):
    user_id: str
    date: str
    meal_name: str
    time_taken: Optional[str] = None
    items: List[MealItemInput]


# =====================================================
# 식단 추천 피드백 루프 + 에이전트용 스키마 (최종본)
# =====================================================




# ----------------------
# User Profile
# ----------------------
class UserProfileBase(BaseModel):
    diet_style: str = "normal"            # "tight", "normal", "bulk"
    cuisine_preference: str = "mixed"     # "korean", "western", "mixed"
    allergies: Optional[list[str]] = None
    notes: Optional[str] = None


class UserProfileOut(UserProfileBase):
    user_id: str

    class Config:
        from_attributes = True


# ----------------------
# Food Preferences
# ----------------------
class FoodPreferenceOut(BaseModel):
    id: int
    food_name: str
    score: float
    source: str

    class Config:
        from_attributes = True


class FoodExclusionOut(BaseModel):
    id: int
    food_name: str
    reason: str

    class Config:
        from_attributes = True


# ----------------------
# Meal History Item (추천용 로그)
# ----------------------
class UserMealHistoryItemOut(BaseModel):
    id: int
    food_id: Optional[int]
    food_name: str
    amount_g: float

    calories: Optional[float]
    protein: Optional[float]
    fat: Optional[float]
    carbs: Optional[float]

    class Config:
        from_attributes = True


# ----------------------
# Meal History (추천엔진용)
# ----------------------
class UserMealHistoryOut(BaseModel):
    id: int
    date: date
    meal_name: str

    total_calories: Optional[float]
    total_protein: Optional[float]
    total_carbs: Optional[float]
    total_fat: Optional[float]

    items: List[UserMealHistoryItemOut]

    class Config:
        from_attributes = True


# =====================================================
# 식단 피드백 (Meal Feedback)
# =====================================================

class MealFeedbackCreate(BaseModel):
    user_id: str
    history_id: int              # UserMealHistory.id
    rating: int                  # -1, 0, +1
    comment: Optional[str] = None

from typing import Optional
from pydantic import BaseModel, field_validator
from datetime import date



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
    body_fat: float | None = None
    skeletal_muscle: float | None = None
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
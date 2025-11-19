# src/main.py
from fastapi import FastAPI
from src.db import init_db
from src.routers import food, user, exercise, recommendation
from dotenv import load_dotenv
import os
from src.routers import user, test_data #테스트
from src.routers import meal_plan_ai
from src.routers import feedback_router
from src.routers import analytics
from src.routers import coach
from src.routers import chat_coach
from src.routers import score
from src.routers import score_trend
from src.routers import exercise_ai
from src.routers import exercise_score
from src.routers import exercise_feedback
from src.routers.home_feedback import router as home_feedback_router
from src.routers import home 







load_dotenv()

# 필수 API 키 확인
USDA_API_KEY = os.getenv("USDA_API_KEY")
AZURE_COMPUTER_VISION_KEY = os.getenv("AZURE_COMPUTER_VISION_KEY")
AZURE_COMPUTER_VISION_ENDPOINT = os.getenv("AZURE_COMPUTER_VISION_ENDPOINT")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not USDA_API_KEY:
    raise RuntimeError("USDA_API_KEY not set in .env")
if not AZURE_COMPUTER_VISION_KEY:
    raise RuntimeError("AZURE_COMPUTER_VISION_KEY not set in .env")
if not AZURE_COMPUTER_VISION_ENDPOINT:
    raise RuntimeError("AZURE_COMPUTER_VISION_ENDPOINT not set in .env")
if not GEMINI_API_KEY:
    raise RuntimeError("Gemini API key not set in .env")

print("All API keys loaded correctly")

app = FastAPI(title="Diet AI API")

# DB 초기화
init_db()

# 라우터 등록
app.include_router(food.router, prefix="/food")
app.include_router(user.router, prefix="/user")
app.include_router(exercise.router, prefix="/exercise")
app.include_router(recommendation.router, prefix="/recommend")
app.include_router(test_data.router, prefix="/test") #테스트용
app.include_router(meal_plan_ai.router, prefix="/ai-plan")
app.include_router(feedback_router.router)
app.include_router(analytics.router)
app.include_router(coach.router)
app.include_router(chat_coach.router)
app.include_router(score.router)
app.include_router(score_trend.router)
app.include_router(exercise_ai.router)
app.include_router(exercise_score.router)
app.include_router(exercise_feedback.router)
app.include_router(home_feedback_router)
app.include_router(home.router) 


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)

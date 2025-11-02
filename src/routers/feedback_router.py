from fastapi import APIRouter
import os, json, datetime

router = APIRouter(tags=["Feedback"])
FEEDBACK_PATH = os.path.join("src", "data", "user_feedback.json")

@router.post("/feedback/rate")
def rate_feedback(payload: dict):
    """
    사용자가 특정 음식이나 식단에 대한 만족도를 평가할 수 있음.
    payload 예시:
    {
        "user_id": "testuser1",
        "food_name": "닭가슴살 소떡",
        "rating": 4.5,      # (1~5)
        "comment": "조합이 괜찮아요"
    }
    """
    os.makedirs(os.path.dirname(FEEDBACK_PATH), exist_ok=True)
    feedback = {
        "timestamp": datetime.datetime.now().isoformat(),
        **payload
    }

    # 기존 피드백 로드
    data = []
    if os.path.exists(FEEDBACK_PATH):
        with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

    # 새 피드백 추가
    data.append(feedback)
    with open(FEEDBACK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {"message": "Feedback saved successfully", "feedback": feedback}

import os, json, datetime

LOG_PATH = os.path.join("src", "data", "meal_logs.jsonl")

def append_meal_log(user_id: str, daily_plan: dict):
    """하루 식단 추천 결과를 JSONL 로그로 저장"""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    record = {
        "timestamp": datetime.datetime.now().isoformat(),
        "user_id": user_id,
        "daily_plan": daily_plan
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"📝 Meal log appended for user={user_id}")

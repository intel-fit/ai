# src/services/user_preference_updater.py
import os, json, time
import pandas as pd

DATA_DIR = os.path.join("src","data")
PREF_PATH = os.path.join(DATA_DIR, "user_prefs.parquet")

DEFAULT_ALPHA = 0.5  # EMA 가중 (최근 선호 반영 강도)
SCORE_MIN, SCORE_MAX = 0.0, 100.0

def _load_df():
    if os.path.exists(PREF_PATH):
        return pd.read_parquet(PREF_PATH)
    return pd.DataFrame(columns=["user_id","food_name","ema_score","count","updated_ts"])

def _save_df(df):
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_parquet(PREF_PATH, index=False)

def rate(user_id:str, food_name:str, rating:int, alpha:float=DEFAULT_ALPHA):
    """
    rating: 1~5 (별점) → 0~100 점수로 변환해 EMA 갱신
    """
    df = _load_df()

    # 1~5 → 0~100 변환 (가중치 선형 매핑)
    rating = max(1, min(5, int(rating)))
    new_score = (rating - 1) / 4 * 100.0

    idx = (df["user_id"]==user_id) & (df["food_name"]==food_name)
    if idx.any():
        row = df[idx].iloc[0]
        ema_prev = float(row["ema_score"])
        cnt_prev = int(row["count"])
        ema_new = alpha*new_score + (1-alpha)*ema_prev
        df.loc[idx, "ema_score"] = max(SCORE_MIN, min(SCORE_MAX, ema_new))
        df.loc[idx, "count"] = cnt_prev + 1
        df.loc[idx, "updated_ts"] = int(time.time())
    else:
        df.loc[len(df)] = {
            "user_id": user_id,
            "food_name": food_name,
            "ema_score": float(new_score),
            "count": 1,
            "updated_ts": int(time.time())
        }
    _save_df(df)
    return float(new_score)

def bulk_rate(user_id:str, feedbacks:dict, alpha:float=DEFAULT_ALPHA):
    """
    feedbacks: {food_name: rating(1~5), ...}
    """
    for food, r in feedbacks.items():
        rate(user_id, food, r, alpha=alpha)

def get_user_pref_map(user_id:str) -> dict:
    df = _load_df()
    df = df[df["user_id"]==user_id]
    return {r["food_name"]: float(r["ema_score"]) for _,r in df.iterrows()}

if __name__ == "__main__":
    # quick test
    rate("u1","현미밥",5)
    rate("u1","닭가슴살",4)
    print(get_user_pref_map("u1"))

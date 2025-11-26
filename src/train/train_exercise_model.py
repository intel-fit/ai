# ===========================================
# src/train/train_exercise_model.py
# LightGBM 기반 운동 추천 모델 학습 + 모델 저장
# ===========================================
import os
import pickle
import pandas as pd
import lightgbm as lgb
from sqlalchemy import create_engine

# -----------------------------
# 1) 운동 DB 불러오기
# -----------------------------
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "exercise.db")

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

query = """
SELECT exerciseId, name, targetMuscles, bodyParts, equipments,
       difficulty, risk_score, category, effectiveness
FROM exerciseCategory
"""

df = pd.read_sql(query, engine)

# -----------------------------
# 2) 간단한 Feature Engineering
# -----------------------------
df["equip_simple"] = df["equipments"].fillna("").str.lower().str.contains("덤벨").astype(int)
df["category_code"] = df["category"].astype("category").cat.codes
df["eff_norm"] = df["effectiveness"] / df["effectiveness"].max()

# (여기서 ML이 예측할 목표값을 하나 구성 → 지금은 effectiveness 기반 surrogate target)
df["target"] = df["eff_norm"]

FEATURES = ["risk_score", "equip_simple", "category_code"]
TARGET = "target"

X = df[FEATURES]
y = df[TARGET]

# -----------------------------
# 3) LightGBM 모델 학습
# -----------------------------
train_data = lgb.Dataset(X, label=y)
params = {
    "objective": "regression",
    "metric": "rmse",
    "verbosity": -1,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "feature_fraction": 0.8
}

model = lgb.train(params, train_data, num_boost_round=200)

# -----------------------------
# 4) 모델 파일 저장
# -----------------------------
MODEL_PATH = os.path.join(BASE_DIR, "models", "exercise_model.pkl")
os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

with open(MODEL_PATH, "wb") as f:
    pickle.dump(model, f)

print("🎉 모델 학습 완료! → 저장 위치:", MODEL_PATH)

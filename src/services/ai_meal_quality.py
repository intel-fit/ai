# src/services/ai_meal_quality.py
from __future__ import annotations
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_absolute_error

# ============================================================
# ⚙️ 설정
# ============================================================
INPUT_PATH  = os.path.join("src", "data", "extended_food_db_clustered_stage2.xlsx")
OUTPUT_PATH = os.path.join("src", "data", "extended_food_db_scored.xlsx")
MODEL_PATH  = os.path.join("src", "data", "health_score_model.pkl")

# ------------------------------------------------------------
# ✳️ Feature Columns (2차 군집 포함)
# ------------------------------------------------------------
FEATURE_COLS = [
    "energy_kcal", "protein_g", "fat_g", "carb_g",
    "fiber_g", "sugar_g", "sodium_mg",
    "glycemic_index", "processing_level",
    "category_cluster", "nutrition_cluster"
]

# ------------------------------------------------------------
# ✳️ Target Column
# ------------------------------------------------------------
TARGET_COL = "hybrid_health_score"   # health_score, ml_health_score 등으로 변경 가능


# ============================================================
# ⚙️ 모델 선택 함수
# ============================================================
def _get_model():
    """LightGBM 우선, 없으면 RandomForest로 폴백"""
    try:
        from lightgbm import LGBMRegressor
        return LGBMRegressor(
            n_estimators=800,
            learning_rate=0.03,
            max_depth=-1,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_alpha=0.1,
            reg_lambda=0.1,
            random_state=42,
            n_jobs=-1
        )
    except Exception:
        from sklearn.ensemble import RandomForestRegressor
        return RandomForestRegressor(
            n_estimators=400,
            max_depth=None,
            random_state=42,
            n_jobs=-1
        )


# ============================================================
# 🧠 모델 학습
# ============================================================
def train_model(excel_path: str = INPUT_PATH, save_path: str = MODEL_PATH):
    """LightGBM을 이용한 health_score 예측 모델 학습"""
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Input file not found: {excel_path}")

    df = pd.read_excel(excel_path)
    print(f"📘 Loaded data: {excel_path} (rows={len(df)})")

    # 필수 컬럼 확인 및 결측 보정
    for col in FEATURE_COLS:
        if col not in df.columns:
            df[col] = 0.0

    df = df.dropna(subset=FEATURE_COLS + [TARGET_COL]).copy()
    print(f"✅ Training samples: {len(df)} usable rows")

    X = df[FEATURE_COLS]
    y = df[TARGET_COL].astype(float)

    # 훈련/검증 분리
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # 모델 학습
    model = _get_model()
    model.fit(X_train, y_train)

    # 검증
    pred = model.predict(X_val)
    r2 = r2_score(y_val, pred)
    mae = mean_absolute_error(y_val, pred)

    print(f"✅ Train done: R2={r2:.3f}, MAE={mae:.2f}")
    print(f"📊 Feature Count: {len(FEATURE_COLS)} | Target: {TARGET_COL}")

    # 모델 저장
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    joblib.dump(model, save_path)
    print(f"💾 Saved model → {save_path}")

    return save_path


# ============================================================
# 📈 예측 (새로운 데이터에 스코어 추가)
# ============================================================
def load_model(path: str = MODEL_PATH):
    return joblib.load(path)


def predict_scores(excel_path: str, model_path: str = MODEL_PATH, out_path: str | None = None):
    """학습된 모델로 새로운 음식 DB에 ml_health_score 추가"""
    model = load_model(model_path)
    df = pd.read_excel(excel_path)

    # 결측/누락 피처 처리
    for c in FEATURE_COLS:
        if c not in df.columns:
            df[c] = 0.0

    df_pred = df.copy()
    df_pred["ml_health_score"] = model.predict(df_pred[FEATURE_COLS])

    if out_path:
        df_pred.to_excel(out_path, index=False)
        print(f"✅ Predictions saved → {out_path}")

    return df_pred


# ============================================================
# 🧩 실행 엔트리포인트
# ============================================================
if __name__ == "__main__":
    # 1️⃣ 학습
    trained_path = train_model(INPUT_PATH, MODEL_PATH)

    # 2️⃣ 예측 (동일 파일에 예측 컬럼 추가)
    predict_scores(
        excel_path=INPUT_PATH,
        model_path=trained_path,
        out_path=OUTPUT_PATH
    )

    print("🎯 All done → model trained & predictions generated!")

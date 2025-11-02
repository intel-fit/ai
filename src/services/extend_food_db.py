# src/services/extend_food_db.py
from __future__ import annotations
import os, sys, re
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pandas as pd
import numpy as np
from typing import Dict

# 서비스 모듈
from src.services.food_quality import add_or_recalculate_health_scores
from src.services.ai_meal_quality import predict_scores
from src.services.health_score_hybrid import hybrid_health_score

# 경로 설정
INPUT_PATH  = os.path.join("src", "data", "extended_food_db_clustered_stage1.xlsx")
OUTPUT_PATH = os.path.join("src", "data", "extended_food_db.xlsx")

# --------------------------------
# 1️⃣ 하이브리드 결합 함수
# --------------------------------
def build_extended_food_db_with_hybrid(
    in_path: str,
    out_path: str,
    user_goal: str | None = None,
    alpha: float | None = 0.6
) -> str:
    """규칙 + ML + 하이브리드 점수를 포함한 확장 DB 생성"""
    df = pd.read_excel(in_path)
    df = add_or_recalculate_health_scores(df)  # health_score 계산

    # ML 점수 예측
    df_ml = predict_scores(in_path)            # ml_health_score 생성

    # food_name 기준 병합
    df_all = df.merge(
        df_ml[["food_name", "ml_health_score"]],
        on="food_name", how="left"
    )

    # 하이브리드 스코어 결합
    df_all = hybrid_health_score(df_all, alpha=alpha, user_goal=user_goal)

    df_all.to_excel(out_path, index=False)
    print(f"✅ Saved hybrid DB → {out_path}")
    return out_path
# -----------------------------
# 1) 키워드 기반 분류/대표값 테이블
# -----------------------------
GROUP_RULES = [
    # 초가공 / 가공식품 먼저 필터링
    ("튀김|라면|스낵|과자|패스트|햄버거|피자|핫도그|아이스크림|초코|쿠키|도넛", "ultra_processed"),
    ("음료|쥬스|주스|탄산|에이드|라떼|커피|밀크티", "beverage"),
    ("디저트|케이크|도넛|쿠키|초콜릿|젤리|아이스크림", "dessert"),


    # 부식류 / 기타
    ("국|찌개|탕|수프", "soup_stew"),
    ("김치|젓갈|절임|장아찌", "pickled"),
    ("우유|요거트|요구르트|치즈|유제품", "dairy"),


    # 탄수화물 기반 주식류
    ("빵|베이글|토스트|크로와상|빵류", "bread"),
    ("쌀밥|흰밥|국수|면|파스타|우동|라면사리", "refined_carb"),
    ("통밀|현미|귀리|잡곡|오트|수수|퀴노아", "whole_grain"),
    ("고구마|감자|옥수수", "starch_tuber"),

    
    # 단백질 기반 주식/반찬
    ("닭가슴살|계란|달걀|소고기|돼지|오리|두부|콩|유부|단백질", "protein"),
    ("햄|소시지|베이컨|스팸", "ultra_processed"),  # 단백질이지만 가공육은 초가공으로 분류

    
    # 건강식/식이섬유 식품
    ("샐러드|생야채|채소|야채", "veg_salad"),
    ("과일|베리|바나나|사과|오렌지|키위|포도|자몽", "fruit"),

    
    # 기타 예외 처리
    ("샌드위치|도시락|즉석|레토르트|가공식품", "ultra_processed"),
]


# 카테고리별 대표 추정값 (도메인 지식 기반)
GI_DEFAULTS = {
    "veg_salad": 35, "fruit": 50, "whole_grain": 50, "refined_carb": 70,
    "bread": 65, "starch_tuber": 55, "protein": 45, "soup_stew": 55,
    "pickled": 45, "ultra_processed": 80, "dairy": 45, "beverage": 75, "dessert": 80, "other": 60
}

SODIUM_MG_DEFAULTS = {
    "veg_salad": 150, "fruit": 10, "whole_grain": 50, "refined_carb": 200,
    "bread": 250, "starch_tuber": 50, "protein": 150, "soup_stew": 600,
    "pickled": 500, "ultra_processed": 600, "dairy": 120, "beverage": 20, "dessert": 200, "other": 200
}

FIBER_G_DEFAULTS = {
    "veg_salad": 4.0, "fruit": 3.0, "whole_grain": 5.0, "refined_carb": 1.5,
    "bread": 2.5, "starch_tuber": 2.8, "protein": 0.8, "soup_stew": 1.0,
    "pickled": 1.5, "ultra_processed": 1.0, "dairy": 0.0, "beverage": 0.0, "dessert": 1.2, "other": 1.5
}

SUGAR_G_DEFAULTS = {
    "veg_salad": 2.0, "fruit": 12.0, "whole_grain": 2.5, "refined_carb": 2.0,
    "bread": 3.0, "starch_tuber": 4.0, "protein": 0.5, "soup_stew": 1.5,
    "pickled": 2.0, "ultra_processed": 8.0, "dairy": 7.0, "beverage": 15.0, "dessert": 20.0, "other": 3.0
}

# 가공도(1~5) 기본 추정
PROC_LEVEL_DEFAULTS = {
    "veg_salad": 1, "fruit": 1, "whole_grain": 2, "refined_carb": 3,
    "bread": 3, "starch_tuber": 2, "protein": 2, "soup_stew": 2,
    "pickled": 3, "ultra_processed": 5, "dairy": 3, "beverage": 4, "dessert": 4, "other": 3
}

NEEDED_COLS = [
    "food_name","energy_kcal","protein_g","fat_g","carb_g",
    "fiber_g","sugar_g","sodium_mg","glycemic_index","processing_level",
    "serving_size_g"
]

# ---------------------------
# 4️⃣ 유틸 함수
# ---------------------------
def classify_group(name: str) -> str:
    name = str(name).lower()
    for pattern, group in GROUP_RULES:
        if re.search(pattern, name):
            return group
    return "other"

def ensure_cols(df: pd.DataFrame) -> pd.DataFrame:
    """필수 컬럼이 없으면 NaN으로 추가"""
    for col in NEEDED_COLS:
        if col not in df.columns:
            df[col] = np.nan
    return df

def fill_with_group_defaults(df: pd.DataFrame, col: str, defaults: Dict[str, float]) -> None:
    """food_group별 대표값으로 결측치 채움"""
    mask = df[col].isna()
    if mask.any():
        df.loc[mask, col] = df.loc[mask, "food_group"].map(lambda g: defaults.get(g, defaults["other"]))

def clamp_numeric(df: pd.DataFrame, col: str, minv: float, maxv: float) -> None:
    """수치형 컬럼 범위 제한"""
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].clip(lower=minv, upper=maxv)

# ---------------------------
# 5️⃣ 메인 파이프라인
# ---------------------------
def extend_food_db(input_path: str = INPUT_PATH, output_path: str = OUTPUT_PATH, goal_for_score: str | None = None) -> str:
    if not os.path.exists(input_path):
        print(f"[ERROR] Input file not found: {input_path}", file=sys.stderr)
        raise FileNotFoundError(input_path)

    df = pd.read_excel(input_path)
    df = ensure_cols(df)

    # 1️⃣ food_group 분류
    df["food_group"] = df["food_name"].apply(classify_group)

    # 2️⃣ 기본적 수치 클램프
    clamp_numeric(df, "energy_kcal", 0, 5000)
    clamp_numeric(df, "protein_g", 0, 200)
    clamp_numeric(df, "fat_g", 0, 200)
    clamp_numeric(df, "carb_g", 0, 500)
    clamp_numeric(df, "serving_size_g", 50, 1200)
    df["serving_size_g"] = df["serving_size_g"].fillna(100.0)

    # 3️⃣ 결측치 그룹별 대표값 보정
    for col, defaults in [
        ("glycemic_index", GI_DEFAULTS),
        ("sodium_mg", SODIUM_MG_DEFAULTS),
        ("fiber_g", FIBER_G_DEFAULTS),
        ("sugar_g", SUGAR_G_DEFAULTS),
        ("processing_level", PROC_LEVEL_DEFAULTS),
    ]:
        fill_with_group_defaults(df, col, defaults)

    # 4️⃣ 남은 NaN에 보수적 기본값 채움
    df["glycemic_index"]   = df["glycemic_index"].fillna(60.0)
    df["sodium_mg"]        = df["sodium_mg"].fillna(200.0)
    df["fiber_g"]          = df["fiber_g"].fillna(1.5)
    df["sugar_g"]          = df["sugar_g"].fillna(3.0)
    df["processing_level"] = df["processing_level"].fillna(3.0)

    # 5️⃣ 클램프 재정리
    clamp_numeric(df, "glycemic_index", 20, 100)
    clamp_numeric(df, "sodium_mg", 0, 5000)
    clamp_numeric(df, "fiber_g", 0, 30)
    clamp_numeric(df, "sugar_g", 0, 100)
    clamp_numeric(df, "processing_level", 1, 5)

    # 6️⃣ Health Score 계산
    df = add_or_recalculate_health_scores(df, goal=goal_for_score)

    # ✅ 기존 컬럼 유지 + 신규만 추가
    new_cols = [
        "food_group", "glycemic_index", "processing_level",
        "health_score"
    ]
    for c in new_cols:
        if c not in df.columns:
            df[c] = np.nan

    # 저장 (덮어쓰기 X)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_excel(output_path, index=False)
    print(f"✅ Extended food DB saved with {len(df.columns)} columns → {output_path}")

    # 7️⃣ 경고 출력
    warn_mask = (df["health_score"] < 30) & (df["processing_level"] >= 4)
    if warn_mask.any():
        n = int(warn_mask.sum())
        print(f"⚠️  {n} ultra-processed/high-penalty items detected (health_score<30).")

    # 8️⃣ 하이브리드 버전 생성
    build_extended_food_db_with_hybrid(
        in_path=output_path,
        out_path=output_path,
        user_goal=goal_for_score,
        alpha=0.6
    )

    return output_path


# ---------------------------
# 6️⃣ 실행 엔트리포인트
# ---------------------------
if __name__ == "__main__":
    # goal_for_score: 'diet' | 'bulk' | 'lean' | None
    extend_food_db(input_path=INPUT_PATH, output_path=OUTPUT_PATH, goal_for_score=None)
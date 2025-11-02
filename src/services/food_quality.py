# src/services/food_quality.py
from __future__ import annotations
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from typing import Dict, Any
import numpy as np
import pandas as pd

# 기본 가중치 (영양학 문헌/보편적 가이드 요약 반영)
DEFAULT_WEIGHTS = {
    # Penalties
    "sugar_per_g": 2.0,            # g당 -2점
    "sodium_per_100mg": 1.0,       # 100mg당 -1점
    "processing_per_lvl": 5.0,     # 가공도 레벨당 -5점 (1~5)
    "gi_over55_per_pt": 0.3,       # GI 55 초과 1포인트당 -0.3점
    # Bonuses
    "fiber_per_g": 3.0,            # g당 +3점
    "protein_per_g": 1.5,          # g당 +1.5점
}

GOAL_ADJUST = {
    # 목표별 보정: 다이어트는 당/나트륨/가공도 패널티 강화, 섬유 보너스 강화
    "diet":   {"sugar_per_g": 2.3, "sodium_per_100mg": 1.1, "fiber_per_g": 3.3, "protein_per_g": 1.4},
    # 벌크는 단백질 보너스 강화, 당/나트륨은 기본 유지
    "bulk":   {"protein_per_g": 1.9, "fiber_per_g": 2.7},
    # 린(체지방 감량/근육 유지)은 당/가공도 패널티와 단백질/섬유 보너스 균형
    "lean":   {"sugar_per_g": 2.1, "processing_per_lvl": 5.2, "fiber_per_g": 3.2, "protein_per_g": 1.6},
}

SAFE_COLS = [
    "energy_kcal","protein_g","fat_g","carb_g",
    "fiber_g","sugar_g","sodium_mg","glycemic_index","processing_level"
]

def _safe(x: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(x): return default
        return float(x)
    except Exception:
        return default

def get_weights_for_goal(goal: str | None) -> Dict[str, float]:
    w = DEFAULT_WEIGHTS.copy()
    if goal:
        goal = str(goal).lower()
        if goal in GOAL_ADJUST:
            for k, v in GOAL_ADJUST[goal].items():
                w[k] = v
    return w

def calculate_health_score_row(row: pd.Series, goal: str | None = None) -> float:
    """
    0~100 스케일의 건강 점수 계산 (안전/결측 처리 포함).
    goal: 'diet'|'bulk'|'lean'|None
    """
    w = get_weights_for_goal(goal)

    sugar   = _safe(row.get("sugar_g"), 0.0)
    sodium  = _safe(row.get("sodium_mg"), 0.0)
    fiber   = _safe(row.get("fiber_g"), 0.0)
    protein = _safe(row.get("protein_g"), 0.0)
    gi      = _safe(row.get("glycemic_index"), 55.0)
    proc    = _safe(row.get("processing_level"), 3.0)

    score = 100.0
    # penalties
    score -= sugar * w["sugar_per_g"]
    score -= (sodium / 100.0) * w["sodium_per_100mg"]
    score -= proc * w["processing_per_lvl"]
    score -= max(0.0, gi - 55.0) * w["gi_over55_per_pt"]
    # bonuses
    score += fiber * w["fiber_per_g"]
    score += protein * w["protein_per_g"]

    return float(np.clip(score, 0.0, 100.0))

def add_or_recalculate_health_scores(df: pd.DataFrame, goal: str | None = None) -> pd.DataFrame:
    """
    df에 health_score 컬럼을 추가하거나 재계산하여 반환.
    """
    # 필요한 컬럼이 없으면 기본값 채우기
    for col in SAFE_COLS:
        if col not in df.columns:
            df[col] = 0.0
    df["health_score"] = df.apply(lambda r: calculate_health_score_row(r, goal=goal), axis=1)
    return df

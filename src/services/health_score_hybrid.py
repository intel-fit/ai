# src/services/health_score_hybrid.py
from __future__ import annotations
import pandas as pd

# 목표별로 규칙 비중을 다르게 줄 수도 있음 (선택)
GOAL_ALPHA = {
    "diet": 0.7,   # 규칙 70%, ML 30%
    "lean": 0.6,
    "bulk": 0.5,   # 벌크는 ML 비중 조금 더
}

def hybrid_health_score(df: pd.DataFrame, alpha: float | None = 0.6, user_goal: str | None = None) -> pd.DataFrame:
    if "health_score" not in df.columns:
        raise ValueError("DataFrame must contain 'health_score'.")
    # ml_health_score가 없으면 규칙 점수로 대체
    if "ml_health_score" not in df.columns:
        df["ml_health_score"] = df["health_score"]

    a = alpha if alpha is not None else 0.6
    if user_goal:
        a = GOAL_ALPHA.get(str(user_goal).lower(), a)

    df["hybrid_health_score"] = (a * df["health_score"] + (1.0 - a) * df["ml_health_score"]).clip(0, 100)
    return df

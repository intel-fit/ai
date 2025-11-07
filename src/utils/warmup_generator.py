# src/utils/warmup_generator.py
from __future__ import annotations
import math
from typing import List, Dict

def generate_warmup_sets(exercise: Dict, main_weight: float) -> List[Dict]:
    """
    첫 복합 운동을 위한 워밍업 세트 구성.
    - main_weight: 본 세트 목표 중량(kg)
    """
    warmups = []
    if main_weight <= 0:
        # 맨몸운동/밴드 등은 워밍업 불필요
        return []

    # 워밍업 비율
    warmup_ratios = [0.4, 0.6]  # 전체 중량의 40%, 60%
    warmup_reps = [8, 5]
    rest_secs = [40, 60]

    for i, ratio in enumerate(warmup_ratios):
        warmups.append({
            "set": i + 1,
            "weight_kg": round(main_weight * ratio, 1),
            "reps": warmup_reps[i],
            "rest_sec": rest_secs[i],
            "note": f"{int(ratio*100)}% load warm-up",
        })

    return warmups

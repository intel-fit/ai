# -*- coding: utf-8 -*-
"""
meal_optimizer.py
Linear Programming 기반 식단 매크로 정밀 조정 엔진
"""

from typing import List, Dict, Tuple
import numpy as np
import pulp  # pip install pulp

def optimize_meal_macros(
    food_items: List[Dict],
    target: Dict[str, float],
    tol_ratio: float = 0.08
) -> Tuple[List[Tuple[Dict, float]], Dict[str, float]]:
    """
    매크로 오차를 최소화하는 multiplier 조합을 계산한다.
    - 고정 serving(is_fixed_serving=True)은 multiplier=1.0 고정
    - 나머지 음식은 0.5~2.0배까지 조정 가능
    """

    prob = pulp.LpProblem("MealOptimization", pulp.LpMinimize)

    # 변수 생성
    vars_ = {}
    for idx, item in enumerate(food_items):
        if item.get("is_fixed_serving"):
            vars_[idx] = pulp.LpVariable(f"x_{idx}", 1.0, 1.0)
        else:
            vars_[idx] = pulp.LpVariable(f"x_{idx}", 0.5, 2.0)

    # 목표: 매크로 오차 최소화
    kcal_diff = pulp.LpVariable("kcal_diff", lowBound=0)
    prot_diff = pulp.LpVariable("prot_diff", lowBound=0)
    fat_diff  = pulp.LpVariable("fat_diff", lowBound=0)
    carb_diff = pulp.LpVariable("carb_diff", lowBound=0)

    kcal_sum = pulp.lpSum([vars_[i] * item["ps_energy_kcal"] for i, item in enumerate(food_items)])
    prot_sum = pulp.lpSum([vars_[i] * item["ps_protein_g"]  for i, item in enumerate(food_items)])
    fat_sum  = pulp.lpSum([vars_[i] * item["ps_fat_g"]      for i, item in enumerate(food_items)])
    carb_sum = pulp.lpSum([vars_[i] * item["ps_carb_g"]     for i, item in enumerate(food_items)])

    # 절대값 형태의 오차식 추가
    prob += kcal_sum - target["kcal"] <= kcal_diff
    prob += -(kcal_sum - target["kcal"]) <= kcal_diff
    prob += prot_sum - target["protein_g"] <= prot_diff
    prob += -(prot_sum - target["protein_g"]) <= prot_diff
    prob += fat_sum - target["fat_g"] <= fat_diff
    prob += -(fat_sum - target["fat_g"]) <= fat_diff
    prob += carb_sum - target["carb_g"] <= carb_diff
    prob += -(carb_sum - target["carb_g"]) <= carb_diff

    # 목적 함수: 전체 오차 최소화
    prob += 10 * kcal_diff + 5 * prot_diff + 3 * fat_diff + 3 * carb_diff

    # Solver 실행
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    # 결과 해석
    optimized_items = []
    for idx, item in enumerate(food_items):
        mult = vars_[idx].value()
        optimized_items.append((item, round(mult, 3)))

    totals = {
        "kcal": sum(item["ps_energy_kcal"] * m for item, m in optimized_items),
        "protein_g": sum(item["ps_protein_g"] * m for item, m in optimized_items),
        "fat_g": sum(item["ps_fat_g"] * m for item, m in optimized_items),
        "carb_g": sum(item["ps_carb_g"] * m for item, m in optimized_items),
    }

    return optimized_items, totals

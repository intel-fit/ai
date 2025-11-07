# src/utils/progression_engine.py
from __future__ import annotations
from typing import Dict, List

def adjust_load_based_on_log(exercise: Dict, log_entry: Dict) -> Dict:
    """
    이전 세션 로그를 기반으로 무게, 반복수 조정
    log_entry = {
        "actual_reps": int,
        "target_reps": int,
        "actual_weight": float,
    }
    """
    if not log_entry:
        return {
            "weight_kg": exercise.get("weight_kg", 0),
            "reps": exercise.get("reps", 10),
            "note": "no previous log"
        }

    actual_reps = log_entry.get("actual_reps", 0)
    target_reps = log_entry.get("target_reps", 0)
    prev_weight = log_entry.get("actual_weight", exercise.get("weight_kg", 0))

    diff = actual_reps - target_reps
    new_weight = prev_weight
    note = ""

    if diff >= 2:
        new_weight = round(prev_weight * 1.05, 1)
        note = f"✅ Progressed +5% (from {prev_weight}kg → {new_weight}kg)"
    elif diff <= -3:
        new_weight = round(prev_weight * 0.9, 1)
        note = f"⚠️ Reduced -10% (from {prev_weight}kg → {new_weight}kg)"
    else:
        note = "➡ Maintained load"

    # 반복수 조정
    new_reps = max(6, min(20, target_reps + diff // 2))

    return {
        "weight_kg": new_weight,
        "reps": new_reps,
        "note": note
    }


def apply_progression(plan: List[Dict], progress_logs: Dict[str, Dict]) -> List[Dict]:
    """
    전체 루틴에 대해 progression 적용
    progress_logs = { exerciseId: {actual_reps, target_reps, actual_weight}, ... }
    """
    updated_plan = []
    for day in plan:
        new_exercises = []
        for ex in day.get("exercises", []):
            ex_id = ex.get("exerciseId")
            if ex_id in progress_logs:
                adj = adjust_load_based_on_log(ex, progress_logs[ex_id])
                ex["weight_kg"] = adj["weight_kg"]
                ex["reps"] = adj["reps"]
                ex["progress_note"] = adj["note"]
            new_exercises.append(ex)
        day["exercises"] = new_exercises
        updated_plan.append(day)
    return updated_plan

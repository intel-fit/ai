# ==========================================
# src/services/exercise_planner.py  (v2.1 realistic+age-aware)
# ==========================================
import os, random
from typing import List, Dict, Tuple, Set
from sqlalchemy import text, create_engine
from src.schemas import UserExerciseContext
from src.utils.muscle_maps import (
    MUSCLE_KEYWORDS, GOAL_PARAMS, SPLIT_TEMPLATES,
    FOCUS_TO_GROUPS, DEFAULT_HOME_EQUIPS
)
from src.utils.contraindications import CONTRAINDICATIONS
from src.services.hybrid_exercise_score import predict_ai_score
import numpy as np  # 꼭 추가해줘야 함

# ✅ 운동 DB 연결
EXERCISE_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "exercise.db")
if not os.path.exists(EXERCISE_DB_PATH):
    raise FileNotFoundError(f"⚠️ 운동 DB 파일을 찾을 수 없습니다: {EXERCISE_DB_PATH}")
exercise_engine = create_engine(f"sqlite:///{EXERCISE_DB_PATH}", connect_args={"check_same_thread": False})


# ---------------------------
# 연령대 해석 (규칙 기반; 추후 ML로 대체 가능)
# ---------------------------
def age_profile(age: int) -> Dict:
    """
    age_band: 'youth'(<30), 'adult'(30-54), 'senior'(55+)
    규칙 기반 안전 보정값 반환 (초기 MVP에 적합, 추후 ML 가중치로 대체 가능)
    """
    if age is None:
        return {"band": "adult", "core_bias": 0.0, "set_delta": 0, "rest_delta": 0, "avoid_oly": False}
    if age >= 55:
        return {
            "band": "senior",
            "core_bias": 0.8,      # 코어·균형 우선
            "set_delta": -1,       # 세트수 살짝 감산
            "rest_delta": +15,     # 휴식 15초 가산
            "avoid_oly": True      # 올림픽 리프트 회피
        }
    elif age < 30:
        return {"band": "youth", "core_bias": 0.0, "set_delta": 0, "rest_delta": -5, "avoid_oly": False}
    else:
        return {"band": "adult", "core_bias": 0.0, "set_delta": 0, "rest_delta": 0, "avoid_oly": False}


# ===========================
# 메인 진입점
# ===========================
def generate_week_plan(ctx: UserExerciseContext):
    equips = ctx.available_equipment or (DEFAULT_HOME_EQUIPS if ctx.environment == "home" else None)

    # 분할 자동 결정 (숙련도 + 연령대 보정)
    split = determine_split(ctx)

    # 부위 우선순위 (인바디 + 연령대 코어 편향 보정)
    priority = compute_muscle_priority(ctx)

    used_ids: Set[str] = set()
    plan = []

    for day, focus in enumerate(split, start=1):
        if focus.lower() == "rest":
            plan.append({"day": day, "focus": "Rest", "exercises": []})
            continue

        target_groups = FOCUS_TO_GROUPS.get(focus, [])
        candidates = fetch_candidates(target_groups, equips, ctx.health_conditions, ctx.age)

        # 다양성/우선순위 기반 선택
        chosen = pick_exercises(candidates, priority, target_groups, k=5, used_ids=used_ids, focus=focus)
        used_ids.update(e["exerciseId"] for e in chosen)

        # 세트/반복/휴식/강도 부여 (goal + exp + age + condition)
        session = attach_sets_reps(chosen, ctx)
        plan.append({"day": day, "focus": focus, "exercises": session})

    summary = summarize_plan(ctx, priority, split)
    # ---------------------------
    # Hybrid Score 계산 (💡여기가 마지막 부분)
    # ---------------------------
    ai_score = predict_ai_score(ctx, [ex for day in plan for ex in day["exercises"]])
    rule_score = np.mean([len(day["exercises"]) for day in plan]) / 5  # 간단한 루틴 충실도 지표
    alpha = 0.6
    hybrid_score = round(alpha * rule_score + (1 - alpha) * ai_score, 3)

    # ---------------------------
    # 최종 반환
    # ---------------------------
    return {
        "goal": ctx.goal,
        "split": split,
        "summary": summary,
        "plan": plan,
        "scores": {
            "rule_score": round(rule_score, 3),
            "ai_score": round(ai_score, 3),
            "hybrid_score": hybrid_score
        }
    }



# ===========================
# Split 자동 결정 (연령대 보정)
# ===========================
def determine_split(ctx: UserExerciseContext) -> List[str]:
    ap = age_profile(ctx.age)
    if ctx.experience == "beginner":
        base = ["Upper","Lower","Rest","Upper","Lower","Rest","Rest"]
        # 시니어는 코어 안정화 데이 1회 삽입
        if ap["band"] == "senior":
            base[4] = "Core"   # Day5를 코어 안정화로
        return base[:ctx.plan_days]

    elif ctx.experience == "intermediate":
        base = ["Push","Pull","Legs","Rest","Push","Pull","Rest"]
        if ap["band"] == "senior":
            base[2] = "Legs"   # 유지
            base[4] = "Core"   # 하나는 코어
        return base[:ctx.plan_days]

    else:  # advanced
        base = ["Chest","Back","Legs","Shoulders","Arms","Rest","Rest"]
        if ap["band"] == "senior":
            base[3] = "Core"   # 어깨 대신 코어 안정화
        return base[:ctx.plan_days]


# ===========================
# 부위 우선순위 (인바디 + 연령대)
# ===========================
def compute_muscle_priority(ctx: UserExerciseContext) -> Dict[str, float]:
    base = {k: 1.0 for k in MUSCLE_KEYWORDS.keys()}
    ib = ctx.inbody.dict()
    ap = age_profile(ctx.age)

    for group, vals in ib.items():
        m, f = vals.get("muscle_score"), vals.get("fat_score")
        if m is not None:
            base[group] += max(0.0, -m) * 0.8
        if f is not None:
            base[group] += max(0.0, f) * (0.6 if ctx.goal in ["fat_loss","functional"] else 0.3)

    if ap["band"] == "senior":
        base["core"] += ap["core_bias"]
        base["legs"] += 0.5
        base["glutes"] += 0.5

    return base


# ===========================
# 운동 후보 필터링 (모든 키워드 OR, 연령·건강 금기)
# ===========================
def fetch_candidates(groups: List[str], equips: List[str] | None, conditions: List[str], age: int) -> List[dict]:
    avoid_kw, prefer_kw = set(), set()
    for c in conditions or []:
        rule = CONTRAINDICATIONS.get(c)
        if rule:
            avoid_kw.update(rule.get("avoid_keywords", []))
            prefer_kw.update(rule.get("prefer_keywords", []))

    # 연령대 기반 금기(가벼운 규칙) - 시니어는 올림픽 리프트류 회피
    if age_profile(age)["avoid_oly"]:
        avoid_kw.update({"스내치", "클린", "저크", "오버헤드 스쿼트"})

    # (targetMuscles OR bodyParts) 에 대해 그룹별 모든 키워드를 OR 검색
    like_parts = []
    params = {}
    for g in groups:
        kws = MUSCLE_KEYWORDS.get(g, [])
        if not kws:
            continue
        sub_parts = []
        for i, kw in enumerate(kws):
            sub_parts.append(f"targetMuscles LIKE :kw_{g}_{i} OR bodyParts LIKE :kw2_{g}_{i}")
            params[f"kw_{g}_{i}"] = f"%{kw}%"
            params[f"kw2_{g}_{i}"] = f"%{kw}%"
        like_parts.append("(" + " OR ".join(sub_parts) + ")")
    like_clause = " OR ".join(like_parts) if like_parts else "1=1"

    equip_clause = ""
    if equips:
        equip_terms = [f"equipments LIKE :e{i}" for i,_ in enumerate(equips)]
        for i, e in enumerate(equips):
            params[f"e{i}"] = f"%{e}%"
        equip_clause = "AND (" + " OR ".join(equip_terms) + ")"

    sql = f"""
        SELECT exerciseId, name, targetMuscles, bodyParts, equipments, instructions
        FROM exerciseCategory
        WHERE ({like_clause})
        {equip_clause}
    """

    with exercise_engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    # 건강/연령 금기 적용 + 선호 가점
    candidates = []
    for r in rows:
        blob = (r["name"] or "") + " " + (r["instructions"] or "")
        if any(a in blob for a in avoid_kw):
            continue
        pref = 1.0 if any(p in blob for p in prefer_kw) else 0.0
        candidates.append({**r, "_pref": pref})
    return candidates


# ===========================
# 샘플링 (부위 우선 + 다양성 보장 + Lower 보장)
# ===========================
def pick_exercises(
    candidates: List[dict],
    priority: Dict[str, float],
    groups: List[str],
    k: int = 5,
    used_ids: Set[str] | None = None,
    focus: str = ""
) -> List[dict]:
    used_ids = used_ids or set()
    weighted: List[Tuple[float, dict]] = []

    for c in candidates:
        if c["exerciseId"] in used_ids:
            continue
        txt = f"{c.get('targetMuscles','')} {c.get('bodyParts','')}"
        w = 0.0
        for g in groups:
            if any(kw in txt for kw in MUSCLE_KEYWORDS.get(g, [])):
                w += priority.get(g, 1.0)
        w += c.get("_pref", 0)
        if w > 0:
            weighted.append((w, c))

    weighted.sort(key=lambda x: x[0], reverse=True)

    chosen: List[dict] = []
    seen_targets: Set[str] = set()
    seen_equips: Set[str] = set()

    for _, c in weighted:
        if len(chosen) >= k:
            break
        t = (c.get("targetMuscles") or "").strip()
        e = (c.get("equipments") or "").strip()

        # 동일 타깃/장비 과다 중복 억제
        if any(t and (t in s or s in t) for s in seen_targets):
            continue
        if e and e in seen_equips:
            continue

        chosen.append(c)
        if t:
            seen_targets.add(t)
        if e:
            seen_equips.add(e)

    # ✅ Lower 세션 보정: 다리/둔근 최소 2개 보장
    if focus == "Lower":
        leg_kws = set(MUSCLE_KEYWORDS.get("legs", []) + MUSCLE_KEYWORDS.get("glutes", []))
        def is_leglike(item: dict) -> bool:
            txt = f"{item.get('targetMuscles','')} {item.get('bodyParts','')}"
            return any(kw in txt for kw in leg_kws)

        leg_count = sum(1 for it in chosen if is_leglike(it))
        if leg_count < 2:
            extras = [c for _, c in weighted if is_leglike(c) and c not in chosen]
            random.shuffle(extras)
            for ex in extras[: (2 - leg_count)]:
                # 장비·중복 최소화 조건 간단 적용
                if ex.get("equipments") in seen_equips:
                    continue
                chosen.append(ex)
                seen_equips.add(ex.get("equipments",""))

        # 코어만 잔뜩 나오는 상황 방지: 코어 비중 제한 (최대 2개)
        core_kws = set(MUSCLE_KEYWORDS.get("core", []))
        core_items = [it for it in chosen if any(kw in f"{it.get('targetMuscles','')} {it.get('bodyParts','')}" for kw in core_kws)]
        if len(core_items) > 2:
            # 코어 초과분은 제거하고 다리/둔근으로 대체
            surplus = core_items[2:]
            for s in surplus:
                chosen.remove(s)
            replacements = [c for _, c in weighted if is_leglike(c) and c not in chosen]
            for r in replacements[: len(surplus)]:
                chosen.append(r)

    random.shuffle(chosen)
    return chosen[:k]


# ===========================
# 세트/반복/강도 설정 (goal+exp+age+condition)
# ===========================
def attach_sets_reps(ex_list: List[dict], ctx: UserExerciseContext) -> List[dict]:
    p = GOAL_PARAMS[ctx.goal].copy()
    ap = age_profile(ctx.age)

    # 숙련도 보정
    if ctx.experience == "beginner":
        p["sets"] = (max(2, p["sets"][0]-1), max(3, p["sets"][1]-1))
        p["rest_sec"] = (max(30, p["rest_sec"][0]-15), max(90, p["rest_sec"][1]-15))
    elif ctx.experience == "advanced":
        p["sets"] = (p["sets"][0]+1, p["sets"][1]+1)

    # 연령 보정
    if ap["set_delta"] != 0:
        p["sets"] = (max(1, p["sets"][0]+ap["set_delta"]), max(2, p["sets"][1]+ap["set_delta"]))
    if ap["rest_delta"] != 0:
        p["rest_sec"] = (max(20, p["rest_sec"][0]+ap["rest_delta"]), max(30, p["rest_sec"][1]+ap["rest_delta"]))

    # 건강 상태 보정 (보수화)
    if any(c in ["허리통증","무릎통증","어깨충돌","어깨통증","손목불안정"] for c in (ctx.health_conditions or [])):
        p["intensity"] = "low-moderate"
        p["reps"] = (max(10, p["reps"][0]), max(15, p["reps"][1]))

    def pick_range(r: Tuple[int,int]) -> int:
        return random.randint(r[0], r[1])

    out = []
    for e in ex_list:
        out.append({
            "exerciseId": e["exerciseId"],
            "name": e["name"],
            "target": e["targetMuscles"],
            "equip": e["equipments"],
            "sets": pick_range(p["sets"]),
            "reps": pick_range(p["reps"]),
            "rest_sec": pick_range(p["rest_sec"]),
            "intensity": p["intensity"],
        })
    return out


# ===========================
# 요약 문장 생성
# ===========================
def summarize_plan(ctx: UserExerciseContext, priority: Dict[str, float], split: List[str]) -> str:
    top_focus = sorted(priority.items(), key=lambda x: x[1], reverse=True)[:3]
    top_muscles = ", ".join([m for m, _ in top_focus])
    summary = (
        f"{ctx.age}세 {ctx.sex} {ctx.experience} 레벨 사용자를 위한 {ctx.goal} 루틴입니다. "
        f"주요 강화 부위는 {top_muscles}이며, "
        f"{ctx.plan_days}일 동안 {', '.join(split)} 분할로 구성되었습니다."
    )
    if ctx.health_conditions:
        summary += f" 건강 상태({', '.join(ctx.health_conditions)})를 고려하여 부담 운동은 제외했습니다."
    return summary

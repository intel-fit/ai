# ==========================================
# src/services/exercise_planner.py  (v2.4 time-aware + feedback-aware)
# ==========================================
import os, random
import math
from typing import List, Dict, Tuple, Set, Optional
from sqlalchemy import text, create_engine
from sqlalchemy.orm import Session
from src.schemas import UserExerciseContext
from src.utils.muscle_maps import (
    MUSCLE_KEYWORDS, GOAL_PARAMS, SPLIT_TEMPLATES,
    FOCUS_TO_GROUPS, DEFAULT_HOME_EQUIPS
)
from src.utils.contraindications import CONTRAINDICATIONS
from src.services.hybrid_exercise_score import predict_ai_score
import numpy as np
from src.utils.load_rules import suggest_start_load, suggest_tempo, suggest_rir
from src.utils.warmup_generator import generate_warmup_sets
from src.utils.progression_engine import apply_progression
from src.services.ml_progression_model import predict_next_weight
from src.services.exercise_feedback_service import get_user_feedback_profile
import pickle
from src.services.exercise_ml_features import build_exercise_feature_vector


from src.services.exercise_ml_features import build_exercise_feature_vector

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "exercise_model.pkl")
MODEL_PATH = os.path.abspath(MODEL_PATH)

# =======================
# ML 모델 Optional Load
# =======================
import pickle

def load_ml_model():
    if not os.path.exists(MODEL_PATH):
        print("⚠ ML 모델이 없어 Rule-based만 사용합니다.")
        return None
    try:
        with open(MODEL_PATH, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        print("⚠ ML 모델 로딩 실패 → Rule-based로 진행:", e)
        return None

ML_MODEL = load_ml_model()




# ✅ 운동 DB 연결
EXERCISE_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "food_db.sqlite")
if not os.path.exists(EXERCISE_DB_PATH):
    raise FileNotFoundError(f"⚠️ 운동 DB 파일을 찾을 수 없습니다: {EXERCISE_DB_PATH}")
exercise_engine = create_engine(f"sqlite:///{EXERCISE_DB_PATH}", connect_args={"check_same_thread": False})


# ===========================
# Focus별 최소 쿼터 규칙 (비율/최소개수 혼합)
# 핵심: 먼저 쿼터를 채우고, 남는 슬롯은 기존 가중치 우선순위로 보충
# ===========================
FOCUS_QUOTAS = {
    "Push": [
        # (그룹키, 최소개수)
        ("chest", 2),       # 가슴 중심
        ("shoulders", 1),   # 어깨 보조
        ("triceps", 1),     # 삼두 보조
    ],
    "Pull": [
        ("back", 3),        # 광배/상·중·하부 등 포함
        ("biceps", 1),      # 이두 보조
    ],
    "Legs": [
        ("quads", 1),
        ("hamstrings", 1),
        ("glutes", 1),
        ("calves", 1),
    ],
    "Arms": [
    ("biceps", 1),
    ("triceps", 1),
    ("forearms", 1)   # 선택사항
    ],

    # 기타 분할도 확장 가능
    "Upper": [("chest",1),("back",1),("shoulders",1),("biceps",1),("triceps",1)],
    "Lower": [("quads",1),("hamstrings",1),("glutes",1),("calves",1),("core",1)],
    "Core":  [("core",2)]
}
FOCUS_ALIAS = {
    "arm": "Arms",
    "arms": "Arms",
    "bicep": "Arms",
    "biceps": "Arms",
    "tricep": "Arms",
    "triceps": "Arms",

    "leg": "Legs",
    "legs": "Legs",
    "lowerbody": "Legs",
    
    "upperbody": "Upper",
    "upper": "Upper",

    "push": "Push",
    "pull": "Pull",

    "core": "Core",
    "abs": "Core",
    "ab": "Core",

    "chest": "Push",
    "back": "Pull",
    "shoulder": "Push",
    "shoulders": "Push",
}

EXERCISE_TIME_FACTORS = {
    "compound": {"time_per_set_sec": 40, "time_per_rep_sec": 2.4},
    "isolation": {"time_per_set_sec": 32, "time_per_rep_sec": 2.2},
    "functional": {"time_per_set_sec": 45, "time_per_rep_sec": 2.3},
}
SETTING_OVERHEAD_SEC = {
    "바벨": 15, "덤벨": 10, "스미스 머신": 15, "케이블": 12,
    "머신": 10, "레버리지 머신": 10, "EZ 바벨": 12
}
TIME_TOLERANCE = 0.03  # 3%
MAX_TIME_FIT_ITER = 4

FOCUS_INCLUDE = {
    "Push": {"chest", "shoulders", "triceps"},
    "Pull": {"back", "biceps"},
    "Legs": {"quads", "hamstrings", "glutes", "calves", "core"},
    "Arms": {"biceps", "triceps"},
}
FOCUS_EXCLUDE = {
    "Push": {"biceps", "forearms"},   # 전완/이두 과다 진입 방지
    "Pull": {"triceps",},             # 삼두 과다 진입 방지
    "Arms": set()
    # Legs는 제외 규칙 없음
}


def _belongs_to_groups(item: dict, groups: set[str]) -> bool:
    txt = f"{item.get('targetMuscles','')} {item.get('bodyParts','')}"
    for g in groups:
        if any(kw in txt for kw in MUSCLE_KEYWORDS.get(g, [])):
            return True
    return False


def _conflicts_groups(item: dict, groups: set[str]) -> bool:
    return _belongs_to_groups(item, groups)


# 그룹키 -> 후보 매칭에 사용할 키워드 집합(이미 MUSCLE_KEYWORDS에 정의되어 있음)
def _has_group_match(item_text: str, group_key: str) -> bool:
    kws = MUSCLE_KEYWORDS.get(group_key, [])
    return any(kw in item_text for kw in kws)


# ---------------------------
# 연령대 해석
# ---------------------------
def age_profile(age: Optional[int]) -> Dict:
    if age is None:
        return {"band": "adult", "core_bias": 0.0, "set_delta": 0, "rest_delta": 0, "avoid_oly": False}
    if age >= 55:
        return {"band":"senior","core_bias":0.8,"set_delta":-1,"rest_delta":+15,"avoid_oly":True}
    elif age < 30:
        return {"band":"youth","core_bias":0.0,"set_delta":0,"rest_delta":-5,"avoid_oly":False}
    else:
        return {"band":"adult","core_bias":0.0,"set_delta":0,"rest_delta":0,"avoid_oly":False}


# ===========================
# 메인 진입점
# ===========================
def generate_week_plan(ctx: UserExerciseContext, session: Session):
    equips = ctx.available_equipment or (DEFAULT_HOME_EQUIPS if ctx.environment == "home" else None)

    # 🔥 유저 피드백 정보 로딩
    feedback_profile = get_user_feedback_profile(ctx.user_id, session)

    split = determine_split(ctx)
    priority = compute_muscle_priority(ctx)

    used_ids: Set[str] = set()
    plan = []

    for day, focus in enumerate(split, start=1):
        if focus.lower() == "rest":
            plan.append({"day": day, "focus": "Rest", "exercises": []})
            continue

        if focus == "Lower":
            lower_session = build_lower_session(ctx, used_ids)
            plan.append({"day": day, "focus": focus, "exercises": lower_session})
            continue

        target_groups = FOCUS_TO_GROUPS.get(focus, [])
        candidates = fetch_candidates(target_groups, equips, ctx.health_conditions, ctx)

        chosen = pick_exercises(
            candidates,
            priority,
            target_groups,
            k=5,
            used_ids=used_ids,
            focus=focus,
            feedback_profile=feedback_profile
        )
        used_ids.update(e["exerciseId"] for e in chosen)

        session_exs = attach_sets_reps(chosen, ctx, feedback_profile)
        plan.append({"day": day, "focus": focus, "exercises": session_exs})

        # 목표 시간이 있는 경우, 세션 시간이 너무 짧으면 운동을 추가
        if ctx.target_time_min:
            MIN_RATIO = 0.75   # 예: 목표의 75%는 최소 보장

            def est_session_min(exs):
                return sum(estimate_exercise_seconds(ex) for ex in exs) / 60.0

            cur_min = est_session_min(session_exs)

            if cur_min < ctx.target_time_min * MIN_RATIO:
                # 후보 중 남은 운동 가져오기
                extra_candidates = [
                    c for c in candidates
                    if c["exerciseId"] not in used_ids
                ]
                # 위에서 weighting 했던 것처럼 정렬
                extras = []
                for c in extra_candidates:
                    txt = f"{c.get('targetMuscles','')} {c.get('bodyParts','')}"
                    w = 0.0
                    for g in target_groups:
                        if any(kw in txt for kw in MUSCLE_KEYWORDS.get(g, [])):
                            w += priority.get(g, 1.0)
                    if w > 0:
                        extras.append((w, c))
                extras.sort(key=lambda x: x[0], reverse=True)

                # 최대 2개 추가
                for _, extra in extras[:2]:
                    used_ids.add(extra["exerciseId"])
                    session_exs.append(attach_sets_reps([extra], ctx, feedback_profile)[0])
                    cur_min = est_session_min(session_exs)
                    if cur_min >= ctx.target_time_min * MIN_RATIO:
                        break

            # 보정된 세션을 다시 저장
            plan[-1]["exercises"] = session_exs

    # 👉 시간 맞춤 보정: 목표 시간이 전달되면 세션별 총 시간을 ±3% 이내로 자동 튜닝
    if getattr(ctx, "target_time_min", None):
        plan = adjust_to_target_time(plan, ctx)

    summary = summarize_plan(ctx, priority, split)

    # 👉 총 소요시간/칼로리 메트릭(간단 추정) – 보정 이후 계산
    metrics = estimate_session_metrics(plan, user_weight_kg=(ctx.weight_kg or 70.0))

    # Hybrid Score
    ai_score = predict_ai_score(ctx, [ex for day in plan for ex in day["exercises"]])
    rule_score = np.mean([len(day["exercises"]) for day in plan]) / 5  # 간단한 충실도 지표
    alpha = 0.6
    hybrid_score = round(alpha * rule_score + (1 - alpha) * ai_score, 3)

    progress_logs = getattr(ctx, "progress_log", None)
    if progress_logs:
        plan = apply_progression(plan, progress_logs)
    
    return {
        "goal": ctx.goal,
        "split": split,
        "summary": summary,
        "plan": plan,
        "metrics": metrics,
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
        if ap["band"] == "senior":
            base[4] = "Core"
        return base[:ctx.plan_days]
    elif ctx.experience == "intermediate":
        base = ["Push","Pull","Legs","Rest","Push","Pull","Rest"]
        if ap["band"] == "senior":
            base[4] = "Core"
        return base[:ctx.plan_days]
    else:
        base = ["Chest","Back","Legs","Shoulders","Arms","Rest","Rest"]
        if ap["band"] == "senior":
            base[3] = "Core"
        return base[:ctx.plan_days]


# ===========================
# 부위 우선순위 (인바디 + 연령대)
# ===========================
# ===========================
# 부위 우선순위 (인바디 + 연령대) — 완전 안전 버전
# ===========================
INBODY_ALIAS = {
    # 상체/하체 개괄적 지표
    "upper": ["chest", "back", "shoulders", "biceps", "triceps", "forearms"],
    "lower": ["legs", "quads", "hamstrings", "glutes", "calves", "core"],

    # 팔 계열
    "arm": ["biceps","triceps","forearms"],
    "arms": ["biceps","triceps","forearms"],
    "bicep": ["biceps"],
    "biceps": ["biceps"],
    "tricep": ["triceps"],
    "triceps": ["triceps"],

    # 푸쉬/풀
    "push": ["chest","shoulders","triceps"],
    "pull": ["back","biceps"],

    # 코어
    "core": ["core"],
    "abs":  ["core"],
    "ab":   ["core"],

    # 하체
    "leg": ["legs","glutes","hamstrings","quads","calves"],
    "legs": ["legs","glutes","hamstrings","quads","calves"],
}

def compute_muscle_priority(ctx: UserExerciseContext) -> Dict[str, float]:
    """
    인바디 raw key → 실제 근육군 키로 안전 매핑 후 priority 반영하는 완전 안전 버전.
    MUSCLE_KEYWORDS와 항상 호환됨.
    """
    base = {k: 1.0 for k in MUSCLE_KEYWORDS.keys()}
    ib = ctx.inbody.dict()
    ap = age_profile(ctx.age)

    for raw_group, vals in ib.items():
        key = raw_group.lower().strip()

        # 1) alias 매핑 → 실제 근육군 리스트
        if key in INBODY_ALIAS:
            groups = INBODY_ALIAS[key]
        else:
            groups = [key]

        # 2) 매핑된 근육군을 실제 base key에만 반영
        for g in groups:
            if g not in base:
                continue  # 존재하지 않으면 skip

            m = vals.get("muscle_score")
            f = vals.get("fat_score")

            if m is not None:
                base[g] += max(0.0, -m) * 0.8

            if f is not None:
                base[g] += max(0.0, f) * (
                    0.6 if ctx.goal in ["fat_loss","functional"] else 0.3
                )

    # 3) 연령대 보정
    if ap["band"] == "senior":
        base["core"] += ap["core_bias"]
        base["legs"] += 0.5
        base["glutes"] += 0.5

    return base



# ===========================
# 운동 후보 필터링
# ===========================
def fetch_candidates(groups, equips, conditions, ctx):
    avoid_kw, prefer_kw = set(), set()
    for c in conditions:
        rule = CONTRAINDICATIONS.get(c, {})
        avoid_kw.update(rule.get("avoid_keywords", []))
        prefer_kw.update(rule.get("prefer_keywords", []))

    like_terms = []
    params = {}
    p_i = 0
    for g in groups:
        for kw in MUSCLE_KEYWORDS.get(g, []):
            like_terms.append(f"targetMuscles LIKE :p{p_i} OR bodyParts LIKE :p{p_i}")
            params[f"p{p_i}"] = f"%{kw}%"
            p_i += 1
    like_clause = " OR ".join(like_terms) or "1=1"

    equip_clause = ""
    if equips:
        e_parts = []
        for i, e in enumerate(equips):
            e_parts.append(f"equipments LIKE :e{i}")
            params[f"e{i}"] = f"%{e}%"
        equip_clause = " AND (" + " OR ".join(e_parts) + ")"

    ap = age_profile(ctx.age)
    diff_clause = ""
    risk_clause = ""
    if ctx.experience == "beginner":
        diff_clause = "AND difficulty != 'advanced'"
        risk_clause = "AND risk_score < 0.6"
    elif ctx.experience == "intermediate":
        risk_clause = "AND risk_score < 0.8"
    else:
        risk_clause = "AND risk_score < 1.0"
    if ap["band"] == "senior":
        diff_clause = "AND difficulty != 'advanced'"
        risk_clause = "AND risk_score < 0.5"

    sql = f"""
        SELECT exerciseId, name, targetMuscles, bodyParts, equipments,
               difficulty, risk_score, category, effectiveness, instructions
        FROM exerciseCategory
        WHERE ({like_clause}) {equip_clause} {diff_clause} {risk_clause}
    """

    with exercise_engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    out = []
    for r in rows:
        blob = (r["name"] or "") + " " + (r["instructions"] or "")
        if any(a in blob for a in avoid_kw):
            continue
        item = dict(r)
        item["_pref"] = 1.0 if any(p in blob for p in prefer_kw) else 0.0
        out.append(item)
    return out

# ================================================
# 머신러닝 기반 운동 점수 예측 함수 (임시/가상 모델)
# ================================================
def predict_exercise_ml_score(user_features, exercise):
    if ML_MODEL is None:
        return 0.0  # 모델 없으면 영향 0
    
    try:
        fv = build_exercise_feature_vector(user_features, exercise)
        pred = ML_MODEL.predict(fv.reshape(1, -1))[0]
        return max(0.05, min(1.0, float(pred)))
    except:
        return 0.0



# ===========================
# 샘플링 (부위 우선 + 다양성 + Lower 보장 + 피드백 반영)
# ===========================
def pick_exercises(
    candidates: List[dict],
    priority: Dict[str, float],
    groups: List[str],
    k: int = 5,
    used_ids: Set[str] | None = None,
    focus: str = "",
    feedback_profile: Optional[dict] = None
) -> List[dict]:

    used_ids = used_ids or set()
    focus_quotas = FOCUS_QUOTAS.get(focus, [])

    # ---------------------------
    # 1) 피드백 기반 가중치 계산 함수
    # ---------------------------
    def apply_feedback_weight(base_weight: float, c: dict) -> float:
        if not feedback_profile:
            return base_weight

        w = base_weight
        ex_id = c["exerciseId"]
        cat = (c.get("category") or "").lower()

        # 1️⃣ 개별 운동 선호/비선호
        if ex_id in feedback_profile.get("like_exercises", set()):
            w *= 1.30
        elif ex_id in feedback_profile.get("dislike_exercises", set()):
            w *= 0.60

        # 2️⃣ 부위(group) 선호/비선호
        for g in groups:
            if g in feedback_profile.get("like_groups", set()):
                w *= 1.20
            if g in feedback_profile.get("dislike_groups", set()):
                w *= 0.70

        # 3️⃣ 장비/카테고리 선호/비선호
        if cat in feedback_profile.get("like_equip", set()):
            w *= 1.15
        if cat in feedback_profile.get("dislike_equip", set()):
            w *= 0.80

        return w

    # ---------------------------
    # 2) 기본 + 피드백 가중치 계산
    # ---------------------------
    weighted: List[Tuple[float, dict]] = []
    for c in candidates:
        if c["exerciseId"] in used_ids:
            continue

        txt = f"{c.get('targetMuscles','')} {c.get('bodyParts','')}"
        base_w = 0.0

        # 부위 우선순위 반영
        for g in groups:
            if any(kw in txt for kw in MUSCLE_KEYWORDS.get(g, [])):
                base_w += priority.get(g, 1.0)

        # prefer 키워드 (_pref)
        base_w += c.get("_pref", 0)

        # 🔥 피드백 기반 가중치 반영
        final_w = apply_feedback_weight(base_w, c)
        # -----------------------------------------
        # 🔥 ML 점수 기반 가중치 추가 (모델이 있을 때만)
        # -----------------------------------------
        if ML_MODEL is not None and feedback_profile and "ml_features" in feedback_profile:
            try:
                ml_score = predict_exercise_ml_score(
                    feedback_profile["ml_features"],
                    c
                )
                final_w *= (1.0 + ml_score)
            except Exception as e:
                print("⚠ ML scoring failed → skip:", e)


        if final_w > 0:
            weighted.append((final_w, c))

    weighted.sort(key=lambda x: x[0], reverse=True)

    # ---------------------------
    # 3) Include / Exclude 필터
    # ---------------------------
    include = set(FOCUS_INCLUDE.get(focus, []))
    exclude = set(FOCUS_EXCLUDE.get(focus, []))

    if include:
        weighted = [(w, c) for w, c in weighted if _belongs_to_groups(c, include)]

    if exclude:
        weighted = [(w, c) for w, c in weighted if not _conflicts_groups(c, exclude)]

    # ---------------------------
    # 4) 선택 로직
    # ---------------------------
    chosen: List[dict] = []
    seen_targets: Set[str] = set()
    seen_equips: Set[str] = set()

    def _eligible(c: dict) -> bool:
        if c["exerciseId"] in {x["exerciseId"] for x in chosen}:
            return False
        t = (c.get("targetMuscles") or "").strip()
        e = (c.get("equipments") or "").strip()

        # 부위 중복 억제
        if any(t and (t in s or s in t) for s in seen_targets):
            return False

        # 장비 중복 억제
        if e and e in seen_equips:
            return False

        return True

    # ---- A) 쿼터 우선 채우기
    for group_key, need in focus_quotas:
        if len(chosen) >= k:
            break

        group_pool = [
            (w, c) for w, c in weighted
            if _has_group_match(f"{c.get('targetMuscles','')} {c.get('bodyParts','')}", group_key)
        ]

        for _, c in group_pool:
            if len([x for x in chosen if _has_group_match(
                    f"{x.get('targetMuscles','')} {x.get('bodyParts','')}", group_key)]) >= need:
                break

            if not _eligible(c):
                continue

            chosen.append(c)
            seen_targets.add(c.get("targetMuscles", "").strip())
            e = c.get("equipments", "")
            if e: seen_equips.add(e)

            if len(chosen) >= k:
                break

    # ---- B) 남는 슬롯 보충
    for _, c in weighted:
        if len(chosen) >= k:
            break
        if not _eligible(c):
            continue

        chosen.append(c)
        seen_targets.add(c.get("targetMuscles", "").strip())
        e = c.get("equipments", "")
        if e: seen_equips.add(e)

    # ---- C) Lower 보정
    if focus == "Lower":
        leg_kws = set(MUSCLE_KEYWORDS.get("legs", []) + MUSCLE_KEYWORDS.get("glutes", []))

        def is_leglike(item: dict) -> bool:
            txt = f"{item.get('targetMuscles','')} {item.get('bodyParts','')}"
            return any(kw in txt for kw in leg_kws)

        leg_count = sum(1 for it in chosen if is_leglike(it))

        # 다리 부족 → 다리 운동 추가
        if leg_count < 2:
            extras = [c for _, c in weighted if is_leglike(c) and c not in chosen]
            for ex in extras[: (2 - leg_count)]:
                chosen.append(ex)

        # 코어 과다 방지
        core_kws = set(MUSCLE_KEYWORDS.get("core", []))
        core_items = [it for it in chosen if any(
            kw in f"{it.get('targetMuscles','')} {it.get('bodyParts','')}"
            for kw in core_kws
        )]

        if len(core_items) > 2:
            surplus = core_items[2:]
            for s in surplus:
                chosen.remove(s)

    random.shuffle(chosen)
    # 디버그용 출력
    debug_exercise_weights(weighted, chosen)

    return chosen[:k]


# ===========================
# DEBUG: 추천 가중치/선택 과정 분석
# ===========================
def debug_exercise_weights(weighted_list, chosen):
    print("\n===== 🔍 EXERCISE WEIGHT DEBUG =====")
    for w, c in weighted_list[:15]:  # 상위 15개까지만
        print(f"[{c['exerciseId']}] {c['name']} | w={round(w,3)} | "
              f"target={c.get('targetMuscles')} | equip={c.get('equipments')}")
    print("----- 선택된 운동 -----")
    for c in chosen:
        print(f"✔ {c['exerciseId']} {c['name']}")
    print("====================================\n")


# ===========================
# 세트/반복/강도 설정
# ===========================
def attach_sets_reps(ex_list: List[dict], ctx: UserExerciseContext,  feedback_profile=None) -> List[dict]:
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
    # 건강 상태 보정
    if any(c in ["허리통증","무릎통증","어깨충돌","어깨통증","손목불안정"] for c in (ctx.health_conditions or [])):
        p["intensity"] = "low-moderate"
        p["reps"] = (max(10, p["reps"][0]), max(15, p["reps"][1]))

    compound_found = False
    
    def pick_range(r: Tuple[int,int]) -> int:
        return random.randint(r[0], r[1])

    out = []
    for e in ex_list:
        sets = pick_range(p["sets"])
        reps = pick_range(p["reps"])
        rest = pick_range(p["rest_sec"])
        # 안전 캡
        sets = max(1, min(6, sets))
        reps = max(6, min(20, reps))
        rest = max(20, min(150, rest))

        # ✅ 새로 추가: 시작무게 / 템포 / RIR
        start_load = suggest_start_load(
            exercise=e,
            user_weight_kg=getattr(ctx, "weight_kg", None),
            experience=ctx.experience,
            goal=ctx.goal,
        )
        # ML 기반 보정 (LightGBM)
        ml_entry = {
            "age": ctx.age,
            "experience": ctx.experience,
            "goal": ctx.goal,
            "weight_kg": start_load,
            "sets": sets,
            "reps": reps,
            "rest_sec": rest,
            "success_rate": 0.9,   # TODO: 이후 실제 수행 로그 반영
            "fatigue": 0.3         # TODO: wearable 연동 시 자동 계산 가능
        }
        predicted_weight = predict_next_weight(ml_entry)

        # 하이브리드 결합 (Rule + ML)
        alpha = 0.6
        final_weight = round(alpha * start_load + (1 - alpha) * predicted_weight, 1)

        # ============================================
        # 🔥 NEW: heavy/light 피드백 기반 무게 조정
        # ============================================
        if feedback_profile:
            ex_id = e["exerciseId"]

            # 사용자가 "무거워요" → 다음 추천에서 -10%
            if ex_id in feedback_profile.get("heavy_feedback", set()):
                final_weight = round(final_weight * 0.90, 1)

            # 사용자가 "가벼워요" → 다음 추천에서 +10%
            if ex_id in feedback_profile.get("light_feedback", set()):
                final_weight = round(final_weight * 1.10, 1)


        tempo = suggest_tempo(ctx.goal)
        rir = suggest_rir(ctx.goal, ctx.experience)

        # ✅ 첫 복합운동이면 워밍업 생성
        warmups = []
        if not compound_found and (e.get("category") or "").lower() == "compound":
            warmups = generate_warmup_sets(e, start_load)
            compound_found = True

        if ctx.experience == "beginner":
            intensity = "low-moderate"
        elif ctx.experience == "intermediate":
            intensity = "moderate-high"
        else:
            intensity = "high"

        out.append({
            "exerciseId": e["exerciseId"],
            "name": e["name"],
            "target": e.get("targetMuscles"),
            "equip": e.get("equipments"),
            "category": e.get("category"),
            "sets": sets,
            "reps": reps,
            "rest_sec": rest,
            "intensity": intensity,
            # 🔹 AI 예측 포함
            "rule_weight": start_load,
            "ml_pred": predicted_weight,
            "weight_kg": final_weight,
            "rir": rir,
            "tempo": tempo,
            "warmup": warmups,
            "note": "AI-weight hybrid applied"
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


LOWER_QUOTAS = [("quads",1),("hamstrings",1),("glutes",1),("calves",1),("core",1)]

def build_lower_session(ctx, used_ids):
    picked = []
    for muscle_key, need in LOWER_QUOTAS:
        groups = [muscle_key] if muscle_key != "core" else ["core"]
        cands = fetch_candidates(groups, ctx.available_equipment, ctx.health_conditions, ctx)
        weighted = []
        for c in cands:
            if c["exerciseId"] in used_ids:
                continue
            txt = f'{c.get("targetMuscles","")} {c.get("bodyParts","")}'
            w = 1.0 + sum(1.0 for kw in MUSCLE_KEYWORDS.get(muscle_key, []) if kw in txt) + c.get("_pref", 0)
            weighted.append((w, c))
        weighted.sort(key=lambda x: x[0], reverse=True)
        for _, c in weighted[:need*3]:
            if len([x for x in picked if x["exerciseId"] == c["exerciseId"]]) == 0:
                picked.append(c)
                used_ids.add(c["exerciseId"])
                break

    if len(picked) < 5:
        cands = fetch_candidates(["legs","glutes"], ctx.available_equipment, ctx.health_conditions, ctx)
        for c in cands:
            if c["exerciseId"] in used_ids: 
                continue
            picked.append(c)
            used_ids.add(c["exerciseId"])
            if len(picked) >= 5: 
                break

    return attach_sets_reps(picked, ctx)


# ===========================
# 👉 목표 시간 보정 로직
# ===========================
def adjust_to_target_time(plan: List[dict], ctx) -> List[dict]:
    """
    날짜별 target_time_min 적용 + 세트/반복/휴식의 안정적 조정 버전
    """
    def session_minutes(exs: List[dict]) -> float:
        return sum(estimate_exercise_seconds(ex) for ex in exs) / 60.0

    new_plan = []

    for day_idx, day in enumerate(plan, start=1):
        target = _resolve_day_target(ctx, day_idx)
        if not target or not day["exercises"] or day["focus"].lower() == "rest":
            new_plan.append(day)
            continue

        LO = target * (1 - TIME_TOLERANCE)
        HI = target * (1 + TIME_TOLERANCE)

        cur_day = {**day, "exercises": [ex.copy() for ex in day["exercises"]]}

        for _ in range(MAX_TIME_FIT_ITER):
            cur = session_minutes(cur_day["exercises"])
            if LO <= cur <= HI:
                break

            ratio = target / max(cur, 1e-6)
            adjusted = []

            # 줄일 때
            if ratio < 1.0:
                order = {"isolation":0,"functional":1,"compound":2}
                factor_sets = max(0.8, ratio)
                for ex in sorted(cur_day["exercises"], key=lambda x: order.get((x.get("category") or "compound").lower(),1)):
                    sets = max(1, int(round(ex["sets"] * factor_sets)))
                    reps = max(6, int(round(ex["reps"] * (0.9*ratio + 0.1))))
                    rest = max(20, int(ex["rest_sec"] * max(0.7, ratio)))
                    adjusted.append({**ex, "sets": sets, "reps": reps, "rest_sec": rest})

            # 늘릴 때
            else:
                order = {"compound":0,"functional":1,"isolation":2}
                factor_sets = min(1.25, ratio)
                for ex in sorted(cur_day["exercises"], key=lambda x: order.get((x.get("category") or "compound").lower(),1)):
                    sets = min(6, int(round(ex["sets"] * factor_sets)))
                    reps = min(20, int(round(ex["reps"] * (0.95*ratio + 0.05))))
                    rest = min(150, int(ex["rest_sec"] * min(1.25, ratio)))
                    adjusted.append({**ex, "sets": sets, "reps": reps, "rest_sec": rest})

            cur_day["exercises"] = adjusted

        new_plan.append(cur_day)

    return new_plan


# ===========================
# 간단 메트릭 추정 (시간/칼로리)
# ===========================
def estimate_session_metrics(plan: List[dict], user_weight_kg: float = 70.0) -> dict:
    # 카테고리별 대략적 MET(보수값)
    MET = {
        "compound": 5.5,
        "isolation": 4.0,
        "functional": 4.5,
        "core": 3.5
    }
    def session_minutes(exs: List[dict]) -> float:
        total_sec = 0
        for ex in exs:
            total_sec += estimate_exercise_seconds(ex)
        return total_sec / 60.0

    session_details = []
    total_min = 0.0
    total_kcal = 0.0
    for day in plan:
        if not day["exercises"]:
            session_details.append({"day": day["day"], "duration_min": 0, "kcal": 0, "avg_met": 0})
            continue
        dur_min = session_minutes(day["exercises"])
        avg_met = np.mean([MET.get(ex.get("category","compound"), 4.5) for ex in day["exercises"]])
        kcal = avg_met * 3.5 * user_weight_kg / 200 * dur_min  # 일반적 추정식
        session_details.append({
            "day": day["day"],
            "duration_min": round(dur_min, 1),
            "kcal": round(kcal, 1),
            "avg_met": round(float(avg_met), 2)
        })
        total_min += dur_min
        total_kcal += kcal

    return {
        "total_duration_min": round(total_min, 1),
        "total_kcal": round(total_kcal, 1),
        "session_details": session_details
    }


def estimate_exercise_seconds(ex: dict) -> int:
    """
    한 운동의 전체 소요 시간을 '세트 반복시간 + 세트간 휴식 + 세팅오버헤드'로 추정.
    """
    cat = (ex.get("category") or "compound").lower()
    f = EXERCISE_TIME_FACTORS.get(cat, EXERCISE_TIME_FACTORS["compound"])
    sets = int(ex.get("sets", 3))
    reps = int(ex.get("reps", 10))
    rest = int(ex.get("rest_sec", 90))

    # 템포가 "2-0-2"라면 한 반복에 대략 4초지만, 실제는 호흡/탑포즈 포함 → 보수적으로 time_per_rep_sec 사용
    per_set_movement = int(reps * f["time_per_rep_sec"])
    per_set_total = per_set_movement + rest  # 셋 간 휴식은 셋마다 1회로 모델링(마지막셋의 휴식은 다음 운동 세팅으로 상쇄)

    # 장비 세팅 오버헤드 (운동마다 1회)
    equip = (ex.get("equip") or ex.get("equipments") or "").strip()
    overhead = 0
    for key, sec in SETTING_OVERHEAD_SEC.items():
        if key in equip:
            overhead = sec
            break

    # 총합: (세트당 동작시간 + 세트간 휴식) * 세트수 + 오버헤드
    total = sets * per_set_total + overhead
    # 마지막 셋 뒤 휴식은 제외해 주는 보정(과대추정 방지)
    total -= rest
    return max(total, sets * (per_set_movement + 10))  # 최소한의 하한선


def _resolve_day_target(ctx, day_index: int) -> Optional[float]:
    """
    ctx.target_time_min이
      - 단일 숫자(예: 60)면 모든 날 동일
      - 리스트면 day_index(1-based)에 매핑
      - dict면 {1:60, 3:80} 식으로 특정 요일만 타겟
    없거나 0/음수인 경우 None 반환
    """
    t = getattr(ctx, "target_time_min", None)
    if t is None:
        return None
    if isinstance(t, (int, float)):
        return float(t) if t > 0 else None
    if isinstance(t, list):
        if 1 <= day_index <= len(t):
            return float(t[day_index-1]) if t[day_index-1] and t[day_index-1] > 0 else None
        return None
    if isinstance(t, dict):
        v = t.get(day_index)
        return float(v) if v and v > 0 else None
    return None


# ============================================
# ⭐ DAILY RECOMMENDER (NEW)
# ============================================
def generate_daily_plan(ctx: UserExerciseContext, session: Session):
    """
    단일 날짜용 운동 추천.
    """
    equips = ctx.available_equipment or (
        DEFAULT_HOME_EQUIPS if ctx.environment == "home" else None
    )

    feedback_profile = get_user_feedback_profile(ctx.user_id, session)

    # ----------------------
    # 1) focus 결정 (lower로 통일)
    # ----------------------
    priority = compute_muscle_priority(ctx)

    # ----------------------
    # 1) focus 결정 (+ alias 처리)
    # ----------------------
    raw_focus = None

    if getattr(ctx, "focus_muscle", None):
        raw_focus = ctx.focus_muscle.lower().strip()
    else:
        raw_focus = max(priority, key=priority.get).lower().strip()

    # alias 변환
    focus_key = FOCUS_ALIAS.get(raw_focus, raw_focus).capitalize()

    groups = FOCUS_TO_GROUPS.get(focus_key, [])

    # fallback
    if not groups:
        print(f"⚠️ Daily focus '{raw_focus}' → '{focus_key}' 매핑 실패 → Upper로 fallback")
        focus_key = "Upper"
        groups = FOCUS_TO_GROUPS["Upper"]


    # 안전장치: groups가 비었으면 arms/week priority 기반 fallback
    if not groups:
        print(f"⚠️ Daily focus '{raw_focus}' → '{focus_key}' 매핑 실패 → Upper로 fallback")
        focus_key = "Upper"
        groups = FOCUS_TO_GROUPS["Upper"]

    # ----------------------
    # 2) 후보 운동
    # ----------------------
    candidates = fetch_candidates(groups, equips, ctx.health_conditions, ctx)

    # ----------------------
    # 3) 운동 픽
    # ----------------------
    chosen = pick_exercises(
        candidates,
        priority,
        groups,
        k=5,
        used_ids=set(),
        focus=focus_key,
        feedback_profile=feedback_profile
    )

    # ----------------------
    # 4) 세트/반복 설정
    # ----------------------
    session_exs = attach_sets_reps(chosen, ctx, feedback_profile)

    # ----------------------
    # 5) 시간 기반 조정
    # ----------------------
    if getattr(ctx, "target_time_min", None):
        temp = [{"day": 1, "focus": focus_key, "exercises": session_exs}]
        temp = adjust_to_target_time(temp, ctx)
        session_exs = temp[0]["exercises"]

    # ----------------------
    # 7) 메트릭 계산
    # ----------------------
    metrics = estimate_session_metrics(
        [{"day": 1, "focus": focus_key, "exercises": session_exs}],
        user_weight_kg=(ctx.weight_kg or 70.0)
    )

    return {
        "focus": focus_key,
        "exercises": session_exs,
        "metrics": metrics
    }

import random
import re
import pandas as pd
import os
from typing import List, Dict, Tuple
from src.services.meal_optimizer import optimize_meal_macros
import json
FEEDBACK_PATH = os.path.join("src", "data", "user_feedback.json")

def _load_user_feedback():
    if not os.path.exists(FEEDBACK_PATH):
        return {}
    with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
        feedback_list = json.load(f)
    scores = {}
    for fb in feedback_list:
        food = fb.get("food_name")
        rating = float(fb.get("rating", 0))
        if food:
            scores[food] = max(0.0, min(100.0, rating * 20))  # 1~5 → 20~100 변환
    return scores


class MealPlanner:
    """
    지속 가능한 현실식 추천을 위한 최종 버전:
    - 다양성 엔진: 탄수/단백질 소스 회전, 핵심 키워드 중복 방지
    - 현실식 우선: 간식/스낵/가공식 캡, 메인 대체 불가
    - 목표별 kcal 분할 + serving 유연 조정
    - kcal/단백질 오차 제어 + fallback 템플릿
    """
    def __init__(self):
        self.RETRY_LIMIT = 3
        self.TOL_RATIO = 0.08
        self.FORCE_TEMPLATE = True
        self.user_pref_map = _load_user_feedback()


        # ---- 현실식 템플릿 (fallback) ----
        self.REALISTIC_TEMPLATES = [
            ["현미밥", "닭가슴살", "샐러드"],
            ["잡곡밥", "두부", "나물"],
            ["곤약밥", "닭가슴살", "야채볶음"],
            ["고구마", "계란", "브로콜리"],
            ["현미밥", "연어", "미소된장국"]
        ]

        # ---- 역할 키워드 ----
        self.ROLE_KEYWORDS = {
            "main":   ["밥", "면", "국수", "파스타", "리조또", "볶음밥", "덮밥", "현미", "잡곡", "귀리", "보리", "고구마", "감자", "곤약밥", "수수", "퀴노아"],
            "protein":["닭", "가슴살", "소고기", "돼지", "양고기", "계란", "달걀", "연어", "참치", "고등어", "두부", "유부", "콩", "스테이크", "생선", "오징어", "문어", "새우", "요거트"],
            "side":   ["샐러드", "야채", "채소", "김치", "나물", "무침", "볶음", "브로콜리", "수프", "스프", "국", "탕", "찌개", "된장", "미소", "김"]
        }

        # ---- 제외/가공/간식 키워드 ----
        self.SUPPLEMENT_KEYWORDS = ["프로틴", "단백질바", "보충제", "쉐이크", "아미노", "스파클링", "젤리", "제로", "가루", "분말"]
        self.DRINK_DESSERT_KEYWORDS = ["커피", "음료", "에이드", "주스", "라떼", "쿠키", "비스켓", "초콜릿", "디저트", "아이스크림", "시리얼", "스낵", "케이크"]
        self.HIGHLY_PROCESSED_KEYWORDS = ["피자", "버거", "핫도그", "튀김", "라면", "과자", "그래놀라", "칩", "파이", "크루아상", "도너츠", "마요", "소시지"]

        # ---- 다양성/회전 제약 ----
        self.DAILY_BREAD_CAP = 1            # 빵/베이글/식빵류 메인 최대 1식
        self.DAILY_NOODLE_CAP = 1           # 면/파스타 메인 최대 1식
        self.DAILY_PROCESSED_CAP = 2        # 가공/스낵/피자류 하루 최대 2품목(메인 불가)
        self.DAILY_SNACK_DRINK_CAP = 1      # 간식/음료 하루 최대 1품목(메인 불가)
        self.MIN_DISTINCT_CARB_SOURCES = 2  # 탄수 소스 최소 2종 회전
        self.MIN_DISTINCT_PROT_SOURCES = 2  # 단백질 소스 최소 2종 회전

        # ---- kcal 밴드 & 단백질 상한 ----
        self.ROLE_KCAL_BAND = 0.40  # ±40%
        self.PROTEIN_CAP_PER_MEAL = {"lean": 60.0, "diet": 60.0, "bulk": 80.0, "maintain": 70.0}

        # ---- carb/protein 소스 키워드 (회전용) ----
        self.CARB_SOURCES = {
            "rice_grain": ["밥", "현미", "잡곡", "귀리", "보리", "퀴노아", "수수"],
            "noodle":     ["면", "국수", "파스타", "칼국수", "라면"],  # 라면은 아래 가공 필터에도 걸림
            "bread":      ["빵", "베이글", "토스트", "식빵", "치아바타", "바게트"],
            "tuber":      ["고구마", "감자"],
            "konjac":     ["곤약밥"]
        }
        self.PROTEIN_SOURCES = {
            "poultry":   ["닭", "가슴살"],
            "red_meat":  ["소고기", "돼지", "양고기", "스테이크"],
            "seafood":   ["연어", "참치", "고등어", "생선", "오징어", "새우", "문어"],
            "egg":       ["계란", "달걀", "오므"],
            "soy":       ["두부", "콩", "유부"],
            "dairy":     ["요거트", "치즈", "우유"]
        }
         # ---- 데이터 경로 ----
        self.PAIR_JSON = os.path.join("src", "data", "food_pair_scores.json")
        self.user_pref_map = {}
        self.pair_map = {}
        if os.path.exists(self.PAIR_JSON):
            try:
                with open(self.PAIR_JSON, "r", encoding="utf-8") as f:
                    self.pair_map = json.load(f).get("pairs", {})
            except:
                self.pair_map = {}

    # ========== 분류/태그 ==========
    def _is_match_any(self, name: str, keywords: List[str]) -> bool:
        return any(kw in name for kw in keywords)

    def _is_supplement(self, name: str) -> bool:
        return self._is_match_any(name, self.SUPPLEMENT_KEYWORDS)

    def _is_drink_or_dessert(self, name: str) -> bool:
        return self._is_match_any(name, self.DRINK_DESSERT_KEYWORDS)

    def _is_highly_processed(self, name: str) -> bool:
        return self._is_match_any(name, self.HIGHLY_PROCESSED_KEYWORDS)

    def _is_meal_candidate(self, name: str) -> bool:
        # 식사로 부적합한 품목 제거
        if self._is_supplement(name) or self._is_drink_or_dessert(name):
            return False
        if self._is_highly_processed(name):
            return False
        bad = ["과자", "그래놀라", "칩", "파이", "쿠키", "비스켓", "도넛", "크루아상", "스낵"]
        if self._is_match_any(name, bad):
            return False
        return True

    def _classify_food_role(self, name: str) -> str:
        for role, kws in self.ROLE_KEYWORDS.items():
            if self._is_match_any(name, kws):
                return role
        if re.search("국|탕|찌개|스튜|수프|스프", name):
            return "side"
        if re.search("덮밥|오므라이스|카레", name):
            return "main"
        if re.search("닭|소고기|돼지|스테이크|생선", name):
            return "protein"
        return "misc"

    def _carb_source_tag(self, name: str) -> str:
        for tag, kws in self.CARB_SOURCES.items():
            if self._is_match_any(name, kws):
                return tag
        return "other"

    def _protein_source_tag(self, name: str) -> str:
        for tag, kws in self.PROTEIN_SOURCES.items():
            if self._is_match_any(name, kws):
                return tag
        return "other"

    # ========== 목표/서빙 ==========
    def _role_kcal_split(self, goal: str):
        g = (goal or "").lower()
        if g in ("lean", "diet"):
            return {"main": 0.45, "protein": 0.35, "side": 0.20}
        elif g == "bulk":
            return {"main": 0.50, "protein": 0.30, "side": 0.20}
        return {"main": 0.45, "protein": 0.30, "side": 0.25}

    def _adjust_serving_for_target(self, food, role_target_kcal):
        base_kcal = food.get("ps_energy_kcal", 0.0)
        if base_kcal <= 0:
            return food, 1.0
        if not bool(food.get("is_flexible", 0)):
            return food, 1.0

        base_serv = float(food.get("serving_size_g", 100.0))
        min_g = float(food.get("serving_min_g", 50.0))
        max_g = float(food.get("serving_max_g", 300.0))

        ratio_by_kcal = role_target_kcal / base_kcal if base_kcal > 0 else 1.0
        ratio_min = min_g / base_serv
        ratio_max = max_g / base_serv
        ratio = max(ratio_min, min(ratio_by_kcal, ratio_max))

        adj = {**food}
        for k in ["ps_energy_kcal", "ps_protein_g", "ps_fat_g", "ps_carb_g"]:
            adj[k] = food[k] * ratio
        adj["adjusted_serving_g"] = base_serv * ratio
        return adj, ratio

        # ========== 스코어링 ==========
    def _priority_score(self, food, goal, role, role_target_kcal, selected_names=None):
        """
        음식별 우선순위 점수 계산:
        - 건강도(Health Score)
        - 목표 매크로 적합도
        - 궁합 점수 (food_pair_scores.json 기반)
        - 사용자 선호 보너스 (self.user_pref_map)
        """
        quality = float(
        food.get("hybrid_health_score",
                 food.get("ml_health_score",
                          food.get("health_score", 60.0)))
        )
        quality = max(0.0, min(100.0, quality))

        kcal = food.get("ps_energy_kcal", 0.0)
        protein = food.get("ps_protein_g", 0.0)
        fat = food.get("ps_fat_g", 0.0)
        carb = food.get("ps_carb_g", 0.0)
        name = str(food.get("food_name", ""))

        # -----------------------------
        # ① 역할별 kcal 적합도 (±40%)
        # -----------------------------
        band = self.ROLE_KCAL_BAND
        low = role_target_kcal * (1 - band)
        high = role_target_kcal * (1 + band)
        if kcal < low:
            kcal_fit = 1.0 - (low - kcal) / max(low, 1.0)
        elif kcal > high:
            kcal_fit = 1.0 - (kcal - high) / max(high, 1.0)
        else:
            kcal_fit = 1.0
        kcal_fit = max(0.0, min(1.0, kcal_fit))

        # -----------------------------
        # ② 목표별 매크로 가중치
        # -----------------------------
        g = (goal or "").lower()
        if g in ("lean", "diet"):
            macro_term = protein * 2.0 - fat * 0.5 - carb * 0.15
            w_q, w_fit, w_macro = 0.55, 0.30, 0.15
        elif g == "bulk":
            macro_term = protein * 2.2 + carb * 0.7
            w_q, w_fit, w_macro = 0.50, 0.30, 0.20
        else:  # maintain
            macro_term = protein * 1.5 + carb * 0.4 - fat * 0.2
            w_q, w_fit, w_macro = 0.55, 0.25, 0.20

        # -----------------------------
        # ③ 가공식 / 보충제 페널티
        # -----------------------------
        penalty = 0.0
        if self._is_highly_processed(name):
            penalty -= 20.0
        if self._is_supplement(name) or self._is_drink_or_dessert(name):
            penalty -= 15.0

        # -----------------------------
        # ④ 궁합 점수 보너스 (pair_map)
        # -----------------------------
        pair_bonus = 0.0
        if selected_names:
            pairs = self.pair_map.get(name, [])
            if pairs:
                pair_dict = {n: s for n, s in pairs}
                for sel in selected_names:
                    if sel in pair_dict:
                        pair_bonus += pair_dict[sel] * 30.0  # 가중치 30
        else:
            pair_bonus = 0.0

        # -----------------------------
        # ⑤ 사용자 선호도 반영 (향후 feedback_router)
        # -----------------------------
        pref_bonus = 0.0
        if self.user_pref_map:
            pref = float(self.user_pref_map.get(name, 0.0))
            pref_bonus = (pref / 100.0) * 15.0  # 최대 15점 가산

        # -----------------------------
        # ⑥ 최종 종합 점수
        # -----------------------------
        base_score = (
            w_q * quality
            + w_fit * (kcal_fit * 100)
            + w_macro * macro_term
            + penalty
            + pair_bonus
            + pref_bonus
        )
        return base_score


    # ========== 후보 필터 ==========
    def _filter_candidates(self, foods, role, used_foods, daily_counters) -> List[Dict]:
        cands = []
        for f in foods:
            if f["_role"] != role:
                continue
            name = f["food_name"]
            if name in used_foods:
                continue
            # 메인에 간식/가공 금지
            if role in ("main", "protein"):
                if self._is_supplement(name) or self._is_drink_or_dessert(name) or self._is_highly_processed(name):
                    continue
            cands.append(f)
        return cands

    # ========== 다양성 검증 ==========
    def _update_daily_counters(self, meal_items: List[Dict], counters: Dict):
        bread_hit = any(self._is_match_any(i["food_name"], self.CARB_SOURCES["bread"]) for i in meal_items if i["_role"]=="main")
        noodle_hit = any(self._is_match_any(i["food_name"], self.CARB_SOURCES["noodle"]) for i in meal_items if i["_role"]=="main")
        processed_hits = sum(1 for i in meal_items if self._is_highly_processed(i["food_name"]))
        snack_hits = sum(1 for i in meal_items if (self._is_supplement(i["food_name"]) or self._is_drink_or_dessert(i["food_name"])))

        counters["bread_mains"] += 1 if bread_hit else 0
        counters["noodle_mains"] += 1 if noodle_hit else 0
        counters["processed"] += processed_hits
        counters["snack_drink"] += snack_hits

        # 탄수/단백질 소스 레지스터
        for it in meal_items:
            if it["_role"] == "main":
                counters["carb_sources"].add(it["_carb_source"])
            if it["_role"] == "protein":
                counters["prot_sources"].add(it["_protein_source"])

        # 핵심 키워드 중복 방지 (예: '고구마', '베이글' 등)
        for it in meal_items:
            base_kw = self._extract_core_keyword(it["food_name"])
            if base_kw:
                counters["core_seen"].add(base_kw)

    def _violates_diversity(self, meal_items: List[Dict], counters: Dict) -> bool:
        # 메인 제약
        if any(self._is_match_any(i["food_name"], self.CARB_SOURCES["bread"]) for i in meal_items if i["_role"]=="main"):
            if counters["bread_mains"] >= self.DAILY_BREAD_CAP:
                return True
        if any(self._is_match_any(i["food_name"], self.CARB_SOURCES["noodle"]) for i in meal_items if i["_role"]=="main"):
            if counters["noodle_mains"] >= self.DAILY_NOODLE_CAP:
                return True

        # 가공/간식 상한
        if sum(1 for i in meal_items if self._is_highly_processed(i["food_name"])) + counters["processed"] > self.DAILY_PROCESSED_CAP:
            return True
        if sum(1 for i in meal_items if (self._is_supplement(i["food_name"]) or self._is_drink_or_dessert(i["food_name"]))) + counters["snack_drink"] > self.DAILY_SNACK_DRINK_CAP:
            return True

        # 핵심 키워드 중복 회피
        for it in meal_items:
            kw = self._extract_core_keyword(it["food_name"])
            if kw and kw in counters["core_seen"]:
                return True

        return False

    def _extract_core_keyword(self, name: str) -> str:
        # 가장 강한 정체성 키워드 하나 추출
        buckets = sum(self.CARB_SOURCES.values(), []) + sum(self.PROTEIN_SOURCES.values(), [])
        for kw in buckets:
            if kw in name:
                return kw
        return ""

    # ========== 한 끼 구성 ==========
    def _pick_meal(self, foods, targets, used_foods, goal, daily_counters):
        role_split = self._role_kcal_split(goal)
        role_targets = {r: targets["kcal"] * role_split.get(r, 0.3) for r in ["main", "protein", "side"]}

        selected = []

        # 필수: main, protein
        for role in ["main", "protein"]:
            cands = self._filter_candidates(foods, role, used_foods, daily_counters)
            if not cands:
                return None
            cands.sort(key=lambda x: self._priority_score(x, goal, role, role_targets[role], selected_names=[f["food_name"] for f in selected]), reverse=True)
            # 다양성 고려하며 상위 몇 개에서 고르기
            top = cands[:10]
            pick = None
            for cand in top:
                tmp_item, _ = self._adjust_serving_for_target(cand, role_targets[role])
                if not self._violates_diversity([tmp_item], daily_counters):
                    pick = tmp_item
                    break
            if pick is None:
                pick, _ = self._adjust_serving_for_target(top[0], role_targets[role])  # 어쩔 수 없이 1등
            selected.append(pick)

        # 옵션: side
        cands_side = self._filter_candidates(foods, "side", used_foods, daily_counters)
        if cands_side:
            cands_side.sort(key=lambda x: self._priority_score(x, goal, "side", role_targets["side"]), reverse=True)
            top_s = cands_side[:10]
            side_pick = None
            for cand in top_s:
                tmp_item, _ = self._adjust_serving_for_target(cand, role_targets["side"])
                if not self._violates_diversity([tmp_item], daily_counters):
                    side_pick = tmp_item
                    break
            if side_pick:
                selected.append(side_pick)

        # 합계
        totals = {"kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0}
        for f in selected:
            totals["kcal"] += f.get("ps_energy_kcal", 0.0)
            totals["protein_g"] += f.get("ps_protein_g", 0.0)
            totals["fat_g"] += f.get("ps_fat_g", 0.0)
            totals["carb_g"] += f.get("ps_carb_g", 0.0)

        # kcal 15% 초과면 side 제거 시도
        if totals["kcal"] > targets["kcal"] * 1.15 and len(selected) >= 3:
            selected = selected[:2]
            totals = {"kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0}
            for f in selected:
                totals["kcal"] += f.get("ps_energy_kcal", 0.0)
                totals["protein_g"] += f.get("ps_protein_g", 0.0)
                totals["fat_g"] += f.get("ps_fat_g", 0.0)
                totals["carb_g"] += f.get("ps_carb_g", 0.0)

        # 단백질 과다 방지
        cap = self.PROTEIN_CAP_PER_MEAL.get((goal or "lean").lower(), 60.0)
        if totals["protein_g"] > cap and len(selected) >= 3:
            selected.sort(key=lambda x: x.get("ps_protein_g", 0) / max(1.0, x.get("ps_energy_kcal", 1.0)), reverse=True)
            selected.pop(0)
            totals = {"kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0}
            for f in selected:
                totals["kcal"] += f.get("ps_energy_kcal", 0.0)
                totals["protein_g"] += f.get("ps_protein_g", 0.0)
                totals["fat_g"] += f.get("ps_fat_g", 0.0)
                totals["carb_g"] += f.get("ps_carb_g", 0.0)

        # 최종 오차 기준
        kcal_diff = abs(totals["kcal"] - targets["kcal"]) / max(1.0, targets["kcal"])
        prot_diff = abs(totals["protein_g"] - targets["protein_g"]) / max(1.0, targets["protein_g"])
        if kcal_diff < 0.15 and prot_diff < 0.30 and len(selected) >= 2:
            optimized, totals_adj = optimize_meal_macros(selected, targets, tol_ratio=self.TOL_RATIO)
            for it in selected:
                used_foods.add(it["food_name"])
            # 다양성 카운터 업데이트
            self._update_daily_counters(selected, daily_counters)
            return {
                "targets": targets,
                "actuals": totals_adj,
                "items": [{**item, "multiplier": mult} for item, mult in optimized]
            }

        # fallback: 현실식 템플릿
        if self.FORCE_TEMPLATE:
            template = random.choice(self.REALISTIC_TEMPLATES)
            fallback_items = [f for f in foods if any(tag in f["food_name"] for tag in template)][:3]
            if fallback_items:
                optimized, totals = optimize_meal_macros(fallback_items, targets, tol_ratio=self.TOL_RATIO)
                self._update_daily_counters(fallback_items, daily_counters)
                for it in fallback_items:
                    used_foods.add(it["food_name"])
                return {
                    "targets": targets,
                    "actuals": totals,
                    "items": [{**i, "multiplier": m} for i, m in optimized],
                    "fallback": True
                }
        return None

    # ========== 하루/주간 ==========
    def plan_day(self, user, meals_per_day, calc_fn):
        goal_cal, p, f, c = calc_fn(user)
        targets = {"kcal": goal_cal, "protein_g": p, "fat_g": f, "carb_g": c}
        per_meal = {k: targets[k] / meals_per_day for k in targets}

        foods = self._get_food_pool()
        used_foods = set()
        daily_counters = {
            "bread_mains": 0,
            "noodle_mains": 0,
            "processed": 0,
            "snack_drink": 0,
            "carb_sources": set(),
            "prot_sources": set(),
            "core_seen": set()
        }

        meals = []
        for i in range(meals_per_day):
            for _ in range(self.RETRY_LIMIT):
                meal = self._pick_meal(foods, per_meal, used_foods, user.goal, daily_counters)
                if meal:
                    meal["meal_number"] = i + 1
                    meals.append(meal)
                    break
            else:
                # 현실식 기반 fallback
                realistic = [f for f in foods if self._is_meal_candidate(f["food_name"]) and f["_role"] in ("main","protein","side")]
                realistic.sort(key=lambda x: x.get("ml_health_score", x.get("health_score", 60)), reverse=True)
                sample = random.sample(realistic[:60], min(3, len(realistic[:60])))
                optimized, totals = optimize_meal_macros(sample, per_meal, tol_ratio=self.TOL_RATIO)
                meals.append({
                    "targets": per_meal,
                    "actuals": totals,
                    "items": [{**i2, "multiplier": m} for i2, m in optimized],
                    "fallback": True,
                    "meal_number": i + 1
                })
                self._update_daily_counters([i2 for i2, _ in optimized], daily_counters)

        # 다양성 최종 검사: 탄수/단백질 소스 최소치
        # (부족하면 다음날 로테이션이 더 강하게 걸리도록 이 버전은 soft하게 통과)
        daily_actual = {k: sum(m["actuals"][k] for m in meals) for k in targets}
        return {"target_daily": targets, "actual_daily": daily_actual, "meals": meals}

    def plan_week(self, user, meals_per_day, calc_fn, days=7):
        week = []
        totals = {"kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0}
        for d in range(days):
            day = self.plan_day(user, meals_per_day, calc_fn)
            week.append({"day": d + 1, "daily_plan": day})
            for k in totals:
                totals[k] += day["actual_daily"][k]
        avg = {k: totals[k] / days for k in totals}
        return {"weekly_average": avg, "weekly_plan": week}

    # ========== DB 로드 ==========
    def _get_food_pool(self) -> List[Dict]:
        excel_path = os.path.join("src", "data", "extended_food_db_scored.xlsx")
        if not os.path.exists(excel_path):
            excel_path = os.path.join("src", "data", "extended_food_db.xlsx")

        df = pd.read_excel(excel_path)
        df = df.fillna({
            "energy_kcal": 0, "protein_g": 0, "fat_g": 0, "carb_g": 0,
            "serving_size_g": 100, "is_flexible": 0, "serving_min_g": 50, "serving_max_g": 300,
            "ml_health_score": 60, "health_score": 60
        })

        pool = []
        for _, r in df.iterrows():
            name = str(r["food_name"])
            if not self._is_meal_candidate(name):
                # 식사로 부적합한 품목은 전체에서 제외
                continue

            serving = float(max(30.0, min(400.0, r["serving_size_g"])))
            mult = serving / 100.0

            item = {
                "food_name": name,
                "serving_size_g": serving,
                "ps_energy_kcal": float(r["energy_kcal"]) * mult,
                "ps_protein_g": float(r["protein_g"]) * mult,
                "ps_fat_g": float(r["fat_g"]) * mult,
                "ps_carb_g": float(r["carb_g"]) * mult,
                "ml_health_score": float(r.get("ml_health_score", 60.0)),
                "health_score": float(r.get("health_score", 60.0)),
                "is_flexible": int(r.get("is_flexible", 0)),
                "serving_min_g": float(r.get("serving_min_g", 50.0)),
                "serving_max_g": float(r.get("serving_max_g", 300.0)),
            }
            role = self._classify_food_role(name)
            item["_role"] = role
            item["_carb_source"] = self._carb_source_tag(name) if role == "main" else "none"
            item["_protein_source"] = self._protein_source_tag(name) if role == "protein" else "none"
            pool.append(item)

        return pool

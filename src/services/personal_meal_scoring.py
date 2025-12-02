# src/services/personal_meal_scoring.py

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple
from collections import Counter

from sqlalchemy.orm import Session

from src import db


# =====================================================
# 1) 유저 컨텍스트 구조체
# =====================================================

@dataclass
class UserMealContext:
    user: db.User
    profile: Optional[db.UserProfile]
    preferences: Dict[str, float]          # food_name -> score
    exclusions: set[str]                   # 제외 음식 이름들
    recent_food_counts: Dict[str, int]     # 최근 N일 동안 먹은 횟수
    recent_days: int                       # 얼마나 과거까지 봤는지
    tdee_kcal: Optional[float] = None      # 나중에 필요하면 넣기 (지금은 None 가능)


# =====================================================
# 2) 유틸 - 유저 컨텍스트 로딩
# =====================================================

def load_user_meal_context(
    session: Session,
    user_id: str,
    recent_days: int = 7,
) -> UserMealContext:
    """
    유저 기본정보, 프로필, 선호/제외 음식, 최근 식단 히스토리를 한 번에 읽어서
    추천 엔진이 쓰기 좋은 형태로 정리한다.
    """

    user = session.query(db.User).filter_by(id=user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    # 1) 프로필 (diet_style, cuisine_preference, allergies 등)
    profile = session.query(db.UserProfile).filter_by(user_id=user_id).first()

    # 2) 선호 음식
    prefs_rows = (
        session.query(db.UserFoodPreference)
        .filter_by(user_id=user_id)
        .all()
    )
    preferences: Dict[str, float] = {
        row.food_name: row.score for row in prefs_rows
    }

    # 3) 제외 음식
    exclusions_rows = (
        session.query(db.UserFoodExclusion)
        .filter_by(user_id=user_id)
        .all()
    )
    exclusions: set[str] = {row.food_name for row in exclusions_rows}

    # 4) 최근 N일 식단 로그 → food_name 카운트
    since = date.today() - timedelta(days=recent_days)
    history_rows = (
        session.query(db.UserMealHistory)
        .filter(db.UserMealHistory.user_id == user_id)
        .filter(db.UserMealHistory.date >= since)
        .all()
    )

    recent_food_counts: Dict[str, int] = {}

    for h in history_rows:
        for item in h.items:
            name = item.food_name
            if not name:
                continue
            recent_food_counts[name] = recent_food_counts.get(name, 0) + 1

    ctx = UserMealContext(
        user=user,
        profile=profile,
        preferences=preferences,
        exclusions=exclusions,
        recent_food_counts=recent_food_counts,
        recent_days=recent_days,
        tdee_kcal=None,  # TODO: 나중에 nutrition.calculate_macros와 연결 가능
    )
    return ctx


# =====================================================
# 3) 음식 점수 계산 로직
# =====================================================

def _preference_bonus(food_name: str, ctx: UserMealContext) -> float:
    """
    선호 음식 점수: 많이 좋아할수록 가중치 플러스.
    """
    score = ctx.preferences.get(food_name, 0.0)
    if score <= 0:
        return 0.0
    # 예시: log 스케일로 완만하게 증가
    return min(10.0, 2.0 * score ** 0.5)


def _novelty_bonus(food_name: str, ctx: UserMealContext) -> float:
    """
    최근에 자주 먹지 않은 음식일수록 점수 플러스.
    너무 자주 먹은 음식은 약간 페널티.
    """
    cnt = ctx.recent_food_counts.get(food_name, 0)
    if cnt == 0:
        return 5.0   # 최근 안 먹었으면 +5
    elif cnt == 1:
        return 2.0
    elif cnt == 2:
        return 0.0
    else:
        return -3.0  # 너무 자주 먹은 건 약간 페널티


def _diet_style_weight(food: db.Food, ctx: UserMealContext) -> float:
    """
    diet_style에 따라 기본 영양 성분을 보고 보너스/페널티를 준다.
    - tight: 고단백/저칼로리/저지방 선호
    - normal: 균형
    - bulk: 칼로리/단백 허용 범위 확대
    """
    if not ctx.profile:
        return 0.0

    style = (ctx.profile.diet_style or "normal").lower()

    # g/100g 기준 대충 감 정도로 조정
    kcal = food.calories
    protein = food.protein
    fat = food.fat
    processing = food.processing_level or 1

    bonus = 0.0

    if style == "tight":
        # 가벼운 음식(저칼로리) + 단백질 높은 것
        if kcal <= 120 and protein >= 15:
            bonus += 5.0
        if fat >= 15:
            bonus -= 3.0
    elif style == "bulk":
        # 칼로리는 어느 정도 허용, 단백질 위주
        if protein >= 20:
            bonus += 3.0
        # 가공도 너무 높으면 조금 페널티
        if processing >= 3:
            bonus -= 2.0
    else:
        # normal: 너무 극단적인 것만 조정
        if processing >= 4:
            bonus -= 2.0

    return bonus


def _cuisine_match_bonus(food: db.Food, ctx: UserMealContext) -> float:
    """
    cuisine_preference와 음식 이름/회사로 추정해서 보너스 주기.
    (임시 버전 — 나중에 카테고리 컬럼 있으면 거기로 교체)
    """
    if not ctx.profile:
        return 0.0

    pref = (ctx.profile.cuisine_preference or "mixed").lower()
    name = (food.name or "").lower()
    company = (food.company or "").lower()

    # 아주 대충 “한식스러운 이름” / “외국 브랜드” 구분 예시
    is_korean_style = any(ch >= "가" and ch <= "힣" for ch in food.name)
    is_western_brand = any(
        kw in company
        for kw in ["kellogg", "nestle", "cheerios", "cereal", "pizza", "pasta"]
    )

    if pref == "mixed":
        return 0.0

    if pref == "korean":
        if is_korean_style:
            return 2.0
        if is_western_brand:
            return -1.0

    if pref == "western":
        if is_western_brand:
            return 2.0
        if is_korean_style:
            return -1.0

    return 0.0


def _processing_penalty(food: db.Food) -> float:
    """
    가공도에 따른 기본 페널티.
    processing_level: 1 = 최소, 숫자 클수록 가공 음식
    """
    level = food.processing_level or 1
    if level <= 1:
        return 0.0
    elif level == 2:
        return -1.0
    elif level == 3:
        return -3.0
    else:
        return -5.0


def score_food_for_user(food: db.Food, ctx: UserMealContext) -> float:
    """
    하나의 Food row에 대해 최종 점수 계산.
    이 점수로 정렬해서 상위 N개 후보를 뽑게 될 것.
    """

    # 0) 제외 음식이면 아주 낮은 점수 리턴
    if food.name in ctx.exclusions:
        return -9999.0

    # 1) 베이스 점수: 일단 단순하게 "hybrid-like" 점수 구성
    # (나중에 extended_food_db에서 hybrid_health_score 읽어 올 수 있으면 그걸 쓰면 됨)
    base = 0.0

    # 단백질당 보너스, 지방/당류/나트륨에 약간 페널티
    base += food.protein * 0.8
    base -= food.fat * 0.2
    base -= food.sugar * 0.1
    base -= (food.sodium / 1000.0) * 0.5  # 1000mg당 -0.5점 정도

    # 2) 선호도 점수
    pref = _preference_bonus(food.name, ctx)

    # 3) novelty (최근에 많이 안 먹은 것)
    nov = _novelty_bonus(food.name, ctx)

    # 4) diet_style에 따른 조정
    diet_adj = _diet_style_weight(food, ctx)

    # 5) cuisine_preference 매칭
    cuisine_adj = _cuisine_match_bonus(food, ctx)

    # 6) 가공도 페널티
    proc_pen = _processing_penalty(food)

    final = base + pref + nov + diet_adj + cuisine_adj + proc_pen
    return final


# =====================================================
# 4) 유저별 음식 후보 상위 N개 가져오기
# =====================================================

def get_ranked_food_candidates(
    session: Session,
    user_id: str,
    limit: int = 50,
    recent_days: int = 7,
) -> List[Tuple[db.Food, float]]:
    """
    - 전체 Food 테이블에서 기본적으로 '건강한' 후보를 어느 정도 필터링하고
    - 유저 컨텍스트 기반으로 점수를 계산해
    - 점수 순으로 상위 limit개를 반환한다.
    """

    # recent_days 기준으로 컨텍스트 로딩 (이 안에 recent_food_counts 포함)
    ctx = load_user_meal_context(session, user_id, recent_days=recent_days)

    # 1) 일단 음식 전체를 가져오되, 너무 극단적인 값은 필터링 (여기선 전체)
    foods: List[db.Food] = session.query(db.Food).all()

    # 2) 각 음식 점수 계산 + 반복 페널티 적용
    scored: List[Tuple[db.Food, float]] = []

    # 최근 음식 등장 횟수 (이름 기준)
    recent_freq = ctx.recent_food_counts  # { food_name: count }
    penalty_weight = 0.5                  # 반복 1회당 감점 수치

    for f in foods:
        base_score = score_food_for_user(f, ctx)  # 선호도/novelty/diet_style 등 반영된 기본 점수

        freq = recent_freq.get(f.name, 0)
        penalty = freq * penalty_weight

        final_score = base_score - penalty

        scored.append((f, final_score))

    # 3) 점수 순 정렬 (내림차순)
    scored.sort(key=lambda x: x[1], reverse=True)

    # 4) 상위 limit개만 반환
    return scored[:limit]



def get_recent_food_frequency(user_id: str, session: Session, days: int = 3):
    """
    최근 n일 동안 등장한 음식들의 등장 횟수를 반환.
    { '닭가슴살': 7, '현미밥': 7, '브로콜리': 5 }
    """
    cutoff = date.today() - timedelta(days=days)
    
    histories = (
        session.query(db.UserMealHistory)
        .filter(db.UserMealHistory.user_id == user_id)
        .filter(db.UserMealHistory.date >= cutoff)
        .all()
    )

    counter = Counter()

    for h in histories:
        for item in h.items:
            if item.food_name:
                counter[item.food_name] += 1

    return counter

def apply_food_diversity_penalty(score_map: dict, freq_map: dict, penalty_weight: float = 0.5):
    """
    freq_map = 음식 등장 횟수
    score_map = 기존 점수 dict { food_name: score }
    penalty_weight = 반복 1회당 감점 수치
    """
    for food_name, freq in freq_map.items():
        if food_name in score_map:
            penalty = freq * penalty_weight
            score_map[food_name] -= penalty
    return score_map

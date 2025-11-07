# src/utils/load_rules.py
from __future__ import annotations

# 간단한 휴리스틱: 장비/부위/카테고리 기준 시작무게 스케일(kg)과 보정
BASE_START_KG = {
    "barbell": 20.0,    # 빈바 기준
    "dumbbell": 6.0,    # 덤벨 한 손 기준
    "machine": 10.0,
    "cable": 5.0,
    "band": 0.0,
    "bodyweight": 0.0,
    "ez bar": 12.0,
    "smith": 15.0,
}

# 부위별 추가 가중치 (초기 가이드)
MUSCLE_ADJ = {
    "가슴": 1.2, "광배": 1.1, "등": 1.1, "삼각": 0.9, "이두": 0.7, "삼두": 0.8,
    "대퇴사두": 1.3, "햄스트링": 1.1, "둔근": 1.2, "종아리": 0.8, "복근": 0.3, "전완": 0.5,
}

# 숙련도 보정
EXP_MULT = {
    "beginner": 0.8,
    "intermediate": 1.0,
    "advanced": 1.15,
}

# 목표별 템포/리프 여유(RIR) 기본값
GOAL_TEMPO = {
    "hypertrophy": "2-0-2",
    "strength":    "2-1-1",
    "fat_loss":    "2-0-2",
    "functional":  "2-0-2",
}

GOAL_RIR = {
    "hypertrophy": (1, 3),
    "strength":    (1, 2),
    "fat_loss":    (2, 4),
    "functional":  (2, 4),
}

def _norm(text: str) -> str:
    return (text or "").strip().lower()

def _equip_key(equip_text: str) -> str:
    e = _norm(equip_text)
    # 대표 키워드 매핑
    if "barbell" in e or "바벨" in e: return "barbell"
    if "dumbbell" in e or "덤벨" in e: return "dumbbell"
    if "machine" in e or "머신" in e or "레버" in e or "스미스" in e: return "machine" if "스미스" not in e else "smith"
    if "cable" in e or "케이블" in e: return "cable"
    if "밴드" in e or "band" in e: return "band"
    if "맨몸" in e or "bodyweight" in e: return "bodyweight"
    if "ez" in e: return "ez bar"
    return "machine"  # 모르면 보수적으로

def _muscle_key(target_text: str) -> str:
    t = _norm(target_text)
    # 한국어 주요 타깃 키워드 일부
    if "가슴" in t: return "가슴"
    if "광배" in t or "등" in t: return "광배"
    if "삼각" in t: return "삼각"
    if "이두" in t: return "이두"
    if "삼두" in t: return "삼두"
    if "대퇴사두" in t or "사두" in t or "쿼드" in t: return "대퇴사두"
    if "햄" in t: return "햄스트링"
    if "둔" in t or "힙" in t or "엉덩" in t: return "둔근"
    if "종아" in t: return "종아리"
    if "복근" in t or "코어" in t or "복직" in t: return "복근"
    if "전완" in t: return "전완"
    return "가슴"  # 모르면 중간값 대체

def suggest_start_load(
    exercise: dict,
    user_weight_kg: float | None,
    experience: str,
    goal: str,
) -> float:
    """
    시작 무게(kg) 제안. 맨몸/밴드/유산소성/코어성은 0 반환.
    장비 & 타깃부위 & 숙련도 보정 + 체중의 약한 가중.
    """
    equip_key = _equip_key(exercise.get("equipments") or exercise.get("equip") or "")
    target_key = _muscle_key(exercise.get("targetMuscles") or exercise.get("target") or "")

    # 맨몸/밴드/코어성은 무게 0
    if equip_key in ("bodyweight", "band"):
        return 0.0
    if target_key in ("복근", "전완"):
        # 코어/전완은 수행 품질 중심 -> 최소 가중치
        base = 0.0
    else:
        base = BASE_START_KG.get(equip_key, 6.0)

    # 부위 가중
    base *= MUSCLE_ADJ.get(target_key, 1.0)

    # 숙련도
    base *= EXP_MULT.get((experience or "beginner").lower(), 0.8)

    # 체중 약한 영향(너무 과도하지 않게 0~+20%)
    if user_weight_kg and user_weight_kg > 0:
        base *= min(1.2, 0.8 + (user_weight_kg / 100.0))  # 50kg→1.3(상한1.2로 클램프)

    # 안전 하한/상한
    if equip_key in ("barbell", "smith", "ez bar"):
        base = max(15.0, min(base, 50.0))
    elif equip_key == "dumbbell":
        base = max(4.0, min(base, 30.0))
    else:  # machine/cable
        base = max(5.0, min(base, 40.0))

    # 맨몸/밴드는 0 보장
    if equip_key in ("bodyweight", "band"):
        base = 0.0

    # 소수점 한 자리 반올림
    return round(base, 1)

def suggest_tempo(goal: str) -> str:
    return GOAL_TEMPO.get((goal or "").lower(), "2-0-2")

def suggest_rir(goal: str, experience: str) -> int:
    lo, hi = GOAL_RIR.get((goal or "").lower(), (2, 3))
    # 초보는 여유를 더 남김
    if (experience or "beginner").lower() == "beginner":
        hi = min(5, hi + 1)
    return hi  # 상단값 쪽을 가이드로

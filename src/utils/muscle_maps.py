# src/utils/muscle_maps.py
# ----------------------------------------
# 부위 매핑 / 분할 / 목표 파라미터
# ----------------------------------------

MUSCLE_KEYWORDS = {
    "arms": ["팔", "이두", "삼두"],
    "chest": ["가슴", "흉근"],
    "back": ["등", "광배", "승모"],
    "shoulders": ["어깨", "삼각근"],
    "legs": ["하체", "대퇴", "햄스트링", "종아리", "대퇴사두근","허벅지"],
    "glutes": ["둔부", "엉덩이", "둔근"],
    "core": ["복근", "코어", "복사근", "복직근", "기립근"],
}

MUSCLE_KEYWORDS.update({
    "quads": ["대퇴사두근", "앞벅지", "사두"],
    "hamstrings": ["햄스트링", "뒤벅지"],
    "glutes": ["둔근", "중둔근", "소둔근", "엉덩이"],
    "calves": ["비복근", "가자미근", "종아리"],
    # 기존 legs, core 등은 이미 있음
})

# 목표별 세트/반복/휴식 파라미터
GOAL_PARAMS = {
    "fat_loss":     {"reps": (12,20), "sets": (3,4), "rest_sec": (45,75), "intensity": "moderate"},
    "hypertrophy":  {"reps": (8,12),  "sets": (3,5), "rest_sec": (60,120), "intensity": "moderate-high"},
    "strength":     {"reps": (3,6),   "sets": (4,6), "rest_sec": (120,240), "intensity": "high"},
    "functional":   {"reps": (10,15), "sets": (2,4), "rest_sec": (45,90), "intensity": "low-moderate"},
}

# 숙련도별 주간 분할
SPLIT_TEMPLATES = {
    "beginner":    ["Upper","Lower","Rest","Upper","Lower","Rest","Rest"],
    "intermediate":["Push","Pull","Legs","Rest","Push","Pull","Legs"],
    "advanced":    ["Upper","Lower","Push","Pull","Legs","Upper","Lower"],
}

FOCUS_TO_GROUPS = {
    "Upper": ["chest","back","shoulders","arms","core"],
    "Lower": ["legs","glutes","core"],
    "Push":  ["chest","shoulders","arms"],
    "Pull":  ["back","arms"],
    "Legs":  ["legs","glutes","core"],
    "Core":  ["core"],
}

DEFAULT_HOME_EQUIPS = ["매트","덤벨","밴드","철봉","케틀벨"]

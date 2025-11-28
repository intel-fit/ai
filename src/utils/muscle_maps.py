# ----------------------------------------
# 부위 매핑 / 분할 / 목표 파라미터
# ----------------------------------------

MUSCLE_KEYWORDS = {
    # 상체
    "chest": ["가슴", "흉근", "대흉근", "소흉근"],
    "back": ["등", "광배", "승모", "기립근"],
    "shoulders": ["어깨", "삼각근", "전면삼각근", "측면삼각근", "후면삼각근"],

    # 팔
    "biceps": ["이두", "이두근", "상완이두근", "biceps"],
    "triceps": ["삼두", "삼두근", "상완삼두근", "triceps"],
    "forearms": ["전완", "전완근", "팔뚝", "forearm"],

    # 복부/코어
    "core": ["복근", "복직근", "복사근", "코어", "기립근"],

    # 하체
    "legs": ["하체", "허벅지", "대퇴", "종아리", "햄스트링", "사두"],
    "quads": ["대퇴사두근", "앞벅지", "사두"],
    "hamstrings": ["햄스트링", "뒤벅지"],
    "glutes": ["둔근", "엉덩이", "중둔근", "소둔근"],
    "calves": ["비복근", "가자미근", "종아리"],

    # 전신/기능성
    "fullbody": ["전신", "전신운동", "풀바디"],

    # 유산소
    "cardio": ["유산소", "러닝", "걷기", "사이클", "조깅", "스텝퍼"],
    
    # 스트레칭 & 모빌리티
    "stretch": ["스트레칭", "신장", "유연성", "모빌리티", "가동성"],
}

# 목표별 세트/반복/휴식 파라미터 (유산소 제외)
GOAL_PARAMS = {
    "fat_loss":     {"reps": (12,20), "sets": (3,4), "rest_sec": (45,75), "intensity": "moderate"},
    "hypertrophy":  {"reps": (8,12),  "sets": (3,5), "rest_sec": (60,120), "intensity": "moderate-high"},
    "strength":     {"reps": (3,6),   "sets": (4,6), "rest_sec": (120,240), "intensity": "high"},
    "functional":   {"reps": (10,15), "sets": (2,4), "rest_sec": (45,90), "intensity": "low-moderate"},
}

# 분할 매핑
SPLIT_TEMPLATES = {
    "beginner":    ["Upper","Lower","Rest","Upper","Lower","Rest","Rest"],
    "intermediate":["Push","Pull","Legs","Rest","Push","Pull","Legs"],
    "advanced":    ["Upper","Lower","Push","Pull","Legs","Upper","Lower"],
}

# Focus → 그룹
FOCUS_TO_GROUPS = {
    "Upper": ["chest","back","shoulders","arms","core"],
    "Lower": ["legs","glutes","core"],
    "Push":  ["chest","shoulders","triceps"],
    "Pull":  ["back","biceps"],
    "Legs":  ["legs","glutes","core"],
    "Core":  ["core"],
    "Arms":  ["biceps", "triceps", "forearms"],
    "Cardio": ["cardio", "fullbody"],
    "Stretch": ["stretch"],
}

# 홈트 환경 장비
DEFAULT_HOME_EQUIPS = ["매트","덤벨","밴드","철봉","케틀벨"]

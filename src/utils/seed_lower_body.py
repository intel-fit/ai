# src/utils/seed_lower_body.py
import os, sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "exercise.db")

SEED = [
    # exerciseId, name, targetMuscles, bodyParts, equipments, secondaryMuscles, instructions
    ("seed_back_squat", "바벨 백 스쿼트", "대퇴사두근|둔근|햄스트링", "하체", "바벨", "코어",
     "발 어깨너비, 가슴 펴고 바벨을 승모 위에; 고관절-무릎 동시에 굴곡; 깊이 유지 후 폭발적으로 일어선다."),
    ("seed_front_squat", "바벨 프론트 스쿼트", "대퇴사두근|둔근", "하체", "바벨", "코어",
     "바벨을 쇄골 앞에; 팔꿈치 높게; 무릎 전방 이동 허용; 중량은 보수적으로."),
    ("seed_oh_squat", "오버헤드 스쿼트", "대퇴사두근|둔근|코어|광배", "하체", "바벨", "어깨",
     "바벨을 머리 위 락아웃; 발은 스쿼트 스탠스; 코어·견갑 안정 유지."),
    ("seed_rdl", "바벨 루마니안 데드리프트", "햄스트링|둔근|척추기립근", "하체", "바벨", "코어",
     "무릎 살짝 굽힌 채 엉덩이 뒤로 빼며 힌지; 햄스트링 텐션 유지; 허리 말림 금지."),
    ("seed_hip_thrust", "힙 쓰러스트", "둔근|햄스트링", "하체", "바벨", "코어",
     "등판을 벤치에; 바벨은 골반 위; 최상단에서 둔근 수축 1-2초."),
    ("seed_bulgarian", "불가리안 스플릿 스쿼트", "대퇴사두근|둔근|햄스트링", "하체", "덤벨", "코어",
     "후족을 벤치에; 전족 무릎-발끝 정렬; 상체 약간 전경사."),
    ("seed_leg_press", "레그 프레스", "대퇴사두근|둔근|햄스트링", "하체", "머신", "코어",
     "발 스탠스 중간; 무릎 안쪽 붕괴 방지; 가동범위 확보."),
    ("seed_leg_ext", "레그 익스텐션", "대퇴사두근", "하체", "머신", "없음",
     "무릎 축 정렬; 최상단에서 1초 정지."),
    ("seed_leg_curl", "레그 컬", "햄스트링", "하체", "머신", "종아리",
     "엉덩이 뜨지 않게; 햄스트링 수축감 위주."),
    ("seed_calf_raise", "서서 카프 레이즈", "비복근|가자미근", "하체", "머신", "없음",
     "최하단 스트레치, 최상단 수축 1초."),
    ("seed_goblet_squat", "고블릿 스쿼트", "대퇴사두근|둔근|코어", "하체", "덤벨", "허리",
     "덤벨을 가슴 앞; 가슴 펴고 힙·무릎 동시 굴곡."),
    ("seed_db_dl", "덤벨 루마니안 데드리프트", "햄스트링|둔근", "하체", "덤벨", "코어",
     "덤벨 허벅지 따라 이동, 힌지 집중."),
    ("seed_stepup", "스텝업", "둔근|대퇴사두근", "하체", "덤벨", "햄스트링",
     "발 전부 올리고 뒤꿈치로 밀어 일어서기."),
    ("seed_split_squat", "스플릿 스쿼트", "대퇴사두근|둔근|햄스트링", "하체", "바벨", "코어",
     "전후 스탠스; 상체 약간 전경사."),
    ("seed_sldl", "싱글 레그 RDL", "햄스트링|둔근|코어", "하체", "덤벨", "척추기립근",
     "지지발 무릎 약간 굴곡; 힌지 시 골반 수평."),
    ("seed_cable_pull", "케이블 풀쓰루", "둔근|햄스트링", "하체", "케이블", "코어",
     "엉덩이 후방 스윙; 둔근 수축."),
    ("seed_abductor", "힙 어브덕션", "중둔근", "하체", "머신", "둔근",
     "무릎 라인 유지; 반동 금지."),
    ("seed_adductor", "힙 애덕션", "내전근", "하체", "머신", "둔근",
     "가동범위 확보; 통증 범위 회피."),
    ("seed_box_squat", "박스 스쿼트", "대퇴사두근|둔근|햄스트링", "하체", "바벨", "코어",
     "깊이 일정; 힙 백, 컨트롤."),
    ("seed_rw_lunge", "리어 워킹 런지", "둔근|대퇴사두근|햄스트링", "하체", "바벨", "코어",
     "긴 보폭; 앞발 뒤꿈치로 밀기.")
]

def main():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"DB not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS exerciseCategory (
        exerciseId TEXT PRIMARY KEY,
        name TEXT,
        gifUrl TEXT,
        targetMuscles TEXT,
        bodyParts TEXT,
        equipments TEXT,
        secondaryMuscles TEXT,
        instructions TEXT
    )
    """)

    inserted = 0
    for row in SEED:
        cur.execute("SELECT 1 FROM exerciseCategory WHERE exerciseId=?", (row[0],))
        if cur.fetchone():
            continue
        cur.execute("""
        INSERT INTO exerciseCategory (
            exerciseId, name, gifUrl, targetMuscles, bodyParts, equipments, secondaryMuscles, instructions
        ) VALUES (?, ?, '', ?, ?, ?, ?, ?)
        """, row)
        inserted += 1

    conn.commit()
    conn.close()
    print(f"✅ Seeded lower-body: inserted={inserted}, total={len(SEED)}")

if __name__ == "__main__":
    main()

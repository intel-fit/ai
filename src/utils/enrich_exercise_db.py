# ==========================================
# src/utils/enrich_exercise_db.py
# ==========================================
import sqlite3, os, pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "exercise.db")
OUT_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "exercise_enriched.csv")

# ---------- 규칙 기반 태그 추론 ----------
def infer_difficulty(name, equip, target):
    text = f"{name} {equip} {target}".lower()
    if any(x in text for x in ["smith", "machine", "cable", "band", "seated", "bodyweight", "맨몸", "밴드", "케이블"]):
        return "beginner"
    elif any(x in text for x in ["barbell", "dumbbell", "press", "squat", "deadlift", "벤치", "바벨", "덤벨", "스쿼트"]):
        return "intermediate"
    elif any(x in text for x in ["snatch", "clean", "jerk", "hang", "power", "케틀벨", "올림픽"]):
        return "advanced"
    return "intermediate"


def infer_risk(name, equip, target):
    text = f"{name} {equip} {target}".lower()
    risk = 0.3
    if any(x in text for x in ["barbell", "deadlift", "clean", "snatch", "jerk", "press", "squat", "벤치", "스쿼트"]):
        risk += 0.4
    if any(x in text for x in ["machine", "band", "seated", "케이블", "밴드"]):
        risk -= 0.2
    return round(max(0.1, min(1.0, risk)), 2)


def infer_category(name, equip, target):
    text = f"{name} {equip} {target}".lower()
    if any(x in text for x in ["plank", "bridge", "balance", "twist", "raise", "복부", "코어", "플랭크", "브리지"]):
        return "functional"
    elif any(x in text for x in ["machine", "cable", "band", "curl", "extension", "fly", "케이블", "밴드"]):
        return "isolation"
    else:
        return "compound"


def infer_effectiveness(target):
    if not target:
        return 0.7
    t = target.lower()
    if any(x in t for x in ["legs", "하체", "둔근", "core", "복부", "코어", "대퇴", "햄스트링"]):
        return 0.9
    if any(x in t for x in ["arms", "biceps", "triceps", "팔", "이두", "삼두"]):
        return 0.8
    if any(x in t for x in ["back", "등", "shoulder", "어깨", "chest", "가슴"]):
        return 0.85
    return 0.7


# ---------- DB 연결 및 갱신 ----------
def enrich_exercise_db():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"❌ DB not found: {DB_PATH}")
    
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM exerciseCategory", conn)

    print(f"📊 Loaded {len(df)} exercises")

    # 새 컬럼 추가
    df["difficulty"] = df.apply(lambda x: infer_difficulty(x["name"], x["equipments"], x["targetMuscles"]), axis=1)
    df["risk_score"] = df.apply(lambda x: infer_risk(x["name"], x["equipments"], x["targetMuscles"]), axis=1)
    df["category"] = df.apply(lambda x: infer_category(x["name"], x["equipments"], x["targetMuscles"]), axis=1)
    df["effectiveness"] = df.apply(lambda x: infer_effectiveness(x["targetMuscles"]), axis=1)


    # CSV 저장
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"✅ Saved enriched CSV: {OUT_CSV}")

    # DB 업데이트
    cur = conn.cursor()
    for col, dtype in [
        ("difficulty", "TEXT"),
        ("risk_score", "REAL"),
        ("category", "TEXT"),
        ("effectiveness", "REAL")
    ]:
        try:
            cur.execute(f"ALTER TABLE exerciseCategory ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError:
            pass  # 이미 존재하면 무시

    for _, row in df.iterrows():
        cur.execute("""
            UPDATE exerciseCategory
            SET difficulty=?, risk_score=?, category=?, effectiveness=?
            WHERE exerciseId=?
        """, (row["difficulty"], row["risk_score"], row["category"], row["effectiveness"], row["exerciseId"]))

    conn.commit()
    conn.close()
    print("💾 Database updated successfully.")

if __name__ == "__main__":
    enrich_exercise_db()

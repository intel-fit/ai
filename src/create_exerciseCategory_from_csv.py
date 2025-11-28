import sqlite3
import pandas as pd
import os

DB_PATH = "src/data/food_db.sqlite"
CSV_PATH = "src/data/exercise_enriched.csv"

# DB 파일 존재 확인
if not os.path.exists(DB_PATH):
    print("[ERROR] food_db.sqlite 파일이 없습니다.")
    exit()

# CSV 확인
if not os.path.exists(CSV_PATH):
    print("[ERROR] exercise_enriched.csv 파일이 없습니다.")
    exit()

# CSV 로드
df = pd.read_csv(CSV_PATH)

# 컬럼명 출력
print("CSV columns:", df.columns.tolist())

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("[*] 기존 exerciseCategory 테이블 삭제...")
cur.execute("DROP TABLE IF EXISTS exerciseCategory;")

print("[*] 새 exerciseCategory 테이블 생성...")
cur.execute("""
CREATE TABLE exerciseCategory (
    exerciseId TEXT PRIMARY KEY,
    name TEXT,
    gifUrl TEXT,
    targetMuscles TEXT,
    bodyParts TEXT,
    equipments TEXT,
    secondaryMuscles TEXT,
    instructions TEXT,
    difficulty TEXT,
    risk_score REAL,
    category TEXT,
    effectiveness REAL
);
""")

print("[*] 데이터 INSERT 중...")

df.to_sql("exerciseCategory", conn, if_exists="append", index=False)

conn.commit()
conn.close()

print("✔ 성공! exerciseCategory 테이블이 CSV 기반으로 생성되었습니다.")

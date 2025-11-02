# src/load_food_data.py
import os
import pandas as pd
import src.db as db

# DB 초기화
db.init_db()

# 현재 파일 기준 data 디렉토리
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
FILE_FOOD = os.path.join(DATA_DIR, "food_db.xlsx")
FILE_PROCESSED = os.path.join(DATA_DIR, "processed_food_db.xlsx")

# 매핑 테이블에 '식품중량' 추가 ✅
MAPPING = {
    "식품명": "name",
    "에너지(kcal)": "calories",
    "탄수화물(g)": "carbs",
    "단백질(g)": "protein",
    "지방(g)": "fat",
    "식이섬유(g)": "fiber",
    "당류(g)": "sugar",
    "나트륨(mg)": "sodium",
    "식품중량": "weight",  # ✅ 추가된 부분
    "업체명": "company"
}

def safe_float(val):
    try:
        return float(val) if pd.notna(val) else 0.0
    except Exception:
        return 0.0

def parse_weight(val):
    """
    "900g", "100 g" 같은 문자열 처리 후 float 반환
    """
    if pd.isna(val):
        return 0.0
    val_str = str(val).strip().lower().replace("g", "").replace(" ", "")
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def load_excel_to_db(filepath: str):
    df = pd.read_excel(filepath)

    # 매핑 가능한 컬럼만 필터링
    available_mapping = {k: v for k, v in MAPPING.items() if k in df.columns}
    df = df[list(available_mapping.keys())].rename(columns=available_mapping)

    session = db.SessionLocal()
    existing_names = {(f.name, f.company) for f in session.query(db.Food).all()}
    count = 0

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        name = str(row["name"]).strip()
        company = str(row.get("company") or "해당없음").strip()
        key = (name, company)
        counter = 1
        while key in existing_names:
            name_candidate = f"{row['name']}_{counter}"
            key = (name_candidate, company)
            counter += 1
        name = key[0]
        existing_names.add(key)

        food = db.Food(
            name=name,
            company=company,
            calories=safe_float(row.get("calories")),
            carbs=safe_float(row.get("carbs")),
            protein=safe_float(row.get("protein")),
            fat=safe_float(row.get("fat")),
            fiber=safe_float(row.get("fiber")),
            sugar=safe_float(row.get("sugar")),
            sodium=safe_float(row.get("sodium")),
            weight=parse_weight(row.get("weight")),  # ✅ 수정된 부분
        )
        session.add(food)
        count += 1

        if idx % 1000 == 0:
            session.commit()

    session.commit()
    session.close()
    print(f"{count}개 새 데이터 저장 완료: {os.path.basename(filepath)}")

if __name__ == "__main__":
    load_excel_to_db(FILE_FOOD)
    load_excel_to_db(FILE_PROCESSED)

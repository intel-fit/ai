import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

food_db_path = os.path.join(DATA_DIR, "food_db.xlsx")
processed_food_db_path = os.path.join(DATA_DIR, "processed_food_db.xlsx")
output_path = os.path.join(DATA_DIR, "combined_food_db.xlsx")

# 엑셀 불러오기
food_db = pd.read_excel(food_db_path)
processed_food_db = pd.read_excel(processed_food_db_path)

# 2. 필요한 컬럼 정의 및 이름 통일
food_columns = {
    "식품코드": "food_code",
    "식품명": "food_name",
    "식품대분류명": "category_large",
    "식품중분류명": "category_medium",
    "식품소분류명": "category_small",
    "식품세분류명": "category_detail",
    "에너지(kcal)": "energy_kcal",
    "단백질(g)": "protein_g",
    "지방(g)": "fat_g",
    "탄수화물(g)": "carb_g",
    "식이섬유(g)": "fiber_g",
    "당류(g)": "sugar_g",
    "나트륨(mg)": "sodium_mg",
    "식품기원명": "food_origin",
    "데이터구분명": "data_type",
    "출처명": "source",
    "업체명": "company",
    "식품중량": "serving_size"
}

processed_food_columns = food_columns.copy()
# processed_food_db에는 '업체명' 대신 '제조사명'과 '수입업체명' 사용
processed_food_columns.pop("업체명")  # 기존 '업체명' 제거

# 3. processed_food_db에서 company 컬럼 생성
processed_food_db["제조사명"] = processed_food_db["제조사명"].fillna("해당없음")
processed_food_db["수입업체명"] = processed_food_db["수입업체명"].fillna("해당없음")
processed_food_db["company"] = processed_food_db.apply(
    lambda row: row["제조사명"] if row["제조사명"] != "해당없음" else row["수입업체명"],
    axis=1
)

# 4. 필요한 컬럼만 선택 및 이름 변경
food_db_processed = food_db[list(food_columns.keys())].rename(columns=food_columns)
processed_food_db_processed = processed_food_db[list(processed_food_columns.keys()) + ["company"]].rename(
    columns=processed_food_columns
)

# 5. 두 DB 합치기
combined_db = pd.concat([food_db_processed, processed_food_db_processed], ignore_index=True)

# 6. 중복 제거 (식품코드 기준)
combined_db = combined_db.drop_duplicates(subset="food_code")

# 7. src/data 경로에 저장
data_dir = os.path.join("src", "data")
os.makedirs(data_dir, exist_ok=True)
output_file = os.path.join(data_dir, "combined_food_db.xlsx")
combined_db.to_excel(output_file, index=False)

print(f"통합 DB가 '{output_file}'로 생성되었습니다.")

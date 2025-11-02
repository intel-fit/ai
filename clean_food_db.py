import pandas as pd
import numpy as np
import os
import re

# -----------------------------
# 1. 파일 경로 설정
# -----------------------------
INPUT_PATH = os.path.join("src", "data", "combined_food_db.xlsx")
OUTPUT_PATH = os.path.join("src", "data", "cleaned_food_db.xlsx")

# -----------------------------
# 2. 데이터 불러오기
# -----------------------------
food_df = pd.read_excel(INPUT_PATH)
print(f"✅ 원본 데이터 로드 완료: {food_df.shape}")

# -----------------------------
# 3. 결측치 처리 (영양소 NaN → 0)
# -----------------------------
nutrient_cols = ['energy_kcal', 'protein_g', 'fat_g', 'carb_g', 'fiber_g', 'sugar_g', 'sodium_mg']
food_df[nutrient_cols] = food_df[nutrient_cols].fillna(0)

# -----------------------------
# 4. serving_size 정제 ("200g" → 200)
# -----------------------------
def extract_number(value):
    if pd.isna(value):
        return np.nan
    match = re.search(r'(\d+\.?\d*)', str(value))
    return float(match.group(1)) if match else np.nan

food_df['serving_size_g'] = food_df['serving_size'].apply(extract_number)

# -----------------------------
# 5. 100g 결측치 처리 (냉면 등 총중량 보정)
# -----------------------------
def estimate_serving(row):
    name = str(row['food_name'])
    size = row['serving_size_g']

    # 이미 100 이상 정상값인 경우 유지
    if pd.notna(size) and size > 100:
        return size, False

    # 이름 기반 평균 추정치 (g)
    if any(k in name for k in ['냉면', '면', '파스타', '국수', '칼국수']):
        return 600.0, True
    elif any(k in name for k in ['찌개', '국', '탕', '수프']):
        return 400.0, True
    elif any(k in name for k in ['밥', '덮밥', '비빔밥', '볶음밥']):
        return 300.0, True
    elif any(k in name for k in ['샐러드']):
        return 250.0, True
    elif any(k in name for k in ['과일', '주스']):
        return 200.0, True
    elif any(k in name for k in ['빵', '토스트']):
        return 120.0, True
    elif any(k in name for k in ['치킨', '고기', '스테이크', '삼겹살']):
        return 250.0, True
    elif any(k in name for k in ['도시락', '세트', '정식']):
        return 600.0, True

    # 추정 불가 → 그대로 유지
    return size if pd.notna(size) else 100.0, pd.isna(size) or size == 100.0

food_df[['serving_size_g', 'is_estimated']] = food_df.apply(lambda r: pd.Series(estimate_serving(r)), axis=1)

# -----------------------------
# 6. category_detail 정제 ("해당없음" → NaN)
# -----------------------------
food_df['category_detail'] = food_df['category_detail'].replace('해당없음', np.nan)

# -----------------------------
# 7. 이상치 제거 (칼로리 10,000 kcal 이상)
# -----------------------------
before = food_df.shape[0]
food_df = food_df[food_df['energy_kcal'] < 10000]
after = food_df.shape[0]
print(f"⚙️ 칼로리 이상치 제거: {before - after}개 항목 제거됨")

# -----------------------------
# 8. 정렬 및 컬럼 순서 정리
# -----------------------------
cols_order = [
    'food_code', 'food_name',
    'category_large', 'category_medium', 'category_small', 'category_detail',
    'energy_kcal', 'protein_g', 'fat_g', 'carb_g', 'fiber_g', 'sugar_g', 'sodium_mg',
    'serving_size', 'serving_size_g', 'is_estimated',
    'food_origin', 'data_type', 'source', 'company'
]
food_df = food_df[cols_order].sort_values(['category_large', 'category_medium', 'food_name']).reset_index(drop=True)

# -----------------------------
# 9. 저장
# -----------------------------
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
food_df.to_excel(OUTPUT_PATH, index=False)
print(f"✅ 정제된 데이터 저장 완료: {OUTPUT_PATH}")
print(f"✅ 최종 데이터 크기: {food_df.shape}")

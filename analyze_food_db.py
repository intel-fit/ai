import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import rc
import seaborn as sns
import os

# -----------------------------
# 한글 깨짐 방지
# -----------------------------
rc('font', family='Malgun Gothic')
plt.rcParams['axes.unicode_minus'] = False

# -----------------------------
# pandas 출력 옵션 설정
# -----------------------------
pd.set_option('display.max_rows', None)   # 모든 행 출력
pd.set_option('display.max_columns', None) # 모든 열 출력
pd.set_option('display.width', 200)      # 출력 폭 조절

# -----------------------------
# 1. 엑셀 파일 불러오기
# -----------------------------
DATA_PATH = os.path.join("src", "data", "cleaned_food_db.xlsx")
food_db = pd.read_excel(DATA_PATH)

# -----------------------------
# 2. 기본 정보 확인
# -----------------------------
print("==== 데이터 기본 정보 ====")
print(food_db.info(), "\n")

print("==== 컬럼 리스트 ====")
print(food_db.columns.tolist(), "\n")

print("==== 상위 5개 샘플 ====")
print(food_db.head(), "\n")

# -----------------------------
# 3. 결측치 확인
# -----------------------------
print("==== 결측치 현황 ====")
print(food_db.isna().sum(), "\n")

# -----------------------------
# 4. 카테고리별 분포
# -----------------------------
print("==== 대분류별 음식 수 ====")
print(food_db['category_large'].value_counts(), "\n")

print("==== 중분류별 음식 수 ====")
print(food_db['category_medium'].value_counts(), "\n")

print("==== 소분류 상위 20개 ====")
print(food_db['category_small'].value_counts().head(20), "\n")

print("==== 상세 분류 상위 20개 ====")
print(food_db['category_detail'].value_counts().head(20), "\n")

# -----------------------------
# 5. 영양소 통계
# -----------------------------
nutrition_cols = ['energy_kcal','protein_g','fat_g','carb_g','fiber_g','sugar_g','sodium_mg']
print("==== 영양소 기본 통계 ====")
print(food_db[nutrition_cols].describe(), "\n")

print("==== 칼로리 상위 10 음식 ====")
print(food_db.sort_values('energy_kcal', ascending=False)[['food_name','energy_kcal']].head(10), "\n")

# -----------------------------
# 6. 시각화: 대분류별 평균 칼로리
# -----------------------------
plt.figure(figsize=(12,6))
avg_cal_by_category = food_db.groupby('category_large')['energy_kcal'].mean().sort_values()
sns.barplot(x=avg_cal_by_category.index, y=avg_cal_by_category.values)
plt.xticks(rotation=45, ha='right')
plt.ylabel("평균 칼로리")
plt.title("대분류별 평균 칼로리")
plt.tight_layout()
plt.show()

# -----------------------------
# 7. 시각화: 중분류별 평균 칼로리 상위 15
# -----------------------------
plt.figure(figsize=(12,6))
avg_cal_by_medium = food_db.groupby('category_medium')['energy_kcal'].mean().sort_values(ascending=False).head(15)
sns.barplot(x=avg_cal_by_medium.index, y=avg_cal_by_medium.values)
plt.xticks(rotation=45, ha='right')
plt.ylabel("평균 칼로리")
plt.title("중분류별 평균 칼로리 상위 15")
plt.tight_layout()
plt.show()

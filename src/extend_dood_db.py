import pandas as pd
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
import numpy as np

# --------------------------------------------
# 파일 경로
# --------------------------------------------
input_path = "src/data/cleaned_food_db.xlsx"
output_path = "src/data/extended_food_db_clustered_stage1.xlsx"

# --------------------------------------------
# 1️⃣ 데이터 로드
# --------------------------------------------
print("📂 Loading dataset...")
df = pd.read_excel(input_path)
print(f"✅ Loaded {len(df):,} rows and {len(df.columns)} columns")

# --------------------------------------------
# 2️⃣ 기능성 + 카테고리 확장
# --------------------------------------------
def map_main(x):
    x = str(x)
    if any(k in x for k in ["곡", "서류"]): return "곡류"
    if any(k in x for k in ["육", "고기", "식육"]): return "육류"
    if any(k in x for k in ["채소", "나물", "해조"]): return "채소류"
    if "과일" in x: return "과일류"
    if any(k in x for k in ["유", "치즈", "알"]): return "유제품류"
    if any(k in x for k in ["수산", "젓갈"]): return "어패류"
    if any(k in x for k in ["장", "양념", "조미"]): return "양념류"
    if any(k in x for k in ["즉석", "가공", "특수"]): return "가공식품류"
    if any(k in x for k in ["음료", "주류"]): return "음료류"
    return "기타"

def infer_function(row):
    text = f"{row.get('category_large', '')} {row.get('category_medium', '')} {row.get('category_small', '')}".lower()
    if any(k in text for k in ["균형영양", "표준형", "영양조제", "일반 환자용"]):
        return "균형영양조제식품"
    if any(k in text for k in ["체중조절", "다이어트", "단백질쉐이크"]):
        return "체중조절용 조제식품"
    if any(k in text for k in ["환자용", "질환자용", "암환자", "신장질환", "고혈압", "임산부", "고령자"]):
        return "특수의료용/환자용 식품"
    if any(k in text for k in ["이유식", "영아용", "유아용", "성장기"]):
        return "영유아용 식품"
    if any(k in text for k in ["특수영양", "특수의료"]):
        return "기타 특수영양식품"
    return "일반식품"

df["category_main"] = df["category_large"].apply(map_main)
df["category_function"] = df.apply(infer_function, axis=1)

# --------------------------------------------
# 3️⃣ 최적 k 탐색 함수 (Elbow + Silhouette)
# --------------------------------------------
def find_optimal_k(data, k_min=15, k_max=30, min_sil=0.1):
    inertias, silhouettes = [], []
    for k in range(k_min, k_max + 1):
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(data)
        inertias.append(kmeans.inertia_)
        sil = silhouette_score(data, labels) if k < len(data) else 0
        silhouettes.append(sil)
    # 엘보우 지점 + 실루엣 조합
    diffs = np.diff(inertias)
    elbow_k = np.argmin(diffs) + k_min + 1
    best_sil_k = np.argmax(silhouettes) + k_min
    final_k = best_sil_k if silhouettes[np.argmax(silhouettes)] > min_sil else elbow_k
    print(f"📊 Optimal K estimated: {final_k} (Sil={max(silhouettes):.3f})")
    return final_k

# --------------------------------------------
# 4️⃣ 1차 군집화 (카테고리 중심)
# --------------------------------------------
print("🔧 Running category-based clustering (Stage 1)...")

encoded_df = df[["category_large", "category_medium", "category_small", "category_main", "category_function"]].copy()
for col in encoded_df.columns:
    encoded_df[col] = LabelEncoder().fit_transform(encoded_df[col].astype(str))

scaled_cat = StandardScaler().fit_transform(encoded_df)

print("🔍 Finding optimal number of clusters between 15–30...")
opt_k_cat = find_optimal_k(scaled_cat, k_min=15, k_max=30)

df["category_cluster"] = KMeans(n_clusters=opt_k_cat, random_state=42, n_init=10).fit_predict(scaled_cat)

# --------------------------------------------
# 5️⃣ 저장
# --------------------------------------------
df.to_excel(output_path, index=False)
print(f"✅ Stage 1 clustering saved: {output_path}")
print(f"Category clusters: {opt_k_cat}")
print(f"현재 단계에서는 영양 기반 군집화는 수행하지 않습니다.")

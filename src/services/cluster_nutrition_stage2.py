# src/services/cluster_nutrition_stage2.py
import os
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

# --------------------------------
# 설정
# --------------------------------
INPUT_PATH  = os.path.join("src", "data", "extended_food_db.xlsx")
OUTPUT_PATH = os.path.join("src", "data", "extended_food_db_clustered_stage2.xlsx")

# --------------------------------
# 1️⃣ 데이터 로드
# --------------------------------
if not os.path.exists(INPUT_PATH):
    raise FileNotFoundError(f"[ERROR] Input file not found: {INPUT_PATH}")

df = pd.read_excel(INPUT_PATH)

# 필수 컬럼 체크
nutr_cols = [
    "energy_kcal", "protein_g", "fat_g", "carb_g",
    "fiber_g", "sugar_g", "sodium_mg", "glycemic_index",
    "processing_level", "hybrid_health_score"
]

missing = [c for c in nutr_cols if c not in df.columns]
if missing:
    raise ValueError(f"[ERROR] Missing columns in input file: {missing}")

# --------------------------------
# 2️⃣ 전처리
# --------------------------------
# 결측값 → 평균으로 보정
df[nutr_cols] = df[nutr_cols].apply(pd.to_numeric, errors="coerce")
df[nutr_cols] = df[nutr_cols].fillna(df[nutr_cols].mean())

# Standard Scaling
scaler = StandardScaler()
scaled = scaler.fit_transform(df[nutr_cols])

# --------------------------------
# 3️⃣ 최적 클러스터 개수 탐색
# --------------------------------
def find_optimal_k(data, k_min=5, k_max=25):
    """Silhouette score 기반 최적 K 탐색"""
    inertias, silhouettes = [], []
    for k in range(k_min, k_max + 1):
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(data)
        inertias.append(kmeans.inertia_)
        sil = silhouette_score(data, labels)
        silhouettes.append(sil)
        print(f"  k={k:2d} → inertia={inertias[-1]:.0f}, silhouette={sil:.3f}")
    
    best_idx = int(np.argmax(silhouettes))
    final_k = k_min + best_idx
    print(f"\n📊 Optimal K = {final_k} (Silhouette = {silhouettes[best_idx]:.3f})")
    return final_k

opt_k = find_optimal_k(scaled, 5, 25)

# --------------------------------
# 4️⃣ 최종 K-Means 모델 적용
# --------------------------------
kmeans = KMeans(n_clusters=opt_k, random_state=42, n_init=10)
df["nutrition_cluster"] = kmeans.fit_predict(scaled)

# 각 클러스터별 통계 요약
summary = df.groupby("nutrition_cluster")[nutr_cols].mean().round(2)
print("\n📈 Cluster Summary (avg per group):")
print(summary)

# --------------------------------
# 5️⃣ 결과 저장
# --------------------------------
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
df.to_excel(OUTPUT_PATH, index=False)
print(f"\n✅ Stage 2 nutrition-based clustering saved → {OUTPUT_PATH}")

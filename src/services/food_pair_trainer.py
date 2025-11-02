# src/services/food_pair_trainer.py
import os, json, math, itertools, time
from collections import Counter, defaultdict
import pandas as pd

DATA_DIR = os.path.join("src", "data")
LOG_PATH = os.path.join(DATA_DIR, "meal_logs.jsonl")  # 하루별 추천 결과 로그
PAIR_OUT_PARQUET = os.path.join(DATA_DIR, "food_pair_scores.parquet")
PAIR_OUT_JSON = os.path.join(DATA_DIR, "food_pair_scores.json")
FOOD_DB_PATH = os.path.join(DATA_DIR, "cleaned_food_db_final.xlsx")  # ✅ 정제된 DB 기반 필터링


def _norm_pair(a: str, b: str):
    a, b = str(a), str(b)
    return (a, b) if a <= b else (b, a)


# ---------------------------------------------------------
# 1️⃣ 로그 로드
# ---------------------------------------------------------
def load_logs(path=LOG_PATH):
    """meal_logs.jsonl 로드 (1줄 = 1일치 식단 로그)"""
    if not os.path.exists(path):
        print(f"⚠️ No logs found at {path}")
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rows.append(json.loads(line))
            except:
                pass
    print(f"📘 Loaded {len(rows)} daily logs")
    return rows


# ---------------------------------------------------------
# 2️⃣ 하루 식단에서 음식쌍 추출
# ---------------------------------------------------------
def extract_pairs_from_daily_plan(daily_plan: dict):
    """한 일(day)의 각 끼니에서 아이템 food_name을 뽑아 페어/단일 출현 카운트."""
    single = Counter()
    pair = Counter()
    meals = daily_plan.get("meals", [])
    for meal in meals:
        names = []
        for it in meal.get("items", []):
            n = it.get("food_name")
            if not n:
                continue
            names.append(n)

        # 단일 출현수
        for n in set(names):
            single[n] += 1

        # 음식쌍 조합
        for a, b in itertools.combinations(sorted(set(names)), 2):
            pair[(a, b)] += 1
    return single, pair


# ---------------------------------------------------------
# 3️⃣ 메인 학습 함수
# ---------------------------------------------------------
def train_from_logs():
    logs = load_logs()
    # ⚙️ 로그 없을 때 샘플 생성 (테스트용)
    if not logs:
        print("⚠️ No logs found. Generating small synthetic sample for testing...")
        sample_daily = {
            "meals": [
                {"items": [{"food_name": "현미밥"}, {"food_name": "닭가슴살"}, {"food_name": "샐러드"}]},
                {"items": [{"food_name": "잡곡밥"}, {"food_name": "두부"}, {"food_name": "나물"}]},
                {"items": [{"food_name": "고구마"}, {"food_name": "계란"}, {"food_name": "브로콜리"}]},
            ]
        }
        logs = [{"daily_plan": sample_daily} for _ in range(10)]

    # ✅ 유효 음식 목록 로드 (정제된 DB 기반 필터링)
    valid_foods = set()
    if os.path.exists(FOOD_DB_PATH):
        db = pd.read_excel(FOOD_DB_PATH)
        valid_foods = set(db["food_name"].astype(str).tolist())
        print(f"✅ Loaded {len(valid_foods)} valid food names from DB")

    single = Counter()
    pair = Counter()
    N_meals = 0

    # ---- 모든 로그 순회 ----
    for row in logs:
        daily = row.get("daily_plan") or row.get("plan") or {}
        s, p = extract_pairs_from_daily_plan(daily)
        single.update(s)
        pair.update(p)
        N_meals += len(daily.get("meals", []))

    # ---- 노이즈 제거 ----
    min_single = 2  # 2회 이상 등장한 음식만
    min_pair = 2    # 2회 이상 등장한 페어만
    single = Counter({k: v for k, v in single.items() if v >= min_single})
    pair = Counter({k: v for k, v in pair.items() if v >= min_pair and k[0] in single and k[1] in single})

    # ---- 유효 음식만 남기기 ----
    if valid_foods:
        pair = Counter({(a, b): c for (a, b), c in pair.items() if a in valid_foods and b in valid_foods})
        single = Counter({k: v for k, v in single.items() if k in valid_foods})

    print(f"📊 Training pairs: {len(pair)}, singles: {len(single)}, meals logged: {N_meals}")

    # ---- PMI / Lift 계산 ----
    k = 1.0
    vocab = set(single.keys())
    N = max(1, N_meals)
    records = []

    for (a, b), c_ab in pair.items():
        c_a = single.get(a, 0)
        c_b = single.get(b, 0)
        p_a = (c_a + k) / (N + k * len(vocab))
        p_b = (c_b + k) / (N + k * len(vocab))
        p_ab = (c_ab + k) / (N + k * len(vocab))

        pmi = math.log(max(1e-12, p_ab / (p_a * p_b)))
        lift = p_ab / (p_a * p_b)
        pmi_sig = 1 / (1 + math.exp(-pmi))
        support = c_ab
        score = pmi_sig * (1 - math.exp(-support / 5))
        records.append({
            "food_a": a, "food_b": b,
            "count_ab": c_ab, "count_a": c_a, "count_b": c_b,
            "pmi": pmi, "lift": lift, "score": score
        })

    # ---- 저장 ----
    df = pd.DataFrame(records).sort_values("score", ascending=False)
    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_parquet(PAIR_OUT_PARQUET, index=False)

    # ---- JSON (양방향 매핑, 안전 필터 포함) ----
    top = df[df["score"] > 0].copy()
    pair_map = defaultdict(list)
    for _, r in top.iterrows():
        if not isinstance(r["food_a"], str) or not isinstance(r["food_b"], str):
            continue
        pair_map[r["food_a"]].append([r["food_b"], float(r["score"])])
        pair_map[r["food_b"]].append([r["food_a"], float(r["score"])])

    with open(PAIR_OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"updated": int(time.time()), "pairs": pair_map}, f, ensure_ascii=False)

    print(f"✅ Pair training done. meals={N_meals:,}, pairs={len(df):,}, saved → {PAIR_OUT_JSON}")
    return df


if __name__ == "__main__":
    train_from_logs()

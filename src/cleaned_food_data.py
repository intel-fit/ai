import pandas as pd

# --------------------------------------------
# 파일 로드
# --------------------------------------------
df = pd.read_excel("src/data/cleaned_food_db.xlsx")

# "해당없음"을 결측치처럼 처리
df = df.replace("해당없음", "")

# 결측값 채우기 (빈 문자열)
df["category_large"] = df["category_large"].fillna("미분류")
df["category_medium"] = df["category_medium"].fillna("")
df["category_small"] = df["category_small"].fillna("")

# --------------------------------------------
# 계층 트리 생성
# --------------------------------------------
tree_summary = {}

for _, row in df.iterrows():
    large = row["category_large"].strip()
    medium = row["category_medium"].strip()
    small = row["category_small"].strip()

    if large not in tree_summary:
        tree_summary[large] = {}

    # 중분류가 없을 경우 — 소분류를 바로 연결
    if medium == "":
        tree_summary[large].setdefault("_direct_small_", set()).add(small)
    else:
        if medium not in tree_summary[large]:
            tree_summary[large][medium] = set()
        if small:
            tree_summary[large][medium].add(small)

# --------------------------------------------
# 보기 좋게 출력
# --------------------------------------------
for large, mids in tree_summary.items():
    print("=" * 100)
    print(f"📂 {large}")
    print("-" * 100)

    if "_direct_small_" in mids:
        direct_smalls = sorted(list(mids["_direct_small_"]))
        print(f"  • (중분류 없음) → 소분류 {len(direct_smalls)}개:")
        print("    " + ", ".join(direct_smalls[:15]) + (" ..." if len(direct_smalls) > 15 else ""))
        print()

    for mid, smalls in mids.items():
        if mid == "_direct_small_":
            continue
        small_list = sorted(list(smalls))
        if small_list:
            print(f"  🔹 {mid} → 소분류 {len(small_list)}개:")
            print("    " + ", ".join(small_list[:10]) + (" ..." if len(small_list) > 10 else ""))
        else:
            print(f"  🔹 {mid} (소분류 없음)")
    print()

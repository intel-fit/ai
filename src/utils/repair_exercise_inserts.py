# -*- coding: utf-8 -*-
# src/utils/repair_exercise_inserts.py
import os, re, sqlite3, unicodedata
from sqlparse import split

DB_PATH  = "src/data/exercise.db"
SQL_PATH = "src/data/exerciseCategoryDataBase_sqlite.sql"  # 네가 넣어둔 '고쳐준 파일'

def sanitize_sqlite_strings(values_clause: str) -> str:
    """
    VALUES (...) 내부 문자열에서 SQLite에 맞지 않는 이스케이프를 정리:
    - 백슬래시-작은따옴표 \\'  ->  '' (SQLite 표준)
    - 스마트 따옴표 -> 일반 따옴표
    - 제어문자 제거
    """
    s = unicodedata.normalize("NFKC", values_clause)
    # 숨은 제어문자(탭/개행 제외) 제거
    s = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", s)
    # 스마트 따옴표 표준화
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    # 백슬래시+작은따옴표 -> 작은따옴표 2개
    s = s.replace("\\'", "''").replace('\\"', '"')
    return s

def extract_values_clause(insert_stmt: str) -> str:
    # INSERT ... VALUES ( ... );
    m = re.search(r"VALUES\s*(\(.+\))\s*;?\s*$", insert_stmt, flags=re.IGNORECASE | re.DOTALL)
    return m.group(1) if m else None

def get_exercise_id_from_values(values_clause: str) -> str:
    # 첫 번째 값이 exerciseId 라고 가정(문자열 리터럴)
    m = re.match(r"\(\s*'([^']*)'", values_clause.strip(), flags=re.DOTALL)
    if m:
        return m.group(1)
    return None

def main():
    if not os.path.exists(DB_PATH):
        raise SystemExit(f"DB not found: {DB_PATH}")
    if not os.path.exists(SQL_PATH):
        raise SystemExit(f"SQL not found: {SQL_PATH}")

    with open(SQL_PATH, "r", encoding="utf-8") as f:
        raw = f.read()

    # 가능한 한 원문 유지하되, 구문 split만
    stmts = [s.strip() for s in split(raw) if s.strip()]
    insert_stmts = [s for s in stmts if s.upper().startswith("INSERT")]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    repaired, skipped = 0, 0
    for stmt in insert_stmts:
        values = extract_values_clause(stmt)
        if not values:
            continue
        exid = get_exercise_id_from_values(values)
        if not exid:
            continue

        # 이미 있는지 확인
        try:
            cur.execute("SELECT 1 FROM exerciseCategory WHERE exerciseId = ? LIMIT 1", (exid,))
            exists = cur.fetchone() is not None
        except sqlite3.Error:
            # 테이블 이름/스키마 문제면 중단
            raise

        if exists:
            continue  # 이미 들어간 레코드는 패스

        # 누락된 레코드만 보정해서 재삽입
        clean_values = sanitize_sqlite_strings(values)
        repaired_stmt = re.sub(r"VALUES\s*\(.+\)\s*;?\s*$",
                               f"VALUES {clean_values};",
                               stmt,
                               flags=re.IGNORECASE | re.DOTALL)

        try:
            cur.execute(repaired_stmt)
            repaired += 1
        except sqlite3.Error as e:
            # 마지막 방어: 작은따옴표를 한 번 더 안전하게(문자열 리터럴 내부만) 늘려보기
            # 매우 보수적으로 전체 values 내 단일 ' 를 '' 로 (이미 '' 인 곳은 영향 없음)
            fail_values = clean_values.replace("'", "''")
            last_try = re.sub(r"VALUES\s*\(.+\)\s*;?\s*$",
                              f"VALUES {fail_values};",
                              stmt,
                              flags=re.IGNORECASE | re.DOTALL)
            try:
                cur.execute(last_try)
                repaired += 1
            except sqlite3.Error as e2:
                skipped += 1
                print(f"⚠️ skipped {exid}: {e2}")

    conn.commit()

    # 최종 카운트 확인
    cur.execute("SELECT COUNT(*) FROM exerciseCategory;")
    total = cur.fetchone()[0]
    conn.close()

    print(f"✅ Repair done. Repaired inserts: {repaired}, Still skipped: {skipped}")
    print(f"🔢 Now exerciseCategory rows = {total}")

if __name__ == "__main__":
    main()

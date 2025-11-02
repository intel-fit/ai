# -*- coding: utf-8 -*-
# src/utils/make_exercise_db_safe.py
import os, re, sqlite3, unicodedata
try:
    from sqlparse import split
except:
    raise SystemExit("sqlparse가 필요합니다.  (.venv)에서:  pip install sqlparse")

SQL_PATH = "src/data/exerciseCategoryDataBase_sqlite.sql"   # 네가 넣어둔 '고쳐준 파일'
DB_PATH  = "src/data/exercise.db"

def clean_mysqlisms(sql: str) -> str:
    s = unicodedata.normalize("NFKC", sql).replace("\r", "\n")
    # MySQL 전용 구문/주석 제거
    s = re.sub(r"/\*![\s\S]*?\*/;", "", s)                # /*! ... */;
    s = re.sub(r"(?mi)^\s*USE\s+\w+;\s*", "", s)          # USE db;
    s = re.sub(r"(?mi)^\s*SET\s+.*?;\s*", "", s)          # SET ...
    s = re.sub(r"(?mi)^\s*LOCK TABLES.*?;\s*", "", s)
    s = re.sub(r"(?mi)^\s*UNLOCK TABLES.*?;\s*", "", s)
    s = re.sub(r"ENGINE\s*=\s*\w+\s*", "", s)
    s = re.sub(r"AUTO_INCREMENT\s*=\s*\d+\s*", "", s)
    s = re.sub(r"DEFAULT\s+CHARSET\s*=\s*\w+", "", s)
    # 백틱 제거, VARCHAR → TEXT
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"VARCHAR\(\d+\)", "TEXT", s, flags=re.IGNORECASE)
    return s

def sanitize_insert(stmt: str) -> str:
    t = stmt
    # 가끔 문자열 내부에 제어문자/비표준 따옴표가 섞여있어 파서가 깨짐 → 정규화
    t = unicodedata.normalize("NFKC", t)
    # NULL 바디 영문자 외 제어문자 제거(탭/개행은 허용)
    t = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", t)
    # 보기 드문 스마트따옴표 → 보통 따옴표
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    # 따옴표 불균형 방지: 값 내부의 ' 를 '' 로 이스케이프 (이미 이스케이프된건 그대로)
    # 다만 키워드/스키마에는 영향주지 않도록 VALUES 괄호 안쪽만 강화하는 간단한 보호막
    def _fix_values(m):
        inside = m.group(1)
        # 이미 SQL 문자열 경계 밖으로 나가지 않도록, 작은따옴표 안에서만 단순 이스케이프 추가
        buf, in_str = [], False
        for ch in inside:
            if ch == "'":
                buf.append("''" if in_str else "'")
                in_str = not in_str if not in_str else in_str  # 토글은 경계에서만
                # 위 한 줄은 경계를 완벽히 추적하지 못할 수 있으므로, 추가 방어:
                # 연속 따옴표는 그대로 두고, 단독 ' 는 두 개로 늘어남 → 파서 오류 예방 목적
            else:
                buf.append(ch)
        fixed = "".join(buf)
        return "(" + fixed + ")"
    t = re.sub(r"\(([\s\S]*)\)\s*;?\s*$", _fix_values, t, count=1)

    # 일부 덤프는 INSERT ... VALUES (...) 뒤에 ,(...) ,(...) ... 이어붙이는 형태일 수 있음 → 세미콜론 보장
    if not t.strip().endswith(";"):
        t = t.rstrip() + ";"
    return t

def main():
    if not os.path.exists(SQL_PATH):
        raise FileNotFoundError(f"SQL not found: {SQL_PATH}")

    with open(SQL_PATH, "r", encoding="utf-8") as f:
        raw = f.read()

    cleaned = clean_mysqlisms(raw)

    # 새 DB 생성(있으면 삭제)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    conn.execute("PRAGMA foreign_keys=OFF;")

    stmts = [s.strip() for s in split(cleaned) if s.strip()]
    ok, skipped = 0, 0
    first_error_snippet = None

    for i, stmt in enumerate(stmts, 1):
        try:
            cur.execute(stmt)
            ok += 1
            continue
        except sqlite3.OperationalError as e:
            # INSERT면 한 번 더 정규화해서 재시도
            if stmt[:6].upper() == "INSERT":
                try:
                    fixed = sanitize_insert(stmt)
                    cur.execute(fixed)
                    ok += 1
                    continue
                except Exception as e2:
                    skipped += 1
                    if first_error_snippet is None:
                        first_error_snippet = (i, str(e2), stmt[:300])
                    # 실패해도 계속 진행 (나머지 행 로딩)
                    continue
            else:
                skipped += 1
                if first_error_snippet is None:
                    first_error_snippet = (i, str(e), stmt[:300])
                continue
        except Exception as e:
            skipped += 1
            if first_error_snippet is None:
                first_error_snippet = (i, str(e), stmt[:300])
            continue

    conn.commit()

    # 간단 검증
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cur.fetchall()]
    except Exception:
        tables = []

    try:
        cur.execute("SELECT COUNT(*) FROM exerciseCategory;")
        cnt = cur.fetchone()[0]
    except Exception:
        cnt = None

    conn.close()

    print(f"✅ Done. Executed: {ok}, Skipped: {skipped}")
    print(f"📦 DB: {DB_PATH}")
    print(f"📋 Tables: {tables}")
    print(f"🔢 exerciseCategory rows: {cnt}")
    if first_error_snippet:
        i, msg, snip = first_error_snippet
        print("\n⚠️ First failing statement info (for reference):")
        print(f"  idx={i}, error={msg}")
        print(f"  snippet={snip!r}")

if __name__ == "__main__":
    main()

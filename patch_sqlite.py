import sqlite3

DB_PATH = "src/data/food_db.sqlite"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Check existing columns
cur.execute("PRAGMA table_info(subscriptions);")
columns = [row[1] for row in cur.fetchall()]
print("현재 subscriptions 컬럼:", columns)

# Patch list
patches = []

if "renewal_reminder_sent" not in columns:
    patches.append("ALTER TABLE subscriptions ADD COLUMN renewal_reminder_sent BOOLEAN DEFAULT 0;")

if "expire_reminder_sent" not in columns:
    patches.append("ALTER TABLE subscriptions ADD COLUMN expire_reminder_sent BOOLEAN DEFAULT 0;")

# Execute patch
for sql in patches:
    try:
        print("실행:", sql)
        cur.execute(sql)
    except Exception as e:
        print("오류:", e)

conn.commit()
conn.close()

print("패치 완료!")

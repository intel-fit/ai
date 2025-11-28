# src/routers/score_trend.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, timedelta
from fastapi.responses import StreamingResponse
import matplotlib.pyplot as plt
import io
import matplotlib
from matplotlib import font_manager, rc
import os
from src import db

router = APIRouter(tags=["Health Score Trend"])

matplotlib.use("Agg")

# -------------------- 한글 폰트 설정 --------------------
font_path = "C:/Windows/Fonts/malgun.ttf"
if not os.path.exists(font_path):
    font_path = font_manager.findfont("DejaVu Sans")

font_prop = font_manager.FontProperties(fname=font_path)
rc("font", family=font_prop.get_name())
plt.rcParams["axes.unicode_minus"] = False


def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

# ------------------------------------------------------------
# 공통 그래프 함수
# ------------------------------------------------------------
def _plot_lines(x, lines: dict, title: str, xlabel: str, ylabel: str):
    plt.figure(figsize=(10, 5))

    for label, y in lines.items():
        plt.plot(x, y, marker="o", linewidth=2, label=label)

    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(alpha=0.3)
    plt.legend()
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return buf


# ------------------------------------------------------------
# 1️⃣ 최근 7일 총점 그래프
# ------------------------------------------------------------
@router.get("/score/trend/daily/{user_id}")
def daily_score_trend(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    start = today - timedelta(days=6)

    rows = (
        session.query(db.DailyHealthScore)
        .filter(db.DailyHealthScore.user_id == user_id)
        .filter(db.DailyHealthScore.date >= start)
        .order_by(db.DailyHealthScore.date)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail="No daily score data found")

    x = [r.date.strftime("%m-%d") for r in rows]
    y = [r.total_score for r in rows]

    buf = _plot_lines(
        x,
        {"총점": y},
        title=f"{user_id} — 최근 7일 총점",
        xlabel="날짜",
        ylabel="총점(0~100)"
    )

    return StreamingResponse(buf, media_type="image/png")


# ------------------------------------------------------------
# 1-1️⃣ 최근 7일 세부점수 그래프
# ------------------------------------------------------------
@router.get("/score/trend/daily-detail/{user_id}")
def daily_score_detail(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    start = today - timedelta(days=6)

    rows = (
        session.query(db.DailyHealthScore)
        .filter(db.DailyHealthScore.user_id == user_id)
        .filter(db.DailyHealthScore.date >= start)
        .order_by(db.DailyHealthScore.date)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No daily score data found")

    x = [r.date.strftime("%m-%d") for r in rows]

    buf = _plot_lines(
        x,
        {
            "영양": [r.nutrition_score for r in rows],
            "운동": [r.exercise_score for r in rows],
            "밸런스": [r.balance_score for r in rows],
            "총점": [r.total_score for r in rows],
        },
        title=f"{user_id} — 최근 7일 세부 점수",
        xlabel="날짜",
        ylabel="점수(0~100)"
    )
    return StreamingResponse(buf, media_type="image/png")


# ------------------------------------------------------------
# 2️⃣ 최근 4주 총점 그래프
# ------------------------------------------------------------
@router.get("/score/trend/weekly/{user_id}")
def weekly_score_trend(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    week_starts = [monday - timedelta(days=7 * i) for i in range(4)]
    week_starts.sort()

    labels = []
    totals = []

    for ws in week_starts:
        we = ws + timedelta(days=6)
        rows = (
            session.query(db.DailyHealthScore)
            .filter(db.DailyHealthScore.user_id == user_id)
            .filter(db.DailyHealthScore.date >= ws)
            .filter(db.DailyHealthScore.date <= we)
            .all()
        )

        if not rows:
            continue

        avg_total = sum(r.total_score for r in rows) / len(rows)
        labels.append(f"{ws.strftime('%m-%d')}~{we.strftime('%m-%d')}")
        totals.append(avg_total)

    buf = _plot_lines(
        labels,
        {"평균 총점": totals},
        title=f"{user_id} — 최근 4주 총점",
        xlabel="주차",
        ylabel="점수(0~100)"
    )
    return StreamingResponse(buf, media_type="image/png")


# ------------------------------------------------------------
# 2-1️⃣ 최근 4주 세부점수 그래프
# ------------------------------------------------------------
@router.get("/score/trend/weekly-detail/{user_id}")
def weekly_score_detail(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    week_starts = [monday - timedelta(days=7 * i) for i in range(4)]
    week_starts.sort()

    labels = []
    nut, ex, bal, tot = [], [], [], []

    for ws in week_starts:
        we = ws + timedelta(days=6)
        rows = (
            session.query(db.DailyHealthScore)
            .filter(db.DailyHealthScore.user_id == user_id)
            .filter(db.DailyHealthScore.date >= ws)
            .filter(db.DailyHealthScore.date <= we)
            .all()
        )
        if not rows:
            continue

        def avg(lst): return sum(lst) / len(lst) if lst else 0

        labels.append(f"{ws.strftime('%m-%d')}~{we.strftime('%m-%d')}")
        nut.append(avg([r.nutrition_score for r in rows]))
        ex.append(avg([r.exercise_score for r in rows]))
        bal.append(avg([r.balance_score for r in rows]))
        tot.append(avg([r.total_score for r in rows]))

    buf = _plot_lines(
        labels,
        {
            "영양": nut,
            "운동": ex,
            "밸런스": bal,
            "총점": tot,
        },
        title=f"{user_id} — 최근 4주 세부 점수",
        xlabel="주차",
        ylabel="점수(0~100)"
    )
    return StreamingResponse(buf, media_type="image/png")


# ------------------------------------------------------------
# 3️⃣ 최근 3개월 총점 그래프
# ------------------------------------------------------------
@router.get("/score/trend/monthly/{user_id}")
def monthly_score_trend(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    this_month_start = today.replace(day=1)

    def prev_month_start(d: date):
        return (d - timedelta(days=1)).replace(day=1)

    month_starts = [this_month_start]
    for _ in range(2):
        month_starts.append(prev_month_start(month_starts[-1]))
    month_starts.sort()

    labels = []
    totals = []

    for ms in month_starts:
        next_month = (ms.replace(day=28) + timedelta(days=4)).replace(day=1)
        me = next_month - timedelta(days=1)

        rows = (
            session.query(db.DailyHealthScore)
            .filter(db.DailyHealthScore.user_id == user_id)
            .filter(db.DailyHealthScore.date >= ms)
            .filter(db.DailyHealthScore.date <= me)
            .all()
        )

        if not rows:
            continue

        avg_total = sum(r.total_score for r in rows) / len(rows)
        labels.append(ms.strftime("%Y-%m"))
        totals.append(avg_total)

    buf = _plot_lines(
        labels,
        {"평균 총점": totals},
        title=f"{user_id} — 최근 3개월 총점",
        xlabel="월",
        ylabel="점수(0~100)"
    )
    return StreamingResponse(buf, media_type="image/png")


# ------------------------------------------------------------
# 3-1️⃣ 최근 3개월 세부 점수 그래프
# ------------------------------------------------------------
@router.get("/score/trend/monthly-detail/{user_id}")
def monthly_score_detail(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    this_month_start = today.replace(day=1)

    def prev_month_start(d: date):
        return (d - timedelta(days=1)).replace(day=1)

    month_starts = [this_month_start]
    for _ in range(2):
        month_starts.append(prev_month_start(month_starts[-1]))
    month_starts.sort()

    labels = []
    nut, ex, bal, tot = [], [], [], []

    for ms in month_starts:
        next_month = (ms.replace(day=28) + timedelta(days=4)).replace(day=1)
        me = next_month - timedelta(days=1)

        rows = (
            session.query(db.DailyHealthScore)
            .filter(db.DailyHealthScore.user_id == user_id)
            .filter(db.DailyHealthScore.date >= ms)
            .filter(db.DailyHealthScore.date <= me)
            .all()
        )

        if not rows:
            continue

        def avg(lst): return sum(lst) / len(lst) if lst else 0

        labels.append(ms.strftime("%Y-%m"))
        nut.append(avg([r.nutrition_score for r in rows]))
        ex.append(avg([r.exercise_score for r in rows]))
        bal.append(avg([r.balance_score for r in rows]))
        tot.append(avg([r.total_score for r in rows]))

    buf = _plot_lines(
        labels,
        {
            "영양": nut,
            "운동": ex,
            "밸런스": bal,
            "총점": tot,
        },
        title=f"{user_id} — 최근 3개월 세부 점수",
        xlabel="월",
        ylabel="점수(0~100)"
    )
    return StreamingResponse(buf, media_type="image/png")

# src/routers/analytics.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, timedelta
import matplotlib.pyplot as plt
import io
from fastapi.responses import StreamingResponse, JSONResponse
from src import db
import matplotlib
import os
matplotlib.use("Agg") 
from matplotlib import font_manager, rc
font_path = "C:/Windows/Fonts/malgun.ttf"  # Windows: 맑은 고딕
if not os.path.exists(font_path):
    # Windows 폰트 없을 때 대체
    font_path = font_manager.findfont("DejaVu Sans")

font_prop = font_manager.FontProperties(fname=font_path)
rc("font", family=font_prop.get_name())
plt.rcParams["axes.unicode_minus"] = False

router = APIRouter(tags=["Analytics"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

# ----------------------------------------------------------
# 1️⃣ 일일 요약 조회
# ----------------------------------------------------------
@router.get("/analytics/daily/{user_id}", response_class=JSONResponse)
def get_daily_summary(user_id: str, session: Session = Depends(get_db)):
    rows_nut = (
        session.query(db.DailyNutritionSummary)
        .filter_by(user_id=user_id)
        .order_by(db.DailyNutritionSummary.date)
        .all()
    )
    rows_ex = (
        session.query(db.DailyExerciseSummary)
        .filter_by(user_id=user_id)
        .order_by(db.DailyExerciseSummary.date)
        .all()
    )

    if not rows_nut and not rows_ex:
        raise HTTPException(status_code=404, detail="No summary data found")

    # nutrition + exercise 병합
    merged = {}
    for r in rows_nut:
        merged[r.date.isoformat()] = {
            "kcal": r.kcal,
            "protein_g": r.protein_g,
            "fat_g": r.fat_g,
            "carb_g": r.carb_g,
            "processed_ratio": r.processed_ratio,
            "distinct_main_sources": r.distinct_main_sources,
        }
    for r in rows_ex:
        if r.date.isoformat() not in merged:
            merged[r.date.isoformat()] = {}
        merged[r.date.isoformat()].update({
            "duration_min": r.duration_min,
            "calories_burned": r.calories_burned,
            "avg_intensity": r.avg_intensity,
        })

    return JSONResponse(content={"user_id": user_id, "daily_summary": merged})

# ----------------------------------------------------------
# 2️⃣ 주간 트렌드 그래프 (섭취 vs 소모)
# ----------------------------------------------------------
@router.get("/analytics/weekly/{user_id}")
def get_weekly_trend(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    start = today - timedelta(days=6)

    # 최근 7일 데이터 조회
    rows_nut = (
        session.query(db.DailyNutritionSummary)
        .filter(db.DailyNutritionSummary.user_id == user_id)
        .filter(db.DailyNutritionSummary.date >= start)
        .all()
    )
    rows_ex = (
        session.query(db.DailyExerciseSummary)
        .filter(db.DailyExerciseSummary.user_id == user_id)
        .filter(db.DailyExerciseSummary.date >= start)
        .all()
    )

    if not rows_nut and not rows_ex:
        raise HTTPException(status_code=404, detail="No data in last 7 days")

    # 날짜별 매핑
    days = sorted(list({r.date for r in rows_nut + rows_ex}))
    kcal_in = [next((r.kcal for r in rows_nut if r.date == d), 0) for d in days]
    kcal_out = [next((r.calories_burned for r in rows_ex if r.date == d), 0) for d in days]

    plt.figure(figsize=(9, 5))
    plt.plot(days, kcal_in, marker="o", label="섭취 칼로리 (kcal)")
    plt.plot(days, kcal_out, marker="o", label="운동 소모 칼로리 (kcal)")
    plt.fill_between(days, kcal_in, kcal_out, color="lightgray", alpha=0.3)
    plt.title(f"{user_id} — 최근 7일 칼로리 트렌드")
    plt.xlabel("날짜")
    plt.ylabel("kcal")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()
    return StreamingResponse(buf, media_type="image/png")

# ----------------------------------------------------------
# 3️⃣ 월간 통계 요약 (평균값 JSON)
# ----------------------------------------------------------
@router.get("/analytics/monthly/{user_id}", response_class=JSONResponse)
def get_monthly_average(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    start = today.replace(day=1) - timedelta(days=30)
    rows = (
        session.query(db.DailyNutritionSummary)
        .filter(db.DailyNutritionSummary.user_id == user_id)
        .filter(db.DailyNutritionSummary.date >= start)
        .all()
    )

    if not rows:
        raise HTTPException(status_code=404, detail="No monthly data")

    avg_kcal = sum(r.kcal for r in rows) / len(rows)
    avg_prot = sum(r.protein_g for r in rows) / len(rows)
    avg_fat = sum(r.fat_g for r in rows) / len(rows)
    avg_carb = sum(r.carb_g for r in rows) / len(rows)

    return JSONResponse(
        content={
            "user_id": user_id,
            "period": f"{start} ~ {today}",
            "average": {
                "kcal": round(avg_kcal, 1),
                "protein_g": round(avg_prot, 1),
                "fat_g": round(avg_fat, 1),
                "carb_g": round(avg_carb, 1),
            },
            "days_counted": len(rows),
        }
    )

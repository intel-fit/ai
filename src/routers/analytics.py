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
from fastapi import Query

from src.services.summary_storage import (
    save_weekly_nutrition, save_weekly_exercise,
    save_monthly_nutrition, save_monthly_exercise
)
# === 새로 추가된 요약 테이블 모델 import ===
from src.db import (
    WeeklyNutritionSummary,
    WeeklyExerciseSummary,
    MonthlyNutritionSummary,
    MonthlyExerciseSummary
)


matplotlib.use("Agg")

from matplotlib import font_manager, rc

font_path = "C:/Windows/Fonts/malgun.ttf"  # Windows: 맑은 고딕 (Windows)
if not os.path.exists(font_path):
    # Windows 폰트 없을 때 대체 (서버용)
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

# ----------------------------------------------------------------------
#  계산 함수: 주간 평균 계산 (자동 저장용)
# ----------------------------------------------------------------------
def compute_week_data(session, user_id, ws, we):
    merged = _get_merged_daily_summaries(session, user_id, ws, we)

    nut_kcal, nut_prot, nut_fat, nut_carb = [], [], [], []
    ex_dur, ex_cal, ex_int = [], [], []

    for i in range(7):
        d = ws + timedelta(days=i)
        day_data = merged.get(d, {})
        nut = day_data.get("nutrition")
        ex = day_data.get("exercise")

        if nut:
            nut_kcal.append(nut.get("kcal", 0))
            nut_prot.append(nut.get("protein_g", 0))
            nut_fat.append(nut.get("fat_g", 0))
            nut_carb.append(nut.get("carb_g", 0))
        if ex:
            ex_dur.append(ex.get("duration_min", 0))
            ex_cal.append(ex.get("calories_burned", 0))
            ex_int.append(ex.get("avg_intensity", 0))

    def avg(lst): return sum(lst) / len(lst) if lst else 0

    nut = {
        "kcal": avg(nut_kcal),
        "protein": avg(nut_prot),
        "fat": avg(nut_fat),
        "carb": avg(nut_carb),
    }

    ex = {
        "duration_min": avg(ex_dur),
        "calories_burned": avg(ex_cal),
        "avg_intensity": avg(ex_int),
    }

    return nut, ex

# ----------------------------------------------------------------------
#  Weekly Summary 저장 + 조회 wrapper
# ----------------------------------------------------------------------
def get_or_compute_weekly_summary(session, user_id, ws, we):
    """
    저장된 값이 있으면 반환,
    없으면 계산 후 저장하고 반환
    """

    row_n = session.query(WeeklyNutritionSummary).filter(
        WeeklyNutritionSummary.user_id == user_id,
        WeeklyNutritionSummary.week_start == ws
    ).first()

    row_e = session.query(WeeklyExerciseSummary).filter(
        WeeklyExerciseSummary.user_id == user_id,
        WeeklyExerciseSummary.week_start == ws
    ).first()

    if row_n and row_e:
        return {
            "nutrition": {
                "kcal": row_n.avg_kcal,
                "protein": row_n.avg_protein,
                "fat": row_n.avg_fat,
                "carb": row_n.avg_carb,
            },
            "exercise": {
                "duration_min": row_e.avg_duration,
                "calories_burned": row_e.avg_calories_burned,
                "avg_intensity": row_e.avg_intensity,
            }
        }

    # 저장된 게 없으면 계산
    nut, ex = compute_week_data(session, user_id, ws, we)

    # 저장
    save_weekly_nutrition(session, user_id, ws, we, nut)
    save_weekly_exercise(session, user_id, ws, we, ex)

    return {
        "nutrition": nut,
        "exercise": ex,
    }


# ----------------------------------------
# 공통 유틸: 특정 기간의 일별 요약 병합
# ----------------------------------------
def _get_merged_daily_summaries(session: Session, user_id: str, start: date, end: date):
    """
    start ~ end 사이의 DailyNutritionSummary + DailyExerciseSummary를
    날짜별(dict)로 병합해서 반환.

    key: datetime.date
    value: {
      "nutrition": {...},
      "exercise": {...}
    }
    """
    rows_nut = (
        session.query(db.DailyNutritionSummary)
        .filter(db.DailyNutritionSummary.user_id == user_id)
        .filter(db.DailyNutritionSummary.date >= start)
        .filter(db.DailyNutritionSummary.date <= end)
        .all()
    )
    rows_ex = (
        session.query(db.DailyExerciseSummary)
        .filter(db.DailyExerciseSummary.user_id == user_id)
        .filter(db.DailyExerciseSummary.date >= start)
        .filter(db.DailyExerciseSummary.date <= end)
        .all()
    )

    merged = {}

    for r in rows_nut:
        merged.setdefault(r.date, {})
        merged[r.date]["nutrition"] = {
            "kcal": r.kcal,
            "protein_g": r.protein_g,
            "fat_g": r.fat_g,
            "carb_g": r.carb_g,
            "processed_ratio": r.processed_ratio,
            "distinct_main_sources": r.distinct_main_sources,
        }

    for r in rows_ex:
        merged.setdefault(r.date, {})
        merged[r.date]["exercise"] = {
            "duration_min": r.duration_min,
            "calories_burned": r.calories_burned,
            "avg_intensity": r.avg_intensity,
        }

    return merged


# ----------------------------------------
# 공통 유틸: 라인 그래프(1~2개 라인)
# ----------------------------------------
def _plot_lines(x_labels, series_dict, title: str, xlabel: str, ylabel: str):
    """
    series_dict: { "label": [y1, y2, ...], ... }
    """
    plt.figure(figsize=(9, 5))

    for label, ys in series_dict.items():
        plt.plot(x_labels, ys, marker="o", label=label)

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


# ==========================================================
# 1️⃣ 이번 주(월~일) 일별 요약 JSON
# ==========================================================
@router.get("/analytics/daily/{user_id}", response_class=JSONResponse)
def get_week_daily_summary(user_id: str, session: Session = Depends(get_db)):
    """
    이번 주 월요일~일요일(7일)에 대해
    날짜별로 영양/운동을 분리한 요약을 JSON으로 반환.
    """
    today = date.today()
    monday = today - timedelta(days=today.weekday())  # 0: Monday
    sunday = monday + timedelta(days=6)

    merged = _get_merged_daily_summaries(session, user_id, monday, sunday)

    daily_list = []
    for i in range(7):
        d = monday + timedelta(days=i)
        day_data = merged.get(d, {})

        nutrition = day_data.get(
            "nutrition",
            {
                "kcal": 0,
                "protein_g": 0,
                "fat_g": 0,
                "carb_g": 0,
                "processed_ratio": 0,
                "distinct_main_sources": 0,
            },
        )
        exercise = day_data.get(
            "exercise",
            {
                "duration_min": 0,
                "calories_burned": 0,
                "avg_intensity": 0,
            },
        )

        daily_list.append(
            {
                "date": d.isoformat(),
                "nutrition": nutrition,
                "exercise": exercise,
            }
        )

    return JSONResponse(
        content={
            "user_id": user_id,
            "week_range": f"{monday.isoformat()} ~ {sunday.isoformat()}",
            "daily": daily_list,
        }
    )


# ==========================================================
# 2️⃣ 최근 4주 주간 평균 요약 JSON
# ==========================================================
@router.get("/analytics/weekly/{user_id}", response_class=JSONResponse)
def get_4weeks_summary(user_id: str, session: Session = Depends(get_db)):

    today = date.today()
    current_monday = today - timedelta(days=today.weekday())

    week_starts = [current_monday - timedelta(days=7 * i) for i in range(4)]
    week_starts.sort()

    weekly_summary = []

    for ws in week_starts:
        we = ws + timedelta(days=6)

        # 👇 여기서 “DB 캐싱 + 없으면 계산 + 저장” 적용됨
        result = get_or_compute_weekly_summary(session, user_id, ws, we)

        weekly_summary.append({
            "week_start": ws.isoformat(),
            "week_end": we.isoformat(),
            "nutrition_avg": result["nutrition"],
            "exercise_avg": result["exercise"]
        })

    return JSONResponse(content={
        "user_id": user_id,
        "weeks_count": len(weekly_summary),
        "weekly_summary": weekly_summary,
    })


# ==========================================================
# 3️⃣ 최근 3개월 월간 평균 요약 JSON
# ==========================================================
@router.get("/analytics/monthly/{user_id}", response_class=JSONResponse)
def get_3months_summary(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    this_month_start = today.replace(day=1)

    def prev_month_start(d: date) -> date:
        last_day_prev = d - timedelta(days=1)
        return last_day_prev.replace(day=1)

    # 최근 3개월 시작일 계산
    month_starts = [this_month_start]
    for _ in range(2):
        month_starts.append(prev_month_start(month_starts[-1]))
    month_starts.sort()

    results = []

    for ms in month_starts:
        next_month = (ms.replace(day=28) + timedelta(days=4)).replace(day=1)
        me = next_month - timedelta(days=1)
        month_str = ms.strftime("%Y-%m")

        # ---- DB 캐싱 체크 ----
        row_n = session.query(MonthlyNutritionSummary).filter(
            MonthlyNutritionSummary.user_id == user_id,
            MonthlyNutritionSummary.month == month_str
        ).first()

        row_e = session.query(MonthlyExerciseSummary).filter(
            MonthlyExerciseSummary.user_id == user_id,
            MonthlyExerciseSummary.month == month_str
        ).first()

        if row_n and row_e:
            # 저장된 데이터 이용
            results.append(
                {
                    "month": month_str,
                    "period": f"{ms.isoformat()} ~ {me.isoformat()}",
                    "nutrition_avg": {
                        "kcal": row_n.avg_kcal,
                        "protein_g": row_n.avg_protein,
                        "fat_g": row_n.avg_fat,
                        "carb_g": row_n.avg_carb,
                    },
                    "exercise_avg": {
                        "duration_min": row_e.avg_duration,
                        "calories_burned": row_e.avg_calories_burned,
                        "avg_intensity": row_e.avg_intensity,
                    }
                }
            )
            continue

        # ---- 저장된 데이터 없으면 계산 ----
        merged = _get_merged_daily_summaries(session, user_id, ms, me)

        nut_kcal, nut_prot, nut_fat, nut_carb = [], [], [], []
        ex_dur, ex_cal, ex_int = [], [], []

        for _, day_data in merged.items():
            nut = day_data.get("nutrition")
            ex = day_data.get("exercise")
            if nut:
                nut_kcal.append(nut.get("kcal", 0))
                nut_prot.append(nut.get("protein_g", 0))
                nut_fat.append(nut.get("fat_g", 0))
                nut_carb.append(nut.get("carb_g", 0))
            if ex:
                ex_dur.append(ex.get("duration_min", 0))
                ex_cal.append(ex.get("calories_burned", 0))
                ex_int.append(ex.get("avg_intensity", 0))

        def avg(lst): return sum(lst) / len(lst) if lst else 0

        # 계산 결과
        nut_result = {
            "kcal": round(avg(nut_kcal), 1),
            "protein": round(avg(nut_prot), 1),
            "fat": round(avg(nut_fat), 1),
            "carb": round(avg(nut_carb), 1),
        }

        ex_result = {
            "duration_min": round(avg(ex_dur), 1),
            "calories_burned": round(avg(ex_cal), 1),
            "avg_intensity": round(avg(ex_int), 2),
        }

        # ---- DB 저장 ----
        save_monthly_nutrition(session, user_id, month_str, nut_result)
        save_monthly_exercise(session, user_id, month_str, ex_result)

        # API 출력에 추가
        results.append(
            {
                "month": month_str,
                "period": f"{ms.isoformat()} ~ {me.isoformat()}",
                "nutrition_avg": nut_result,
                "exercise_avg": ex_result,
            }
        )

    return JSONResponse(
        content={
            "user_id": user_id,
            "months_count": len(results),
            "monthly_summary": results,
        }
    )


# ==========================================================
# 4️⃣ 운동만 그래프 (daily / weekly / monthly)
# ==========================================================

# 4-1) 이번 주 일별 운동 그래프
@router.get("/analytics/exercise/daily-graph/{user_id}")
def exercise_daily_graph(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    merged = _get_merged_daily_summaries(session, user_id, monday, sunday)

    x_labels = []
    kcal_out = []

    for i in range(7):
        d = monday + timedelta(days=i)
        day_data = merged.get(d, {})
        ex = day_data.get("exercise", {})

        x_labels.append(d.strftime("%m-%d"))
        kcal_out.append(ex.get("calories_burned", 0))

    buf = _plot_lines(
        x_labels,
        {
            "운동 소모 칼로리 (kcal)": kcal_out,
        },
        title=f"{user_id} — 이번 주(월~일) 운동 소모 칼로리",
        xlabel="날짜",
        ylabel="kcal",
    )
    return StreamingResponse(buf, media_type="image/png")


# 4-2) 최근 4주 주간 평균 운동 그래프
@router.get("/analytics/exercise/weekly-graph/{user_id}")
def exercise_weekly_graph(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    week_starts = [current_monday - timedelta(days=7 * i) for i in range(4)]
    week_starts.sort()

    labels = []
    kcal_out_avg = []

    for ws in week_starts:
        we = ws + timedelta(days=6)
        merged = _get_merged_daily_summaries(session, user_id, ws, we)

        wk_cal = []

        for i in range(7):
            d = ws + timedelta(days=i)
            day_data = merged.get(d, {})
            ex = day_data.get("exercise")
            if ex:
                wk_cal.append(ex.get("calories_burned", 0))

        if not wk_cal:
            continue

        def avg(lst):
            return sum(lst) / len(lst) if lst else 0

        labels.append(f"{ws.strftime('%m-%d')}~{we.strftime('%m-%d')}")
        kcal_out_avg.append(avg(wk_cal))

    if not labels:
        raise HTTPException(status_code=404, detail="No weekly exercise data")

    buf = _plot_lines(
        labels,
        {
            "주간 평균 운동 소모 칼로리 (kcal)": kcal_out_avg,
        },
        title=f"{user_id} — 최근 4주 운동 소모 칼로리 평균",
        xlabel="주(기간)",
        ylabel="kcal",
    )
    return StreamingResponse(buf, media_type="image/png")



# 4-3) 최근 3개월 월간 평균 운동 그래프
@router.get("/analytics/exercise/monthly-graph/{user_id}")
def exercise_monthly_graph(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    this_month_start = today.replace(day=1)

    def prev_month_start(d: date) -> date:
        last_day_prev = d - timedelta(days=1)
        return last_day_prev.replace(day=1)

    month_starts = [this_month_start]
    for _ in range(2):
        month_starts.append(prev_month_start(month_starts[-1]))
    month_starts.sort()

    labels = []
    kcal_out_avg = []

    for ms in month_starts:
        next_month = (ms.replace(day=28) + timedelta(days=4)).replace(day=1)
        me = next_month - timedelta(days=1)

        merged = _get_merged_daily_summaries(session, user_id, ms, me)

        m_cal = []
        for d, day_data in merged.items():
            if not (ms <= d <= me):
                continue
            ex = day_data.get("exercise")
            if ex:
                m_cal.append(ex.get("calories_burned", 0))

        if not m_cal:
            continue

        def avg(lst):
            return sum(lst) / len(lst) if lst else 0

        labels.append(ms.strftime("%Y-%m"))
        kcal_out_avg.append(avg(m_cal))

    if not labels:
        raise HTTPException(status_code=404, detail="No monthly exercise data")

    buf = _plot_lines(
        labels,
        {
            "월간 평균 운동 소모 칼로리 (kcal)": kcal_out_avg,
        },
        title=f"{user_id} — 최근 3개월 운동 소모 칼로리 평균",
        xlabel="월",
        ylabel="kcal",
    )
    return StreamingResponse(buf, media_type="image/png")


# ==========================================================
# 5️⃣ 식단(칼로리만) 그래프 (daily / weekly / monthly)
# ==========================================================

# 5-1) 이번 주 일별 섭취 칼로리 그래프
@router.get("/analytics/nutrition/daily-graph/{user_id}")
def nutrition_daily_graph(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    merged = _get_merged_daily_summaries(session, user_id, monday, sunday)

    x_labels = []
    kcal_in = []

    for i in range(7):
        d = monday + timedelta(days=i)
        day_data = merged.get(d, {})
        nut = day_data.get("nutrition", {})
        x_labels.append(d.strftime("%m-%d"))
        kcal_in.append(nut.get("kcal", 0))

    buf = _plot_lines(
        x_labels,
        {
            "섭취 칼로리 (kcal)": kcal_in,
        },
        title=f"{user_id} — 이번 주(월~일) 섭취 칼로리",
        xlabel="날짜",
        ylabel="kcal",
    )
    return StreamingResponse(buf, media_type="image/png")


# 5-2) 최근 4주 주간 평균 섭취 칼로리 그래프
@router.get("/analytics/nutrition/weekly-graph/{user_id}")
def nutrition_weekly_graph(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    week_starts = [current_monday - timedelta(days=7 * i) for i in range(4)]
    week_starts.sort()

    labels = []
    kcal_avg = []

    for ws in week_starts:
        we = ws + timedelta(days=6)
        merged = _get_merged_daily_summaries(session, user_id, ws, we)

        wk_kcal = []
        for i in range(7):
            d = ws + timedelta(days=i)
            day_data = merged.get(d, {})
            nut = day_data.get("nutrition")
            if nut:
                wk_kcal.append(nut.get("kcal", 0))

        if not wk_kcal:
            continue

        def avg(lst):
            return sum(lst) / len(lst) if lst else 0

        labels.append(f"{ws.strftime('%m-%d')}~{we.strftime('%m-%d')}")
        kcal_avg.append(avg(wk_kcal))

    if not labels:
        raise HTTPException(status_code=404, detail="No weekly nutrition data")

    buf = _plot_lines(
        labels,
        {
            "주간 평균 섭취 칼로리 (kcal)": kcal_avg,
        },
        title=f"{user_id} — 최근 4주 섭취 칼로리 평균",
        xlabel="주(기간)",
        ylabel="kcal",
    )
    return StreamingResponse(buf, media_type="image/png")


# 5-3) 최근 3개월 월간 평균 섭취 칼로리 그래프
@router.get("/analytics/nutrition/monthly-graph/{user_id}")
def nutrition_monthly_graph(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    this_month_start = today.replace(day=1)

    def prev_month_start(d: date) -> date:
        last_day_prev = d - timedelta(days=1)
        return last_day_prev.replace(day=1)

    month_starts = [this_month_start]
    for _ in range(2):
        month_starts.append(prev_month_start(month_starts[-1]))
    month_starts.sort()

    labels = []
    kcal_avg = []

    for ms in month_starts:
        next_month = (ms.replace(day=28) + timedelta(days=4)).replace(day=1)
        me = next_month - timedelta(days=1)

        merged = _get_merged_daily_summaries(session, user_id, ms, me)

        m_kcal = []
        for d, day_data in merged.items():
            if not (ms <= d <= me):
                continue
            nut = day_data.get("nutrition")
            if nut:
                m_kcal.append(nut.get("kcal", 0))

        if not m_kcal:
            continue

        def avg(lst):
            return sum(lst) / len(lst) if lst else 0

        labels.append(ms.strftime("%Y-%m"))
        kcal_avg.append(avg(m_kcal))

    if not labels:
        raise HTTPException(status_code=404, detail="No monthly nutrition data")

    buf = _plot_lines(
        labels,
        {
            "월간 평균 섭취 칼로리 (kcal)": kcal_avg,
        },
        title=f"{user_id} — 최근 3개월 섭취 칼로리 평균",
        xlabel="월",
        ylabel="kcal",
    )
    return StreamingResponse(buf, media_type="image/png")


# ==========================================================
# 6️⃣ 영양 4종 그래프 (kcal, 탄/단/지) — daily / weekly / monthly
# ==========================================================

# 6-1) 이번 주 일별 영양 4종 그래프
@router.get("/analytics/nutrition4/daily-graph/{user_id}")
def nutrition4_daily_graph(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    merged = _get_merged_daily_summaries(session, user_id, monday, sunday)

    x_labels = []
    kcal = []
    protein = []
    fat = []
    carb = []

    for i in range(7):
        d = monday + timedelta(days=i)
        day_data = merged.get(d, {})
        nut = day_data.get("nutrition", {})

        x_labels.append(d.strftime("%m-%d"))
        kcal.append(nut.get("kcal", 0))
        protein.append(nut.get("protein_g", 0))
        fat.append(nut.get("fat_g", 0))
        carb.append(nut.get("carb_g", 0))

    buf = _plot_lines(
        x_labels,
        {
            "칼로리 (kcal)": kcal,
            "단백질 (g)": protein,
            "지방 (g)": fat,
            "탄수화물 (g)": carb,
        },
        title=f"{user_id} — 이번 주(월~일) 영양 4종 트렌드",
        xlabel="날짜",
        ylabel="값 (kcal / g)",
    )
    return StreamingResponse(buf, media_type="image/png")


# 6-2) 최근 4주 영양 4종 주간 평균 그래프
@router.get("/analytics/nutrition4/weekly-graph/{user_id}")
def nutrition4_weekly_graph(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    week_starts = [current_monday - timedelta(days=7 * i) for i in range(4)]
    week_starts.sort()

    labels = []
    kcal_avg = []
    protein_avg = []
    fat_avg = []
    carb_avg = []

    for ws in week_starts:
        we = ws + timedelta(days=6)
        merged = _get_merged_daily_summaries(session, user_id, ws, we)

        wk_kcal = []
        wk_prot = []
        wk_fat = []
        wk_carb = []

        for i in range(7):
            d = ws + timedelta(days=i)
            day_data = merged.get(d, {})
            nut = day_data.get("nutrition")
            if nut:
                wk_kcal.append(nut.get("kcal", 0))
                wk_prot.append(nut.get("protein_g", 0))
                wk_fat.append(nut.get("fat_g", 0))
                wk_carb.append(nut.get("carb_g", 0))

        if not wk_kcal and not wk_prot and not wk_fat and not wk_carb:
            continue

        def avg(lst):
            return sum(lst) / len(lst) if lst else 0

        labels.append(f"{ws.strftime('%m-%d')}~{we.strftime('%m-%d')}")
        kcal_avg.append(avg(wk_kcal))
        protein_avg.append(avg(wk_prot))
        fat_avg.append(avg(wk_fat))
        carb_avg.append(avg(wk_carb))

    if not labels:
        raise HTTPException(status_code=404, detail="No weekly nutrition data")

    buf = _plot_lines(
        labels,
        {
            "칼로리 (kcal)": kcal_avg,
            "단백질 (g)": protein_avg,
            "지방 (g)": fat_avg,
            "탄수화물 (g)": carb_avg,
        },
        title=f"{user_id} — 최근 4주 영양 4종 평균",
        xlabel="주(기간)",
        ylabel="값 (kcal / g)",
    )
    return StreamingResponse(buf, media_type="image/png")


# 6-3) 최근 3개월 영양 4종 월간 평균 그래프
@router.get("/analytics/nutrition4/monthly-graph/{user_id}")
def nutrition4_monthly_graph(user_id: str, session: Session = Depends(get_db)):
    today = date.today()
    this_month_start = today.replace(day=1)

    def prev_month_start(d: date) -> date:
        last_day_prev = d - timedelta(days=1)
        return last_day_prev.replace(day=1)

    month_starts = [this_month_start]
    for _ in range(2):
        month_starts.append(prev_month_start(month_starts[-1]))
    month_starts.sort()

    labels = []
    kcal_avg = []
    protein_avg = []
    fat_avg = []
    carb_avg = []

    for ms in month_starts:
        next_month = (ms.replace(day=28) + timedelta(days=4)).replace(day=1)
        me = next_month - timedelta(days=1)

        merged = _get_merged_daily_summaries(session, user_id, ms, me)

        m_kcal = []
        m_prot = []
        m_fat = []
        m_carb = []

        for d, day_data in merged.items():
            if not (ms <= d <= me):
                continue
            nut = day_data.get("nutrition")
            if nut:
                m_kcal.append(nut.get("kcal", 0))
                m_prot.append(nut.get("protein_g", 0))
                m_fat.append(nut.get("fat_g", 0))
                m_carb.append(nut.get("carb_g", 0))

        if not m_kcal and not m_prot and not m_fat and not m_carb:
            continue

        def avg(lst):
            return sum(lst) / len(lst) if lst else 0

        labels.append(ms.strftime("%Y-%m"))
        kcal_avg.append(avg(m_kcal))
        protein_avg.append(avg(m_prot))
        fat_avg.append(avg(m_fat))
        carb_avg.append(avg(m_carb))

    if not labels:
        raise HTTPException(status_code=404, detail="No monthly nutrition data")

    buf = _plot_lines(
        labels,
        {
            "칼로리 (kcal)": kcal_avg,
            "단백질 (g)": protein_avg,
            "지방 (g)": fat_avg,
            "탄수화물 (g)": carb_avg,
        },
        title=f"{user_id} — 최근 3개월 영양 4종 평균",
        xlabel="월",
        ylabel="값 (kcal / g)",
    )
    return StreamingResponse(buf, media_type="image/png")


@router.get("/analytics/period/{user_id}", response_class=JSONResponse)
def get_period_summary(
    user_id: str,
    start_date: date = Query(..., description="YYYY-MM-DD"),
    end_date: date = Query(..., description="YYYY-MM-DD"),
    session: Session = Depends(get_db),
):
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")

    merged = _get_merged_daily_summaries(session, user_id, start_date, end_date)

    results = []
    for d in sorted(merged.keys()):
        results.append({
            "date": d.isoformat(),
            "nutrition": merged[d].get("nutrition", {}),
            "exercise": merged[d].get("exercise", {}),
        })

    return JSONResponse(
        content={
            "user_id": user_id,
            "range": f"{start_date.isoformat()} ~ {end_date.isoformat()}",
            "days": results,
        }
    )

@router.get("/analytics/custom/weekly/{user_id}", response_class=JSONResponse)
def get_custom_weeks(
    user_id: str,
    weeks: int = Query(4, ge=1, le=52),
    session: Session = Depends(get_db),
):
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())

    week_starts = [current_monday - timedelta(days=7 * i) for i in range(weeks)]
    week_starts.sort()

    summaries = []

    for ws in week_starts:
        we = ws + timedelta(days=6)
        result = get_or_compute_weekly_summary(session, user_id, ws, we)

        summaries.append({
            "week_start": ws.isoformat(),
            "week_end": we.isoformat(),
            "nutrition_avg": result["nutrition"],
            "exercise_avg": result["exercise"]
        })

    return JSONResponse(
        content={
            "user_id": user_id,
            "weeks_requested": weeks,
            "weekly_summary": summaries
        }
    )


@router.get("/analytics/custom/monthly/{user_id}", response_class=JSONResponse)
def get_custom_months(
    user_id: str,
    months: int = Query(3, ge=1, le=24),
    session: Session = Depends(get_db)
):
    today = date.today()
    this_month_start = today.replace(day=1)

    def prev_month_start(d):
        last = d - timedelta(days=1)
        return last.replace(day=1)

    month_starts = [this_month_start]
    for _ in range(months - 1):
        month_starts.append(prev_month_start(month_starts[-1]))

    month_starts.sort()

    results = []

    for ms in month_starts:
        next_month = (ms.replace(day=28) + timedelta(days=4)).replace(day=1)
        me = next_month - timedelta(days=1)
        month_str = ms.strftime("%Y-%m")

        # 캐싱 체크
        row_n = session.query(MonthlyNutritionSummary).filter(
            MonthlyNutritionSummary.user_id == user_id,
            MonthlyNutritionSummary.month == month_str
        ).first()

        row_e = session.query(MonthlyExerciseSummary).filter(
            MonthlyExerciseSummary.user_id == user_id,
            MonthlyExerciseSummary.month == month_str
        ).first()

        if row_n and row_e:
            nut = {
                "kcal": row_n.avg_kcal,
                "protein": row_n.avg_protein,
                "fat": row_n.avg_fat,
                "carb": row_n.avg_carb,
            }
            ex = {
                "duration_min": row_e.avg_duration,
                "calories_burned": row_e.avg_calories_burned,
                "avg_intensity": row_e.avg_intensity,
            }
        else:
            merged = _get_merged_daily_summaries(session, user_id, ms, me)

            nut_kcal, nut_prot, nut_fat, nut_carb = [], [], [], []
            ex_dur, ex_cal, ex_int = [], [], []

            for _, day_data in merged.items():
                nut = day_data.get("nutrition")
                ex = day_data.get("exercise")
                if nut:
                    nut_kcal.append(nut.get("kcal", 0))
                    nut_prot.append(nut.get("protein_g", 0))
                    nut_fat.append(nut.get("fat_g", 0))
                    nut_carb.append(nut.get("carb_g", 0))
                if ex:
                    ex_dur.append(ex.get("duration_min", 0))
                    ex_cal.append(ex.get("calories_burned", 0))
                    ex_int.append(ex.get("avg_intensity", 0))

            def avg(lst): return sum(lst) / len(lst) if lst else 0

            nut = {
                "kcal": avg(nut_kcal),
                "protein": avg(nut_prot),
                "fat": avg(nut_fat),
                "carb": avg(nut_carb),
            }
            ex = {
                "duration_min": avg(ex_dur),
                "calories_burned": avg(ex_cal),
                "avg_intensity": avg(ex_int),
            }

            save_monthly_nutrition(session, user_id, month_str, nut)
            save_monthly_exercise(session, user_id, month_str, ex)

        results.append({
            "month": month_str,
            "nutrition_avg": nut,
            "exercise_avg": ex,
        })

    return JSONResponse(
        content={
            "user_id": user_id,
            "months_requested": months,
            "monthly_summary": results
        }
    )


@router.get("/analytics/custom/weekly-graph/nutrition/{user_id}")
def custom_weekly_graph_nutrition(
    user_id: str, 
    weeks: int = Query(4, ge=1, le=52),
    session: Session = Depends(get_db),
):
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())

    week_starts = [current_monday - timedelta(days=7 * i) for i in range(weeks)]
    week_starts.sort()

    labels, kcal_avg, protein_avg, fat_avg, carb_avg = [], [], [], [], []

    for ws in week_starts:
        we = ws + timedelta(days=6)

        result = get_or_compute_weekly_summary(session, user_id, ws, we)
        nut = result.get("nutrition", {})

        labels.append(ws.strftime("%m-%d"))
        kcal_avg.append(nut.get("kcal", 0))
        protein_avg.append(nut.get("protein", 0))
        fat_avg.append(nut.get("fat", 0))
        carb_avg.append(nut.get("carb", 0))

    buf = _plot_lines(
        labels,
        {
            "칼로리(kcal)": kcal_avg,
            "단백질(g)": protein_avg,
            "지방(g)": fat_avg,
            "탄수화물(g)": carb_avg,
        },
        title=f"{user_id} — 최근 {weeks}주 영양 평균",
        xlabel="주 시작일",
        ylabel="값 (kcal / g)",
    )
    return StreamingResponse(buf, media_type="image/png")


@router.get("/analytics/custom/weekly-graph/exercise/{user_id}")
def custom_weekly_graph_exercise(
    user_id: str, 
    weeks: int = Query(4, ge=1, le=52),
    session: Session = Depends(get_db),
):
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())

    week_starts = [current_monday - timedelta(days=7 * i) for i in range(weeks)]
    week_starts.sort()

    labels, duration_avg, kcal_out_avg, intensity_avg = [], [], [], []

    for ws in week_starts:
        we = ws + timedelta(days=6)

        result = get_or_compute_weekly_summary(session, user_id, ws, we)
        ex = result.get("exercise", {})

        labels.append(ws.strftime("%m-%d"))
        duration_avg.append(ex.get("duration_min", 0))
        kcal_out_avg.append(ex.get("calories_burned", 0))
        intensity_avg.append(ex.get("avg_intensity", 0))

    buf = _plot_lines(
        labels,
        {
            "운동시간(min)": duration_avg,
            "운동소모칼로리(kcal)": kcal_out_avg,
            "운동강도(score)": intensity_avg,
        },
        title=f"{user_id} — 최근 {weeks}주 운동 평균",
        xlabel="주 시작일",
        ylabel="값",
    )
    return StreamingResponse(buf, media_type="image/png")


@router.get("/analytics/custom/monthly-graph/nutrition/{user_id}")
def custom_monthly_graph_nutrition(
    user_id: str,
    months: int = Query(3, ge=1, le=24),
    session: Session = Depends(get_db),
):
    results = get_custom_months(user_id, months, session).body["monthly_summary"]

    labels = []
    kcal_avg = []
    protein_avg = []
    fat_avg = []
    carb_avg = []

    for row in results:
        labels.append(row["month"])
        nut = row["nutrition_avg"]
        kcal_avg.append(nut.get("kcal", 0))
        protein_avg.append(nut.get("protein", 0))
        fat_avg.append(nut.get("fat", 0))
        carb_avg.append(nut.get("carb", 0))

    buf = _plot_lines(
        labels,
        {
            "칼로리(kcal)": kcal_avg,
            "단백질(g)": protein_avg,
            "지방(g)": fat_avg,
            "탄수화물(g)": carb_avg,
        },
        title=f"{user_id} — 최근 {months}개월 영양 평균",
        xlabel="월",
        ylabel="값 (kcal / g)",
    )
    return StreamingResponse(buf, media_type="image/png")


@router.get("/analytics/custom/monthly-graph/exercise/{user_id}")
def custom_monthly_graph_exercise(
    user_id: str,
    months: int = Query(3, ge=1, le=24),
    session: Session = Depends(get_db),
):
    results = get_custom_months(user_id, months, session).body["monthly_summary"]

    labels = []
    duration_avg = []
    kcal_out_avg = []
    intensity_avg = []

    for row in results:
        labels.append(row["month"])
        ex = row["exercise_avg"]
        duration_avg.append(ex.get("duration_min", 0))
        kcal_out_avg.append(ex.get("calories_burned", 0))
        intensity_avg.append(ex.get("avg_intensity", 0))

    buf = _plot_lines(
        labels,
        {
            "운동시간(min)": duration_avg,
            "운동소모칼로리(kcal)": kcal_out_avg,
            "운동강도(score)": intensity_avg,
        },
        title=f"{user_id} — 최근 {months}개월 운동 평균",
        xlabel="월",
        ylabel="값",
    )
    return StreamingResponse(buf, media_type="image/png")


@router.get("/analytics/custom/period-graph/nutrition/{user_id}")
def custom_period_graph_nutrition(
    user_id: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    session: Session = Depends(get_db)
):
    merged = _get_merged_daily_summaries(session, user_id, start_date, end_date)

    labels, kcal, protein, fat, carb = [], [], [], [], []

    for d in sorted(merged.keys()):
        nut = merged[d].get("nutrition", {})
        labels.append(d.strftime("%m-%d"))
        kcal.append(nut.get("kcal", 0))
        protein.append(nut.get("protein_g", 0))
        fat.append(nut.get("fat_g", 0))
        carb.append(nut.get("carb_g", 0))

    buf = _plot_lines(
        labels,
        {
            "칼로리(kcal)": kcal,
            "단백질(g)": protein,
            "지방(g)": fat,
            "탄수화물(g)": carb,
        },
        title=f"{user_id} — {start_date} ~ {end_date} 영양 트렌드",
        xlabel="날짜",
        ylabel="값 (kcal / g)",
    )
    return StreamingResponse(buf, media_type="image/png")


@router.get("/analytics/custom/period-graph/exercise/{user_id}")
def custom_period_graph_exercise(
    user_id: str,
    start_date: date = Query(...),
    end_date: date = Query(...),
    session: Session = Depends(get_db)
):
    merged = _get_merged_daily_summaries(session, user_id, start_date, end_date)

    labels, duration, kcal_out, intensity = [], [], [], []

    for d in sorted(merged.keys()):
        ex = merged[d].get("exercise", {})
        labels.append(d.strftime("%m-%d"))
        duration.append(ex.get("duration_min", 0))
        kcal_out.append(ex.get("calories_burned", 0))
        intensity.append(ex.get("avg_intensity", 0))

    buf = _plot_lines(
        labels,
        {
            "운동시간(min)": duration,
            "운동소모칼로리(kcal)": kcal_out,
            "운동강도(score)": intensity,
        },
        title=f"{user_id} — {start_date} ~ {end_date} 운동 트렌드",
        xlabel="날짜",
        ylabel="값",
    )
    return StreamingResponse(buf, media_type="image/png")

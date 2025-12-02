from apscheduler.schedulers.background import BackgroundScheduler
from datetime import date, timedelta
from sqlalchemy.orm import Session
from src import db

from src.services.summary_storage import (
    save_weekly_nutrition,
    save_weekly_exercise,
    save_monthly_nutrition,
    save_monthly_exercise
)

from src.routers.analytics import compute_week_data, _get_merged_daily_summaries


# =========================================
# ⚡ 기존 함수 이름 유지 + 내부 확장 (Backfill 처리)
# =========================================

def compute_previous_week_summaries(max_weeks: int = 52):
    """
    기존 함수 이름 유지:
    - 기존 "지난 주만 계산" → 개선: 최근 max_weeks 기간 중 누락된 주 summary 생성
    """
    session: Session = db.SessionLocal()

    today = date.today()
    current_monday = today - timedelta(days=today.weekday())  # 이번 주 월요일

    print(f"[Scheduler] Weekly summary backfill check (max {max_weeks} weeks)")

    users = session.query(db.User.id).all()

    for (user_id,) in users:

        for w in range(1, max_weeks + 1):
            ws = current_monday - timedelta(days=7 * w)
            we = ws + timedelta(days=6)

            exists = session.query(db.WeeklyNutritionSummary).filter(
                db.WeeklyNutritionSummary.user_id == user_id,
                db.WeeklyNutritionSummary.week_start == ws
            ).first()

            if exists:
                continue  # 이미 저장됨 — skip

            print(f"[Scheduler] (weekly) computing {user_id} — {ws} ~ {we}")

            merged = _get_merged_daily_summaries(session, user_id, ws, we)
            nut, ex = compute_week_data(session, user_id, ws, we)

            save_weekly_nutrition(session, user_id, ws, we, nut)
            save_weekly_exercise(session, user_id, ws, we, ex)

    session.close()
    print("[Scheduler] Weekly backfill done")


def compute_previous_month_summaries(max_months: int = 12):
    """
    기존 함수 이름 유지:
    - 기존 "지난달 1개만 생성" → 개선: 최근 max_months 기간 중 누락된 달 summary 생성
    """
    session: Session = db.SessionLocal()

    today = date.today()
    first_day_this_month = today.replace(day=1)

    print(f"[Scheduler] Monthly summary backfill check (max {max_months} months)")

    users = session.query(db.User.id).all()

    for (user_id,) in users:
        ms = first_day_this_month  # 기준값(이번 달)

        for _ in range(1, max_months + 1):
            last_day_prev = ms - timedelta(days=1)
            month_key = last_day_prev.strftime("%Y-%m")

            exists = session.query(db.MonthlyNutritionSummary).filter(
                db.MonthlyNutritionSummary.user_id == user_id,
                db.MonthlyNutritionSummary.month == month_key
            ).first()

            if exists:
                # 한 달 뒤로 이동만
                ms = last_day_prev.replace(day=1)
                continue

            print(f"[Scheduler] (monthly) computing {user_id} — {month_key}")

            # 요약 계산 범위
            start = last_day_prev.replace(day=1)
            end = last_day_prev

            merged = _get_merged_daily_summaries(session, user_id, start, end)

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

            save_monthly_nutrition(session, user_id, month_key, nut)
            save_monthly_exercise(session, user_id, month_key, ex)

            ms = last_day_prev.replace(day=1)

    session.close()
    print("[Scheduler] Monthly backfill done")


# =========================================
# ⚡ Scheduler 실행부
# =========================================

def start_scheduler():
    scheduler = BackgroundScheduler()

    # 매일 새벽 — 최근 52주 누락 summary 자동 보완
    scheduler.add_job(
        compute_previous_week_summaries,
        "cron",
        hour=3, minute=0
    )

    # 매월 1일 새벽 — 최근 12개월 누락 summary 자동 보완
    scheduler.add_job(
        compute_previous_month_summaries,
        "cron",
        day=1,
        hour=3, minute=30
    )

    scheduler.start()
    print("[Scheduler] Started background scheduler (smart backfill enabled)")

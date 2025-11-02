# src/services/coach.py
from sqlalchemy.orm import Session
from datetime import date, timedelta
from src import db
import statistics

def build_weekly_coach_report(user_id: str, session: Session):
    """최근 7일간 요약 데이터를 기반으로 코치 피드백을 생성."""
    
    today = date.today()
    start = today - timedelta(days=6)

    # ✅ 건강 점수 가져오기 (DailyHealthScore 기반)
    all_scores = (
        session.query(db.DailyHealthScore)
        .filter(db.DailyHealthScore.user_id == user_id)
        .order_by(db.DailyHealthScore.date)
        .all()
    )

    weekly_scores = [s for s in all_scores if s.date >= start]
    if weekly_scores:
        avg_score = round(sum(s.total_score for s in weekly_scores) / len(weekly_scores), 1)
        prev_scores = all_scores[:-len(weekly_scores)]
        prev_avg = round(sum(s.total_score for s in prev_scores[-7:]) / max(1, len(prev_scores[-7:])), 1)
        delta = avg_score - prev_avg
        trend = "상승 " if delta > 0 else ("하락 " if delta < 0 else "유지 ➖")
        summary_prefix = f"이번 주 전체 건강 점수는 **{avg_score}점**입니다 ({trend}, 지난주 대비 {delta:+.1f})."
    else:
        summary_prefix = "이번 주 점수 데이터를 불러올 수 없습니다."
        avg_score, delta = None, 0

    # 최근 7일 데이터 로드
    nuts = (
        session.query(db.DailyNutritionSummary)
        .filter(db.DailyNutritionSummary.user_id == user_id)
        .filter(db.DailyNutritionSummary.date >= start)
        .order_by(db.DailyNutritionSummary.date)
        .all()
    )
    exes = (
        session.query(db.DailyExerciseSummary)
        .filter(db.DailyExerciseSummary.user_id == user_id)
        .filter(db.DailyExerciseSummary.date >= start)
        .order_by(db.DailyExerciseSummary.date)
        .all()
    )

    if not nuts and not exes:
        return {"summary": "최근 7일 간 데이터가 부족합니다.", "action_items": [], "motivation": "꾸준한 기록이 첫 걸음이에요!"}

    # -------------------------------
    # 기본 통계 계산
    # -------------------------------
    kcal_avg = statistics.mean([n.kcal for n in nuts]) if nuts else 0
    prot_avg = statistics.mean([n.protein_g for n in nuts]) if nuts else 0
    fat_avg  = statistics.mean([n.fat_g for n in nuts]) if nuts else 0
    carb_avg = statistics.mean([n.carb_g for n in nuts]) if nuts else 0
    sodium_avg = statistics.mean([n.sodium_mg for n in nuts]) if nuts else 0
    proc_ratio = statistics.mean([n.processed_ratio for n in nuts]) if nuts else 0

    ex_days = len([e for e in exes if e.duration_min > 0])
    avg_ex_dur = statistics.mean([e.duration_min for e in exes]) if exes else 0
    avg_ex_int = statistics.mean([e.avg_intensity for e in exes]) if exes else 0
    avg_burned = statistics.mean([e.calories_burned for e in exes]) if exes else 0

    # -------------------------------
    # 규칙 기반 피드백 생성
    # -------------------------------
    summary_parts = []
    actions = []

    # 운동 빈도
    if ex_days >= 5:
        summary_parts.append(f"운동 빈도가 높아요({ex_days}일). 좋은 루틴을 유지하고 있어요!")
    elif ex_days >= 3:
        summary_parts.append(f"운동을 주 {ex_days}일 했어요. 꾸준하지만 조금 더 자주 하면 좋아요.")
        actions.append("주 4~5회로 빈도를 늘려보세요. 하루는 코어, 하루는 전신 등 분할 추천.")
    else:
        summary_parts.append(f"운동이 주 {ex_days}일로 다소 적어요.")
        actions.append("주 3회 이상을 목표로 해보세요. 짧게라도 규칙적인 루틴이 중요해요.")

    # 식단 밸런스
    if prot_avg < 1.5 * (avg_burned / 100) and prot_avg < 80:
        summary_parts.append(f"단백질 섭취가 다소 낮아요 (평균 {prot_avg:.0f}g).")
        actions.append("매 끼니마다 단백질 식품(닭가슴살, 달걀, 두부, 그릭요거트)을 포함해보세요.")
    else:
        summary_parts.append(f"단백질 섭취가 적절해요 ({prot_avg:.0f}g/일).")

    # 초가공 비중
    if proc_ratio > 0.3:
        summary_parts.append("초가공식품 비중이 높아요.")
        actions.append("즉석식품·소스류 대신 직접 조리 음식을 늘려보세요.")
    else:
        summary_parts.append("가공식품 섭취 비중이 낮아 식단의 질이 좋아요!")

    # 나트륨
    if sodium_avg > 2300:
        summary_parts.append(f"평균 나트륨 섭취가 {sodium_avg:.0f}mg로 높아요.")
        actions.append("국물류·가공육 섭취를 줄이고 물을 충분히 섭취하세요.")
    else:
        summary_parts.append(f"나트륨 섭취가 안정적이에요 ({sodium_avg:.0f}mg).")

    # 칼로리 밸런스
    kcal_balance = kcal_avg - avg_burned
    if kcal_balance > 300:
        summary_parts.append("섭취 칼로리가 소비보다 많아요. 체중 증가 가능성이 있어요.")
        actions.append("간식이나 음료 칼로리를 조정해보세요.")
    elif kcal_balance < -300:
        summary_parts.append("섭취 칼로리가 소비보다 적어요. 피로감이 올 수 있어요.")
        actions.append("균형을 위해 식사량을 조금 늘리세요.")
    else:
        summary_parts.append("칼로리 밸런스가 안정적이에요.")

    # 동기부여 메시지
    if ex_days >= 4 and proc_ratio < 0.25:
        motivation = "식단과 운동 균형이 잘 잡혀가고 있어요! 지금처럼 꾸준히 가면 변화가 곧 눈에 보여요 "
    elif ex_days < 3:
        motivation = "작은 루틴부터 다시 만들어봐요. 10분이라도 시작이 중요해요 🌱"
    else:
        motivation = "지속적인 관리가 핵심이에요. 어제보다 1% 나은 하루를 만들어봐요!"

    summary_text = " ".join(summary_parts)

    return {
        "summary": summary_prefix + " " + summary_text,
        "metrics": {
            "avg_kcal": round(kcal_avg, 1),
            "avg_protein": round(prot_avg, 1),
            "avg_fat": round(fat_avg, 1),
            "avg_carb": round(carb_avg, 1),
            "avg_sodium_mg": round(sodium_avg, 1),
            "processed_ratio": round(proc_ratio, 2),
            "exercise_days": ex_days,
            "avg_ex_duration": round(avg_ex_dur, 1),
            "avg_ex_intensity": round(avg_ex_int, 1),
            "avg_burned": round(avg_burned, 1),
            "health_score": avg_score,
            "score_trend_delta": delta
        },
        "action_items": actions,
        "motivation": motivation
    }
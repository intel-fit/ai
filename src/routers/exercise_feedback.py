from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from src import db
from src.schemas import ExerciseSessionInput
import json
import uuid

router = APIRouter(tags=["Exercise Feedback"])


def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.post("/exercise/feedback")
def submit_exercise_feedback(body: ExerciseSessionInput, session: Session = Depends(get_db)):

    # -----------------------------
    # 유저 확인
    # -----------------------------
    user = session.query(db.User).filter(db.User.id == body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # -----------------------------
    # 세션 생성
    # -----------------------------
    sess = db.ExerciseSession(
        user_id=body.user_id,
        session_name=body.session_name,
        duration_min=body.duration_min,
        intensity_score=body.intensity,
        feedback=body.feedback  # 세션 전체의 느낌(사용한다면)
    )
    session.add(sess)
    session.commit()
    session.refresh(sess)

    # -----------------------------
    # 아이템 + 피드백 저장
    # -----------------------------
    for item in body.items:

        # 운동 아이템 저장
        item_row = db.ExerciseSessionItem(
            id=str(uuid.uuid4()),
            session_id=sess.id,
            exercise_id=item.exercise_id,
            exercise_name=item.name,
            weight_kg=item.weight,
            reps=item.reps,
            sets=item.sets,
            warmup_json=json.dumps(item.warmup or [], ensure_ascii=False),
        )
        session.add(item_row)
        session.flush()  # item_row.id 확보

        # 🔥 피드백이 없는 경우 "중립" → feedback 저장 X
        if not item.feedback:
            continue

        # -----------------------------
        # 개별 운동 피드백 저장
        # -----------------------------
        for fb in item.feedback:
            fb_row = db.ExerciseFeedback(
                user_id=body.user_id,
                exercise_id=item.exercise_id,
                exercise_name=item.name,
                feedback_type=fb,  # "like" | "heavy" | ...
                weight_kg=item.weight,
            )
            session.add(fb_row)

    session.commit()

    return {
        "status": "success",
        "session_id": sess.id,
        "message": "운동 세션 + 개별 피드백 저장 완료"
    }

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

    user = session.query(db.User).filter(db.User.id == body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sess = db.ExerciseSession(
        user_id=body.user_id,
        session_name=body.session_name,
        duration_min=body.duration_min,
        intensity_score=body.intensity,
        feedback=body.feedback
    )
    session.add(sess)
    session.commit()
    session.refresh(sess)

    # --------------------------------------
    # ⭐ Option B: 운동 ID 포함해서 저장
    # --------------------------------------
    for item in body.items:
        row = db.ExerciseSessionItem(
            id=str(uuid.uuid4()),
            session_id=sess.id,
            exercise_id=item.exercise_id,     # ← 추가됨
            exercise_name=item.name,
            weight_kg=item.weight,
            reps=item.reps,
            sets=item.sets,
            warmup_json=json.dumps(item.warmup, ensure_ascii=False)
        )
        session.add(row)

    session.commit()

    return {
        "status": "success",
        "session_id": sess.id,
        "message": "운동 세션 피드백이 저장되었습니다."
    }

from src import db
from sqlalchemy.orm import Session
import random
from datetime import datetime, timedelta

def seed_fake_data():
    SessionLocal = db.SessionLocal
    session: Session = SessionLocal()

    # 20 fake session 생성
    for _ in range(20):
        s = db.ExerciseSession(
            user_id="test_user",
            date=datetime.utcnow().date(),
            session_name="fake_session",
            duration_min=random.randint(30, 80),
            intensity_score=random.random(),
            feedback=random.choice(["like", "dislike", "neutral"])
        )
        session.add(s)
        session.flush()  # 🔥 Sessions.id 확보

        # Fake Exercise Items 생성 (1~4개)
        for _ in range(random.randint(1, 4)):
            item = db.ExerciseSessionItem(
                session_id=s.id,
                exercise_id=str(random.randint(1, 200)),
                exercise_name=f"Exercise {random.randint(1,200)}",
                weight_kg=random.randint(20, 60),
                reps=random.randint(5, 12),
                sets=random.randint(2, 5),
            )
            session.add(item)

    session.commit()
    print("🎉 Fake 운동 기록 생성 완료!")


if __name__ == "__main__":
    seed_fake_data()

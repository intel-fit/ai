from sqlalchemy.orm import Session
from src.db import SessionLocal
from src.services.train_exercise_model import train_model

def retrain():
    session = SessionLocal()
    print("🔁 ML 재학습 시작...")
    train_model(session)
    print("🎉 모델 재학습 완료!")
    session.close()

if __name__ == "__main__":
    retrain()

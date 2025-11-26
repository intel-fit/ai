from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from src.services.training_data_builder import collect_training_data
from src.services.ml_trainer import train_exercise_model
from src import db

router = APIRouter(tags=["Admin"])

def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()

@router.post("/admin/retrain_ml")
def retrain_ml_model(session: Session = Depends(get_db)):
    df = collect_training_data(session)
    model = train_exercise_model(df)
    return {"status": "ok", "rows": len(df)}

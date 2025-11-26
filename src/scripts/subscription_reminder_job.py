# scripts/subscription_reminder_job.py
import os
from datetime import datetime, date
from sqlalchemy.orm import Session

from src.db import SessionLocal, Subscription
# User 모델이 필요하면 여기서 import 해서 이메일/닉네임 쓸 수 있음

def send_notification(user_id: str, title: str, message: str):
    """
    실제 알림 로직 자리.
    지금은 그냥 print, 나중에 FCM/이메일/인앱 알림 연결하면 됨.
    """
    print(f"[알림] to {user_id} :: {title} - {message}")


def run():
    session: Session = SessionLocal()
    today = date.today()

    subs = (
        session.query(Subscription)
        .filter(Subscription.status == "active")
        .all()
    )

    for sub in subs:
        if not sub.current_period_end:
            continue

        days_left = (sub.current_period_end.date() - today).days

        # D-3 리마인더
        if days_left == 3 and not sub.renewal_reminder_sent:
            send_notification(
                sub.user_id,
                "구독 만료 3일 전",
                "InterFit 프리미엄 구독이 3일 뒤 만료됩니다. 계속 이용하려면 결제가 자동 갱신됩니다."
            )
            sub.renewal_reminder_sent = True

        # D-1 만료 알림
        if days_left == 1 and not sub.expire_reminder_sent:
            send_notification(
                sub.user_id,
                "구독 만료 1일 전",
                "InterFit 프리미엄 구독이 내일 만료됩니다."
            )
            sub.expire_reminder_sent = True

    session.commit()
    session.close()


if __name__ == "__main__":
    run()

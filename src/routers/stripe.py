# src/routers/stripe.py
import os
import stripe
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import timedelta

from datetime import date
from src.schemas import SubscriptionStatus
from src import db


router = APIRouter(tags=["Stripe"])
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


def get_db():
    session = db.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ===========================
# Request Models
# ===========================
class CheckoutSessionRequest(BaseModel):
    user_id: str


class CancelSubscriptionRequest(BaseModel):
    user_id: str


# ===========================
# 0) 구독 상태 조회 API
# ===========================
@router.get("/subscription-status/{user_id}", response_model=SubscriptionStatus)
def get_subscription_status(user_id: str, session_db: Session = Depends(get_db)):
    sub = (
        session_db.query(db.Subscription)
        .filter(db.Subscription.user_id == user_id)
        .order_by(db.Subscription.created_at.desc())
        .first()
    )

    if not sub or sub.status != "active":
        return SubscriptionStatus(
            has_active_subscription=False,
            status=None,
            current_period_end=None,
            stripe_subscription_id=None,
        )

    return SubscriptionStatus(
        has_active_subscription=True,
        status=sub.status,
        current_period_end=sub.current_period_end,
        stripe_subscription_id=sub.stripe_subscription_id,
    )


# ===========================
# 1) Checkout Session 생성
# ===========================
@router.post("/create-checkout-session")
async def create_checkout_session(
    body: CheckoutSessionRequest,
    session_db: Session = Depends(get_db),
):
    try:
        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[
                {
                    "price": os.getenv("STRIPE_PRICE_ID"),
                    "quantity": 1
                }
            ],
            client_reference_id=body.user_id,
            metadata={"user_id": body.user_id},
            success_url="https://your-domain.com/stripe/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://your-domain.com/stripe/cancel",
        )
        return {"checkout_url": checkout_session.url}

    except Exception as e:
        raise HTTPException(400, str(e))


# ===========================
# 2) Webhook Endpoint
# ===========================
@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    session_db: Session = Depends(get_db),
):
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except Exception as e:
        raise HTTPException(400, f"Webhook signature error: {str(e)}")

    event_type = event["type"]

    # ======================================================
    # CASE 1) checkout.session.completed → 최초 구독 생성
    # ======================================================
    if event_type == "checkout.session.completed":
        data = event["data"]["object"]
        customer_id = data["customer"]
        subscription_id = data["subscription"]

        user_id = data.get("client_reference_id") or data.get("metadata", {}).get("user_id")

        print("🎉 구독 생성 완료:", subscription_id, "for user:", user_id)

        sub = stripe.Subscription.retrieve(subscription_id)

        start_ts = sub.get("current_period_start")
        end_ts = sub.get("current_period_end")

        current_period_start = datetime.fromtimestamp(start_ts) if start_ts else None
        # Stripe 값이 없으면 지금 시점을 시작으로 사용
        current_period_start = datetime.fromtimestamp(start_ts) if start_ts else datetime.utcnow()

        # 🔹 여기서 30일로 강제 설정
        current_period_end = current_period_start + timedelta(days=30)

        # 기존 active 구독 비활성화
        existing = (
            session_db.query(db.Subscription)
            .filter(db.Subscription.user_id == user_id, db.Subscription.status == "active")
            .first()
        )
        if existing:
            existing.status = "canceled"
            existing.canceled_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()

        new_sub = db.Subscription(
            user_id=user_id,
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
            status=sub["status"],
            current_period_start=current_period_start,
            current_period_end=current_period_end,
        )
        session_db.add(new_sub)
        session_db.commit()

    # ======================================================
    # CASE 2) invoice.paid → 결제 성공 (갱신 포함)
    # ======================================================
    elif event_type == "invoice.paid":
        data = event["data"]["object"]
        subscription_id = data.get("subscription")

        if subscription_id:
            print("💳 구독 결제 성공 (갱신 포함):", subscription_id)

            sub = stripe.Subscription.retrieve(subscription_id)

            start_ts = sub.get("current_period_start")
            end_ts = sub.get("current_period_end")

            current_period_start = datetime.fromtimestamp(start_ts)
            current_period_start = datetime.fromtimestamp(start_ts) if start_ts else datetime.utcnow()

            # 🔹 30일로 강제 설정
            current_period_end = current_period_start + timedelta(days=30)

            db_sub = (
                session_db.query(db.Subscription)
                .filter(db.Subscription.stripe_subscription_id == subscription_id)
                .first()
            )
            if db_sub:
                db_sub.status = sub["status"]
                db_sub.current_period_start = current_period_start
                db_sub.current_period_end = current_period_end
                db_sub.updated_at = datetime.utcnow()
                session_db.commit()

    elif event_type == "invoice.payment_failed":
        data = event["data"]["object"]
        subscription_id = data.get("subscription")

        if subscription_id:
            print("⚠️ 결제 실패:", subscription_id)

            # Stripe에서 현재 상태 확인 (past_due, unpaid 등)
            sub = stripe.Subscription.retrieve(subscription_id)
            new_status = sub["status"]  # 예: "past_due"

            db_sub = (
                session_db.query(db.Subscription)
                .filter(db.Subscription.stripe_subscription_id == subscription_id)
                .first()
            )
            if db_sub:
                db_sub.status = new_status
                db_sub.updated_at = datetime.utcnow()
                session_db.commit()

                # TODO: 여기서 사용자에게 "결제 실패" 알림 보내기 (푸시/이메일/인앱)
                print(f"⚠️ 사용자 {db_sub.user_id} 에게 결제 실패 알림 보내기")

    # ======================================================
    # CASE 3) customer.subscription.deleted → 해지
    # ======================================================
    elif event_type == "customer.subscription.deleted":
        data = event["data"]["object"]
        subscription_id = data["id"]

        print("❌ 구독 취소됨:", subscription_id)

        db_sub = (
            session_db.query(db.Subscription)
            .filter(db.Subscription.stripe_subscription_id == subscription_id)
            .first()
        )
        if db_sub:
            db_sub.status = "canceled"
            db_sub.canceled_at = datetime.utcnow()
            db_sub.updated_at = datetime.utcnow()
            session_db.commit()

    return JSONResponse({"status": "ok"})


# ===========================
# 3) SUCCESS 페이지
# ===========================
@router.get("/success")
async def success(session_id: str):
    session = stripe.checkout.Session.retrieve(session_id)
    return {
        "status": "success",
        "session_id": session_id,
        "customer": session.get("customer"),
        "subscription": session.get("subscription"),
    }


# ===========================
# 4) CANCEL 페이지
# ===========================
@router.get("/cancel")
async def cancel():
    return {"status": "cancel"}


# ===========================
# 5) 구독 취소 API (즉시 취소)
# ===========================
@router.post("/cancel-subscription")
def cancel_subscription(
    body: CancelSubscriptionRequest,
    session_db: Session = Depends(get_db),
):
    sub = (
        session_db.query(db.Subscription)
        .filter(db.Subscription.user_id == body.user_id, db.Subscription.status == "active")
        .order_by(db.Subscription.created_at.desc())
        .first()
    )
    if not sub:
        raise HTTPException(404, "Active subscription not found")

    try:
        stripe.Subscription.delete(sub.stripe_subscription_id)
    except Exception as e:
        raise HTTPException(400, f"Stripe cancel failed: {e}")

    sub.status = "canceled"
    sub.canceled_at = datetime.utcnow()
    sub.updated_at = datetime.utcnow()
    session_db.commit()

    return {"status": "canceled", "stripe_subscription_id": sub.stripe_subscription_id}


@router.get("/admin/subscription-summary")
def subscription_summary(session_db: Session = Depends(get_db)):
    total = session_db.query(db.Subscription).count()
    active = (
        session_db.query(db.Subscription)
        .filter(db.Subscription.status == "active")
        .count()
    )
    canceled = (
        session_db.query(db.Subscription)
        .filter(db.Subscription.status == "canceled")
        .count()
    )
    past_due = (
        session_db.query(db.Subscription)
        .filter(db.Subscription.status == "past_due")
        .count()
    )

    today = date.today()
    new_today = (
        session_db.query(db.Subscription)
        .filter(db.Subscription.created_at >= datetime(today.year, today.month, today.day))
        .count()
    )

    return {
        "total_subscriptions": total,
        "active_subscriptions": active,
        "canceled_subscriptions": canceled,
        "past_due_subscriptions": past_due,
        "new_subscriptions_today": new_today,
    }
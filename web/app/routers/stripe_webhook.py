import logging
import time

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..config import STRIPE_WEBHOOK_SECRET, STRIPE_SECRET_KEY, IS_PRODUCTION
from ..models import Subscription, SubscriptionStatus, SubscriptionPlan, Subscriber
from ..subscription_sync import activate_subscription_plates, deactivate_subscription_plates, compute_end_date
from ..email_service import send_payment_confirmation, send_manager_new_subscription

log = logging.getLogger("lapi.web.stripe_webhook")

router = APIRouter()


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
    except ImportError:
        return JSONResponse({"error": "stripe not installed"}, status_code=500)

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        if IS_PRODUCTION:
            log.error("STRIPE_WEBHOOK_SECRET not set in production, rejecting webhook")
            return JSONResponse({"error": "webhook secret not configured"}, status_code=500)
        import json
        try:
            event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
        except (ValueError, Exception) as e:
            log.warning(f"Webhook payload invalide: {e}")
            return JSONResponse({"error": "invalid payload"}, status_code=400)
    else:
        try:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            log.warning(f"Webhook signature invalide: {e}")
            return JSONResponse({"error": "invalid signature"}, status_code=400)

    if event.type == "checkout.session.completed":
        session = event.data.object
        if session.payment_status == "paid":
            _handle_checkout_completed(db, session)

    elif event.type == "invoice.payment_failed":
        invoice = event.data.object
        customer_id = invoice.customer
        subscriber = db.query(Subscriber).filter(
            Subscriber.stripe_customer_id == customer_id,
        ).first()
        if subscriber:
            active_subs = db.query(Subscription).filter(
                Subscription.subscriber_id == subscriber.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            ).all()
            for sub in active_subs:
                sub.status = SubscriptionStatus.PAST_DUE
            db.commit()
            log.warning(f"Paiement echoue pour subscriber {subscriber.id}")

    return JSONResponse({"status": "ok"})


def _handle_checkout_completed(db: Session, session):
    session_id = session.id
    existing = db.query(Subscription).filter(
        Subscription.stripe_checkout_session_id == session_id,
    ).first()
    if existing:
        return

    metadata = session.metadata or {}
    plan_id = metadata.get("plan_id")
    subscriber_id = metadata.get("subscriber_id")
    if not plan_id or not subscriber_id:
        return

    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == int(plan_id)).first()
    if not plan:
        return

    auto_renew = metadata.get("auto_renew") == "1"
    now = time.time()
    subscription = Subscription(
        subscriber_id=int(subscriber_id),
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        auto_renew=auto_renew,
        start_date=now,
        end_date=compute_end_date(now, plan.duration),
        stripe_checkout_session_id=session_id,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    activate_subscription_plates(db, subscription)

    subscriber = db.query(Subscriber).filter(Subscriber.id == int(subscriber_id)).first()
    if subscriber:
        send_payment_confirmation(subscriber, subscription)
        send_manager_new_subscription(plan.parking.tenant, subscriber, subscription)

    log.info(f"Abonnement {subscription.id} cree via webhook Stripe")

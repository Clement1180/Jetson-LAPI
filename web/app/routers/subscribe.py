import time
import logging

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import require_subscriber
from ..models import (
    Parking, Subscriber, SubscriptionPlan, Subscription,
    SubscriptionStatus, PlanDuration,
)
from ..config import STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, WEB_BASE_URL, STRIPE_WEBHOOK_SECRET
from ..subscription_sync import (
    activate_subscription_plates, deactivate_subscription_plates,
    compute_end_date, DURATION_SECONDS,
)
from ..templates_env import templates

log = logging.getLogger("lapi.web.subscribe")

router = APIRouter(prefix="/subscribe")

DURATION_LABELS = {
    PlanDuration.DAILY: "Journalier",
    PlanDuration.WEEKLY: "Hebdomadaire",
    PlanDuration.MONTHLY: "Mensuel",
    PlanDuration.QUARTERLY: "Trimestriel",
    PlanDuration.YEARLY: "Annuel",
}


def _stripe():
    """Lazy import stripe to avoid crash if not installed."""
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        return stripe
    except ImportError:
        return None


@router.get("/parkings", response_class=HTMLResponse)
def list_parkings(request: Request, db: Session = Depends(get_db)):
    parkings = db.query(Parking).all()
    parkings_with_plans = []
    for p in parkings:
        active_plans = [pl for pl in p.plans if pl.is_active]
        if active_plans:
            parkings_with_plans.append((p, active_plans))
    return templates.TemplateResponse(request, "subscribe/parkings.html", {
        "parkings_with_plans": parkings_with_plans,
        "duration_labels": DURATION_LABELS,
    })


@router.get("/parking/{parking_id}", response_class=HTMLResponse)
def parking_plans(request: Request, parking_id: int, db: Session = Depends(get_db)):
    parking = db.query(Parking).filter(Parking.id == parking_id).first()
    if not parking:
        return RedirectResponse(url="/subscribe/parkings", status_code=303)
    plans = db.query(SubscriptionPlan).filter(
        SubscriptionPlan.parking_id == parking_id,
        SubscriptionPlan.is_active == True,
    ).order_by(SubscriptionPlan.price_cents).all()
    return templates.TemplateResponse(request, "subscribe/plans.html", {
        "parking": parking,
        "plans": plans,
        "duration_labels": DURATION_LABELS,
        "stripe_key": STRIPE_PUBLISHABLE_KEY,
    })


@router.post("/checkout/{plan_id}")
def checkout(request: Request, plan_id: int, auto_renew: bool = Form(False),
             db: Session = Depends(get_db)):
    user = require_subscriber(request)
    subscriber = db.query(Subscriber).filter(Subscriber.id == int(user["sub"])).first()
    if not subscriber:
        return RedirectResponse(url="/subscribe/login", status_code=303)

    plan = db.query(SubscriptionPlan).filter(
        SubscriptionPlan.id == plan_id,
        SubscriptionPlan.is_active == True,
    ).first()
    if not plan:
        return RedirectResponse(url="/subscribe/parkings", status_code=303)

    stripe = _stripe()

    if stripe and STRIPE_SECRET_KEY:
        if not subscriber.stripe_customer_id:
            customer = stripe.Customer.create(
                email=subscriber.email,
                name=f"{subscriber.first_name} {subscriber.last_name}",
                metadata={"subscriber_id": str(subscriber.id)},
            )
            subscriber.stripe_customer_id = customer.id
            db.commit()

        session = stripe.checkout.Session.create(
            customer=subscriber.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "eur",
                    "unit_amount": plan.price_cents,
                    "product_data": {
                        "name": f"{plan.name} - {plan.parking.name}",
                        "description": f"Abonnement {DURATION_LABELS[plan.duration].lower()} parking {plan.parking.name}",
                    },
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{WEB_BASE_URL}/subscribe/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{WEB_BASE_URL}/subscribe/parking/{plan.parking_id}",
            metadata={
                "subscriber_id": str(subscriber.id),
                "plan_id": str(plan.id),
                "auto_renew": "1" if auto_renew else "0",
            },
        )
        return RedirectResponse(url=session.url, status_code=303)

    # Mode sans Stripe : activation directe (dev/test)
    now = time.time()
    subscription = Subscription(
        subscriber_id=subscriber.id,
        plan_id=plan.id,
        status=SubscriptionStatus.ACTIVE,
        auto_renew=auto_renew,
        start_date=now,
        end_date=compute_end_date(now, plan.duration),
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    activate_subscription_plates(db, subscription)
    return RedirectResponse(url="/subscribe/account", status_code=303)


@router.get("/success", response_class=HTMLResponse)
def checkout_success(request: Request, session_id: str = "", db: Session = Depends(get_db)):
    user = require_subscriber(request)
    stripe = _stripe()

    if stripe and session_id:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            existing = db.query(Subscription).filter(
                Subscription.stripe_checkout_session_id == session_id,
            ).first()
            if not existing:
                plan_id = int(session.metadata["plan_id"])
                subscriber_id = int(session.metadata["subscriber_id"])
                auto_renew = session.metadata.get("auto_renew") == "1"
                plan = db.query(SubscriptionPlan).get(plan_id)

                now = time.time()
                subscription = Subscription(
                    subscriber_id=subscriber_id,
                    plan_id=plan_id,
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

    return templates.TemplateResponse(request, "subscribe/success.html", {})


@router.get("/account", response_class=HTMLResponse)
def account(request: Request, db: Session = Depends(get_db)):
    user = require_subscriber(request)
    subscriber = db.query(Subscriber).filter(Subscriber.id == int(user["sub"])).first()
    if not subscriber:
        return RedirectResponse(url="/subscribe/login", status_code=303)

    subscriptions = db.query(Subscription).filter(
        Subscription.subscriber_id == subscriber.id,
    ).order_by(Subscription.created_at.desc()).all()

    now = time.time()
    return templates.TemplateResponse(request, "subscribe/account.html", {
        "subscriber": subscriber,
        "subscriptions": subscriptions,
        "duration_labels": DURATION_LABELS,
        "now": now,
        "SubscriptionStatus": SubscriptionStatus,
    })


@router.post("/cancel/{subscription_id}")
def cancel_subscription(request: Request, subscription_id: int,
                        db: Session = Depends(get_db)):
    user = require_subscriber(request)
    subscription = db.query(Subscription).filter(
        Subscription.id == subscription_id,
        Subscription.subscriber_id == int(user["sub"]),
    ).first()
    if not subscription:
        return RedirectResponse(url="/subscribe/account", status_code=303)

    subscription.status = SubscriptionStatus.CANCELLED
    db.commit()
    deactivate_subscription_plates(db, subscription)
    return RedirectResponse(url="/subscribe/account", status_code=303)


@router.post("/toggle-renew/{subscription_id}")
def toggle_auto_renew(request: Request, subscription_id: int,
                      db: Session = Depends(get_db)):
    user = require_subscriber(request)
    subscription = db.query(Subscription).filter(
        Subscription.id == subscription_id,
        Subscription.subscriber_id == int(user["sub"]),
    ).first()
    if subscription and subscription.status == SubscriptionStatus.ACTIVE:
        subscription.auto_renew = not subscription.auto_renew
        db.commit()
    return RedirectResponse(url="/subscribe/account", status_code=303)

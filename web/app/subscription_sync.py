import logging
import time

from sqlalchemy.orm import Session

from .models import (
    Subscription, SubscriptionStatus, SubscriptionPlan, Subscriber,
    Device, WhitelistEntry, PlanDuration,
)
from .mqtt_publisher import publish_plate_add, publish_plate_remove

log = logging.getLogger("lapi.web.subscription_sync")

DURATION_SECONDS = {
    PlanDuration.DAILY: 86400,
    PlanDuration.WEEKLY: 7 * 86400,
    PlanDuration.MONTHLY: 30 * 86400,
    PlanDuration.QUARTERLY: 91 * 86400,
    PlanDuration.YEARLY: 365 * 86400,
}


def compute_end_date(start: float, duration: PlanDuration) -> float:
    return start + DURATION_SECONDS[duration]


def activate_subscription_plates(db: Session, subscription: Subscription):
    """Add subscriber plate to all devices in the parking."""
    plan = subscription.plan
    subscriber = subscription.subscriber
    plate = subscriber.plate
    parking = plan.parking

    for device in parking.devices:
        existing = db.query(WhitelistEntry).filter(
            WhitelistEntry.device_id == device.id,
            WhitelistEntry.plate == plate,
        ).first()
        if not existing:
            entry = WhitelistEntry(
                device_id=device.id,
                plate=plate,
                label=f"Abo: {subscriber.first_name} {subscriber.last_name}",
                owner_name=f"{subscriber.first_name} {subscriber.last_name}",
            )
            db.add(entry)
            publish_plate_add(device.mqtt_client_id, plate, entry.label)
            log.info(f"Plaque {plate} ajoutee au device {device.serial_number}")

    db.commit()


def deactivate_subscription_plates(db: Session, subscription: Subscription):
    """Remove subscriber plate from all devices in the parking, unless another active sub exists."""
    plan = subscription.plan
    subscriber = subscription.subscriber
    plate = subscriber.plate
    parking = plan.parking

    other_active = db.query(Subscription).filter(
        Subscription.subscriber_id == subscriber.id,
        Subscription.id != subscription.id,
        Subscription.status == SubscriptionStatus.ACTIVE,
        Subscription.plan_id.in_(
            db.query(SubscriptionPlan.id).filter(SubscriptionPlan.parking_id == parking.id)
        ),
    ).first()

    if other_active:
        return

    for device in parking.devices:
        entry = db.query(WhitelistEntry).filter(
            WhitelistEntry.device_id == device.id,
            WhitelistEntry.plate == plate,
        ).first()
        if entry:
            db.delete(entry)
            publish_plate_remove(device.mqtt_client_id, plate)
            log.info(f"Plaque {plate} retiree du device {device.serial_number}")

    db.commit()


def check_expired_subscriptions(db: Session):
    """Check and expire subscriptions past their end date."""
    now = time.time()
    expired = db.query(Subscription).filter(
        Subscription.status == SubscriptionStatus.ACTIVE,
        Subscription.end_date <= now,
    ).all()

    for sub in expired:
        if sub.auto_renew and sub.plan.is_active:
            sub.start_date = now
            sub.end_date = compute_end_date(now, sub.plan.duration)
            log.info(f"Abonnement {sub.id} renouvele jusqu'a {sub.end_date}")
        else:
            sub.status = SubscriptionStatus.EXPIRED
            deactivate_subscription_plates(db, sub)
            log.info(f"Abonnement {sub.id} expire")

    db.commit()
    return len(expired)

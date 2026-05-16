"""Tests for subscription system: checkout, activation, cancellation, expiration."""

import time
import pytest
from unittest.mock import patch

from app.models import (
    Subscription, SubscriptionStatus, SubscriptionPlan, PlanDuration,
    WhitelistEntry, Subscriber,
)
from app.subscription_sync import (
    activate_subscription_plates, deactivate_subscription_plates,
    check_expired_subscriptions, check_expiry_warnings, compute_end_date,
    DURATION_SECONDS,
)
from app.security import CSRF_COOKIE_NAME

CSRF = "test-csrf-token-fixed"


def _post(client, url, data=None, cookies=None):
    cookies = cookies or {}
    cookies[CSRF_COOKIE_NAME] = CSRF
    data = data or {}
    data["csrf_token"] = CSRF
    return client.post(url, data=data, cookies=cookies, follow_redirects=False)


class TestDurationComputation:
    def test_daily(self):
        now = 1000000.0
        assert compute_end_date(now, PlanDuration.DAILY) == now + 86400

    def test_monthly(self):
        now = 1000000.0
        assert compute_end_date(now, PlanDuration.MONTHLY) == now + 30 * 86400

    def test_yearly(self):
        now = 1000000.0
        assert compute_end_date(now, PlanDuration.YEARLY) == now + 365 * 86400


class TestSubscriptionActivation:
    @patch("app.subscription_sync.publish_plate_add")
    def test_activate_adds_plate_to_devices(self, mock_mqtt, db_session, active_subscription, device):
        activate_subscription_plates(db_session, active_subscription)
        entry = db_session.query(WhitelistEntry).filter(
            WhitelistEntry.device_id == device.id,
            WhitelistEntry.plate == "AB-123-CD",
        ).first()
        assert entry is not None
        mock_mqtt.assert_called_once()

    @patch("app.subscription_sync.publish_plate_add")
    def test_activate_idempotent(self, mock_mqtt, db_session, active_subscription, device):
        activate_subscription_plates(db_session, active_subscription)
        activate_subscription_plates(db_session, active_subscription)
        count = db_session.query(WhitelistEntry).filter(
            WhitelistEntry.device_id == device.id,
            WhitelistEntry.plate == "AB-123-CD",
        ).count()
        assert count == 1


class TestSubscriptionDeactivation:
    @patch("app.subscription_sync.publish_plate_remove")
    @patch("app.subscription_sync.publish_plate_add")
    def test_deactivate_removes_plate(self, mock_add, mock_remove, db_session, active_subscription, device):
        activate_subscription_plates(db_session, active_subscription)
        deactivate_subscription_plates(db_session, active_subscription)
        entry = db_session.query(WhitelistEntry).filter(
            WhitelistEntry.device_id == device.id,
            WhitelistEntry.plate == "AB-123-CD",
        ).first()
        assert entry is None
        mock_remove.assert_called_once()

    @patch("app.subscription_sync.publish_plate_remove")
    @patch("app.subscription_sync.publish_plate_add")
    def test_deactivate_keeps_plate_if_other_active_sub(self, mock_add, mock_remove, db_session, subscriber, plan, device):
        now = time.time()
        sub1 = Subscription(subscriber_id=subscriber.id, plan_id=plan.id, status=SubscriptionStatus.ACTIVE, auto_renew=False, start_date=now, end_date=now + 86400)
        sub2 = Subscription(subscriber_id=subscriber.id, plan_id=plan.id, status=SubscriptionStatus.ACTIVE, auto_renew=False, start_date=now, end_date=now + 86400 * 2)
        db_session.add_all([sub1, sub2])
        db_session.commit()
        db_session.refresh(sub1)
        db_session.refresh(sub2)

        activate_subscription_plates(db_session, sub1)
        deactivate_subscription_plates(db_session, sub1)

        entry = db_session.query(WhitelistEntry).filter(
            WhitelistEntry.device_id == device.id,
            WhitelistEntry.plate == "AB-123-CD",
        ).first()
        assert entry is not None
        mock_remove.assert_not_called()


class TestExpiration:
    @patch("app.subscription_sync.publish_plate_remove")
    @patch("app.subscription_sync.publish_plate_add")
    def test_expired_subscription_gets_expired(self, mock_add, mock_remove, db_session, subscriber, plan, device):
        now = time.time()
        sub = Subscription(
            subscriber_id=subscriber.id, plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE, auto_renew=False,
            start_date=now - 86400 * 31, end_date=now - 100,
        )
        db_session.add(sub)
        db_session.commit()
        activate_subscription_plates(db_session, sub)

        count = check_expired_subscriptions(db_session)
        assert count == 1
        db_session.refresh(sub)
        assert sub.status == SubscriptionStatus.EXPIRED

    @patch("app.subscription_sync.publish_plate_add")
    def test_auto_renew_extends_subscription(self, mock_add, db_session, subscriber, plan, device):
        now = time.time()
        sub = Subscription(
            subscriber_id=subscriber.id, plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE, auto_renew=True,
            start_date=now - 86400 * 31, end_date=now - 100,
        )
        db_session.add(sub)
        db_session.commit()

        count = check_expired_subscriptions(db_session)
        assert count == 1
        db_session.refresh(sub)
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.end_date > now


class TestExpiryWarnings:
    @patch("app.subscription_sync.send_expiry_warning")
    def test_warning_sent_before_expiry(self, mock_email, db_session, subscriber, plan):
        now = time.time()
        sub = Subscription(
            subscriber_id=subscriber.id, plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE, auto_renew=False,
            start_date=now - 86400 * 25, end_date=now + 86400 * 3,
            expiry_warning_sent=False,
        )
        db_session.add(sub)
        db_session.commit()

        count = check_expiry_warnings(db_session)
        assert count == 1
        db_session.refresh(sub)
        assert sub.expiry_warning_sent is True
        mock_email.assert_called_once()

    @patch("app.subscription_sync.send_expiry_warning")
    def test_warning_not_sent_twice(self, mock_email, db_session, subscriber, plan):
        now = time.time()
        sub = Subscription(
            subscriber_id=subscriber.id, plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE, auto_renew=False,
            start_date=now - 86400 * 25, end_date=now + 86400 * 3,
            expiry_warning_sent=True,
        )
        db_session.add(sub)
        db_session.commit()

        count = check_expiry_warnings(db_session)
        assert count == 0
        mock_email.assert_not_called()


class TestCheckoutDevMode:
    @patch("app.routers.subscribe.send_payment_confirmation")
    @patch("app.routers.subscribe.send_manager_new_subscription")
    @patch("app.subscription_sync.publish_plate_add")
    def test_checkout_without_stripe_activates_directly(self, mock_mqtt, mock_mgr, mock_email, client, subscriber_token, subscriber, plan, device, db_session):
        r = _post(client, f"/subscribe/checkout/{plan.id}", {
            "auto_renew": "false",
        }, cookies={"token": subscriber_token})
        assert r.status_code == 303
        sub = db_session.query(Subscription).filter(
            Subscription.subscriber_id == subscriber.id,
        ).first()
        assert sub is not None
        assert sub.status == SubscriptionStatus.ACTIVE


class TestCancelSubscription:
    @patch("app.subscription_sync.publish_plate_remove")
    @patch("app.subscription_sync.publish_plate_add")
    def test_cancel_subscription(self, mock_add, mock_remove, client, subscriber_token, active_subscription, device, db_session):
        activate_subscription_plates(db_session, active_subscription)
        r = _post(client, f"/subscribe/cancel/{active_subscription.id}",
                  cookies={"token": subscriber_token})
        assert r.status_code == 303
        db_session.refresh(active_subscription)
        assert active_subscription.status == SubscriptionStatus.CANCELLED


class TestToggleAutoRenew:
    def test_toggle_renew(self, client, subscriber_token, active_subscription, db_session):
        assert active_subscription.auto_renew is False
        _post(client, f"/subscribe/toggle-renew/{active_subscription.id}",
              cookies={"token": subscriber_token})
        db_session.refresh(active_subscription)
        assert active_subscription.auto_renew is True

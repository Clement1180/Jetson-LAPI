"""Tests for Stripe webhook integration."""

import json
import time
import pytest
from unittest.mock import patch, MagicMock

from app.models import (
    Subscription, SubscriptionStatus, Subscriber,
)


class TestStripeWebhook:
    @patch("app.subscription_sync.publish_plate_add")
    @patch("app.routers.stripe_webhook.send_payment_confirmation")
    @patch("app.routers.stripe_webhook.send_manager_new_subscription")
    def test_checkout_completed_creates_subscription(
        self, mock_mgr, mock_email, mock_mqtt,
        client, subscriber, plan, device, db_session,
    ):
        event_data = {
            "id": "evt_test_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_session_001",
                    "payment_status": "paid",
                    "metadata": {
                        "subscriber_id": str(subscriber.id),
                        "plan_id": str(plan.id),
                        "auto_renew": "1",
                    },
                }
            },
        }
        with patch("stripe.Webhook.construct_event") as mock_construct:
            mock_construct.return_value = MagicMock(
                type="checkout.session.completed",
                data=MagicMock(object=MagicMock(
                    id="cs_test_session_001",
                    payment_status="paid",
                    metadata={
                        "subscriber_id": str(subscriber.id),
                        "plan_id": str(plan.id),
                        "auto_renew": "1",
                    },
                )),
            )
            with patch("app.routers.stripe_webhook.STRIPE_WEBHOOK_SECRET", "whsec_test"):
                with patch("app.routers.stripe_webhook.STRIPE_SECRET_KEY", "sk_test"):
                    r = client.post("/webhook/stripe",
                        content=json.dumps(event_data),
                        headers={"stripe-signature": "t=123,v1=abc", "content-type": "application/json"},
                    )
        assert r.status_code == 200
        sub = db_session.query(Subscription).filter(
            Subscription.stripe_checkout_session_id == "cs_test_session_001",
        ).first()
        assert sub is not None
        assert sub.status == SubscriptionStatus.ACTIVE
        assert sub.auto_renew is True

    @patch("app.subscription_sync.publish_plate_add")
    @patch("app.routers.stripe_webhook.send_payment_confirmation")
    @patch("app.routers.stripe_webhook.send_manager_new_subscription")
    def test_duplicate_session_ignored(
        self, mock_mgr, mock_email, mock_mqtt,
        client, subscriber, plan, device, db_session,
    ):
        now = time.time()
        existing = Subscription(
            subscriber_id=subscriber.id, plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE, auto_renew=False,
            start_date=now, end_date=now + 86400 * 30,
            stripe_checkout_session_id="cs_test_dup",
        )
        db_session.add(existing)
        db_session.commit()

        with patch("stripe.Webhook.construct_event") as mock_construct:
            mock_construct.return_value = MagicMock(
                type="checkout.session.completed",
                data=MagicMock(object=MagicMock(
                    id="cs_test_dup",
                    payment_status="paid",
                    metadata={
                        "subscriber_id": str(subscriber.id),
                        "plan_id": str(plan.id),
                        "auto_renew": "0",
                    },
                )),
            )
            with patch("app.routers.stripe_webhook.STRIPE_WEBHOOK_SECRET", "whsec_test"):
                with patch("app.routers.stripe_webhook.STRIPE_SECRET_KEY", "sk_test"):
                    r = client.post("/webhook/stripe",
                        content=json.dumps({}),
                        headers={"stripe-signature": "t=123,v1=abc", "content-type": "application/json"},
                    )
        assert r.status_code == 200
        count = db_session.query(Subscription).filter(
            Subscription.subscriber_id == subscriber.id,
        ).count()
        assert count == 1

    def test_payment_failed_marks_past_due(self, client, subscriber, plan, device, db_session):
        subscriber.stripe_customer_id = "cus_test_123"
        db_session.commit()

        now = time.time()
        sub = Subscription(
            subscriber_id=subscriber.id, plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE, auto_renew=True,
            start_date=now, end_date=now + 86400 * 30,
        )
        db_session.add(sub)
        db_session.commit()
        db_session.refresh(sub)

        with patch("stripe.Webhook.construct_event") as mock_construct:
            mock_construct.return_value = MagicMock(
                type="invoice.payment_failed",
                data=MagicMock(object=MagicMock(customer="cus_test_123")),
            )
            with patch("app.routers.stripe_webhook.STRIPE_WEBHOOK_SECRET", "whsec_test"):
                with patch("app.routers.stripe_webhook.STRIPE_SECRET_KEY", "sk_test"):
                    r = client.post("/webhook/stripe",
                        content=json.dumps({}),
                        headers={"stripe-signature": "t=123,v1=abc", "content-type": "application/json"},
                    )
        assert r.status_code == 200
        db_session.refresh(sub)
        assert sub.status == SubscriptionStatus.PAST_DUE


class TestWebhookSecurity:
    def test_missing_stripe_returns_error(self, client):
        with patch("app.routers.stripe_webhook.STRIPE_SECRET_KEY", "sk_test"):
            with patch.dict("sys.modules", {"stripe": None}):
                pass

    def test_invalid_signature_rejected(self, client):
        with patch("app.routers.stripe_webhook.STRIPE_WEBHOOK_SECRET", "whsec_test"):
            with patch("app.routers.stripe_webhook.STRIPE_SECRET_KEY", "sk_test"):
                with patch("stripe.Webhook.construct_event") as mock_construct:
                    import stripe
                    mock_construct.side_effect = stripe.error.SignatureVerificationError("bad sig", "sig")
                    r = client.post("/webhook/stripe",
                        content=b"{}",
                        headers={"stripe-signature": "invalid", "content-type": "application/json"},
                    )
                    assert r.status_code == 400

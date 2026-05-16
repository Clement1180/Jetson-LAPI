"""Initial schema - all tables.

Revision ID: 001
Revises: None
Create Date: 2026-05-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
    )

    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("contact_email", sa.String(100), server_default=""),
        sa.Column("is_active", sa.Boolean(), server_default="1"),
        sa.Column("created_at", sa.Float()),
    )

    op.create_table(
        "tenant_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("username", sa.String(50), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1"),
        sa.Column("created_at", sa.Float()),
    )

    op.create_table(
        "parkings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("address", sa.String(255), server_default=""),
        sa.Column("require_totp", sa.Boolean(), server_default="0"),
        sa.Column("created_at", sa.Float()),
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parking_id", sa.Integer(), sa.ForeignKey("parkings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("serial_number", sa.String(50), unique=True, nullable=False),
        sa.Column("name", sa.String(100), server_default=""),
        sa.Column("mqtt_client_id", sa.String(100), unique=True, nullable=False),
        sa.Column("is_online", sa.Boolean(), server_default="0"),
        sa.Column("last_seen", sa.Float(), server_default="0"),
        sa.Column("created_at", sa.Float()),
    )

    op.create_table(
        "whitelist_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plate", sa.String(20), nullable=False),
        sa.Column("label", sa.String(100), server_default=""),
        sa.Column("owner_name", sa.String(100), server_default=""),
        sa.Column("totp_secret", sa.String(32), server_default=""),
        sa.Column("created_at", sa.Float()),
        sa.UniqueConstraint("device_id", "plate", name="uq_device_plate"),
    )

    op.create_table(
        "subscribers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), server_default=""),
        sa.Column("last_name", sa.String(100), server_default=""),
        sa.Column("plate", sa.String(20), nullable=False),
        sa.Column("stripe_customer_id", sa.String(255), server_default=""),
        sa.Column("is_active", sa.Boolean(), server_default="1"),
        sa.Column("created_at", sa.Float()),
    )

    op.create_table(
        "subscription_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parking_id", sa.Integer(), sa.ForeignKey("parkings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("duration", sa.String(20), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("auto_renew_allowed", sa.Boolean(), server_default="1"),
        sa.Column("is_active", sa.Boolean(), server_default="1"),
        sa.Column("stripe_price_id", sa.String(255), server_default=""),
        sa.Column("created_at", sa.Float()),
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subscriber_id", sa.Integer(), sa.ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("subscription_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("auto_renew", sa.Boolean(), server_default="0"),
        sa.Column("start_date", sa.Float(), nullable=False),
        sa.Column("end_date", sa.Float(), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(255), server_default=""),
        sa.Column("stripe_checkout_session_id", sa.String(255), server_default=""),
        sa.Column("expiry_warning_sent", sa.Boolean(), server_default="0"),
        sa.Column("created_at", sa.Float()),
    )


def downgrade() -> None:
    op.drop_table("subscriptions")
    op.drop_table("subscription_plans")
    op.drop_table("subscribers")
    op.drop_table("whitelist_entries")
    op.drop_table("devices")
    op.drop_table("parkings")
    op.drop_table("tenant_users")
    op.drop_table("tenants")
    op.drop_table("admins")

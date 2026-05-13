from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, UniqueConstraint, Enum
from sqlalchemy.orm import relationship
from .database import Base
import enum
import time


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PAST_DUE = "past_due"


class PlanDuration(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    contact_email = Column(String(100), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(Float, default=time.time)

    users = relationship("TenantUser", back_populates="tenant", cascade="all, delete-orphan")
    parkings = relationship("Parking", back_populates="tenant", cascade="all, delete-orphan")


class TenantUser(Base):
    __tablename__ = "tenant_users"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(Float, default=time.time)

    tenant = relationship("Tenant", back_populates="users")


class Parking(Base):
    __tablename__ = "parkings"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    address = Column(String(255), default="")
    require_totp = Column(Boolean, default=False)
    created_at = Column(Float, default=time.time)

    tenant = relationship("Tenant", back_populates="parkings")
    devices = relationship("Device", back_populates="parking", cascade="all, delete-orphan")
    plans = relationship("SubscriptionPlan", back_populates="parking", cascade="all, delete-orphan")


class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True)
    parking_id = Column(Integer, ForeignKey("parkings.id", ondelete="CASCADE"), nullable=False)
    serial_number = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), default="")
    mqtt_client_id = Column(String(100), unique=True, nullable=False)
    is_online = Column(Boolean, default=False)
    last_seen = Column(Float, default=0)
    created_at = Column(Float, default=time.time)

    parking = relationship("Parking", back_populates="devices")
    whitelist = relationship("WhitelistEntry", back_populates="device", cascade="all, delete-orphan")


class WhitelistEntry(Base):
    __tablename__ = "whitelist_entries"
    __table_args__ = (UniqueConstraint("device_id", "plate", name="uq_device_plate"),)

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    plate = Column(String(20), nullable=False)
    label = Column(String(100), default="")
    owner_name = Column(String(100), default="")
    totp_secret = Column(String(32), default="")
    created_at = Column(Float, default=time.time)

    device = relationship("Device", back_populates="whitelist")


class Subscriber(Base):
    __tablename__ = "subscribers"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), default="")
    last_name = Column(String(100), default="")
    plate = Column(String(20), nullable=False)
    stripe_customer_id = Column(String(255), default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(Float, default=time.time)

    subscriptions = relationship("Subscription", back_populates="subscriber", cascade="all, delete-orphan")


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    id = Column(Integer, primary_key=True)
    parking_id = Column(Integer, ForeignKey("parkings.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    duration = Column(Enum(PlanDuration), nullable=False)
    price_cents = Column(Integer, nullable=False)
    auto_renew_allowed = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    stripe_price_id = Column(String(255), default="")
    created_at = Column(Float, default=time.time)

    parking = relationship("Parking", back_populates="plans")
    subscriptions = relationship("Subscription", back_populates="plan", cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True)
    subscriber_id = Column(Integer, ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id", ondelete="CASCADE"), nullable=False)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, nullable=False)
    auto_renew = Column(Boolean, default=False)
    start_date = Column(Float, nullable=False)
    end_date = Column(Float, nullable=False)
    stripe_subscription_id = Column(String(255), default="")
    stripe_checkout_session_id = Column(String(255), default="")
    created_at = Column(Float, default=time.time)

    subscriber = relationship("Subscriber", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")

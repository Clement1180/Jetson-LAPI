from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .database import Base
import time


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

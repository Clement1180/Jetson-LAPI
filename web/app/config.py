import os

SECRET_KEY = os.getenv("LAPI_SECRET_KEY", "change-me-in-production-with-a-real-secret")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 480

DATABASE_URL = os.getenv("LAPI_DATABASE_URL", "sqlite:///./lapi.db")

MQTT_BROKER = os.getenv("LAPI_MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("LAPI_MQTT_PORT", "8883"))
MQTT_USERNAME = os.getenv("LAPI_MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("LAPI_MQTT_PASSWORD", "")
MQTT_USE_TLS = os.getenv("LAPI_MQTT_USE_TLS", "true").lower() in ("true", "1", "yes")
MQTT_CA_CERT = os.getenv("LAPI_MQTT_CA_CERT", "")
MQTT_CLIENT_CERT = os.getenv("LAPI_MQTT_CLIENT_CERT", "")
MQTT_CLIENT_KEY = os.getenv("LAPI_MQTT_CLIENT_KEY", "")

OTA_STORAGE_DIR = os.getenv("LAPI_OTA_DIR", "app/static/ota")
WEB_BASE_URL = os.getenv("LAPI_WEB_BASE_URL", "http://localhost:8000")

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

SMTP_HOST = os.getenv("LAPI_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("LAPI_SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("LAPI_SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("LAPI_SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("LAPI_SMTP_FROM", "noreply@lapi.fr")
SMTP_USE_TLS = os.getenv("LAPI_SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

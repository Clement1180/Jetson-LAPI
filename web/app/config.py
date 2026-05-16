import os
import sys

_ENV = os.getenv("LAPI_ENV", "development")
IS_PRODUCTION = _ENV.lower() in ("production", "prod")

_secret = os.getenv("LAPI_SECRET_KEY", "")
if not _secret:
    if IS_PRODUCTION:
        print("FATAL: LAPI_SECRET_KEY env var is required in production.", file=sys.stderr)
        sys.exit(1)
    _secret = "dev-only-insecure-key-do-not-use-in-prod"

SECRET_KEY = _secret
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

DEFAULT_ADMIN_USERNAME = os.getenv("LAPI_ADMIN_USERNAME", "")
DEFAULT_ADMIN_PASSWORD = os.getenv("LAPI_ADMIN_PASSWORD", "")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

if IS_PRODUCTION and STRIPE_SECRET_KEY and not STRIPE_WEBHOOK_SECRET:
    print("FATAL: STRIPE_WEBHOOK_SECRET is required when Stripe is enabled in production.", file=sys.stderr)
    sys.exit(1)

SMTP_HOST = os.getenv("LAPI_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("LAPI_SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("LAPI_SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("LAPI_SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("LAPI_SMTP_FROM", "noreply@lapi.fr")
SMTP_USE_TLS = os.getenv("LAPI_SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

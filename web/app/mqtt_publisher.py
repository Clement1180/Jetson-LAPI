import json
import logging
import ssl
import time
from typing import List, Tuple, Optional

import paho.mqtt.client as mqtt

from .config import (
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD,
    MQTT_USE_TLS, MQTT_CA_CERT, MQTT_CLIENT_CERT, MQTT_CLIENT_KEY,
)

log = logging.getLogger("lapi.web.mqtt")

_client: Optional[mqtt.Client] = None
_connected = False
_db_session_factory = None


def init_mqtt(session_factory=None):
    global _client, _connected, _db_session_factory
    _db_session_factory = session_factory

    _v2 = hasattr(mqtt, "CallbackAPIVersion")

    if _v2:
        _client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
            client_id="lapi-web-admin",
            protocol=mqtt.MQTTv311,
        )
    else:
        _client = mqtt.Client(client_id="lapi-web-admin", protocol=mqtt.MQTTv311)

    if MQTT_USERNAME:
        _client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    if MQTT_USE_TLS:
        ca = MQTT_CA_CERT or None
        cert = MQTT_CLIENT_CERT or None
        key = MQTT_CLIENT_KEY or None
        _client.tls_set(
            ca_certs=ca,
            certfile=cert,
            keyfile=key,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )

    def on_connect(client, userdata, flags, rc):
        global _connected
        _connected = rc == 0
        if rc == 0:
            log.info("MQTT publisher connecte")
            client.subscribe("lapi/+/access/log", qos=1)
            client.subscribe("lapi/+/status", qos=1)
        else:
            log.error(f"MQTT connexion echouee: rc={rc}")

    def on_disconnect(client, userdata, rc):
        global _connected
        _connected = False
        if rc != 0:
            log.warning("MQTT deconnexion inattendue")

    _client.on_connect = on_connect
    _client.on_disconnect = on_disconnect
    _client.on_message = _on_message
    _client.reconnect_delay_set(min_delay=1, max_delay=30)

    try:
        _client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
        _client.loop_start()
    except Exception as e:
        log.warning(f"MQTT non disponible: {e}")


def _on_message(client, userdata, msg):
    try:
        topic_parts = msg.topic.split("/")
        if len(topic_parts) < 3:
            return
        device_mqtt_id = topic_parts[1]
        action = "/".join(topic_parts[2:])
        payload = json.loads(msg.payload.decode())

        if action == "access/log":
            _handle_access_log(device_mqtt_id, payload)
        elif action == "status":
            _handle_device_status(device_mqtt_id, payload)
    except Exception as e:
        log.error(f"Erreur traitement message MQTT {msg.topic}: {e}")


def _handle_access_log(device_mqtt_id: str, payload: dict):
    if not _db_session_factory:
        return
    from .models import Device, AccessLog, AccessResult, Alert, AlertType, AlertSeverity
    db = _db_session_factory()
    try:
        device = db.query(Device).filter(Device.mqtt_client_id == device_mqtt_id).first()
        if not device:
            log.warning(f"Device MQTT inconnu: {device_mqtt_id}")
            return

        plate = payload.get("plate", "")
        result_str = payload.get("result", "denied")
        confidence = payload.get("confidence", 0.0)

        result = AccessResult.GRANTED if result_str == "granted" else AccessResult.DENIED

        access_log = AccessLog(
            device_id=device.id,
            plate=plate,
            result=result,
            confidence=confidence,
            created_at=payload.get("timestamp", time.time()),
        )
        db.add(access_log)

        if result == AccessResult.DENIED and plate:
            alert = Alert(
                parking_id=device.parking_id,
                device_id=device.id,
                alert_type=AlertType.ACCESS_DENIED,
                severity=AlertSeverity.WARNING,
                message=f"Acces refuse: plaque {plate} non autorisee",
                plate=plate,
                created_at=time.time(),
            )
            db.add(alert)
            _notify_alert_async(device, alert)

        db.commit()
    except Exception as e:
        db.rollback()
        log.error(f"Erreur enregistrement access log: {e}")
    finally:
        db.close()


def _handle_device_status(device_mqtt_id: str, payload: dict):
    if not _db_session_factory:
        return
    from .models import Device, Alert, AlertType, AlertSeverity
    db = _db_session_factory()
    try:
        device = db.query(Device).filter(Device.mqtt_client_id == device_mqtt_id).first()
        if not device:
            return

        was_online = device.is_online
        device.is_online = True
        device.last_seen = time.time()

        if not was_online:
            alert = Alert(
                parking_id=device.parking_id,
                device_id=device.id,
                alert_type=AlertType.DEVICE_ONLINE,
                severity=AlertSeverity.INFO,
                message=f"Dispositif {device.name or device.serial_number} de retour en ligne",
                created_at=time.time(),
            )
            db.add(alert)

        db.commit()
    except Exception as e:
        db.rollback()
        log.error(f"Erreur mise a jour statut device: {e}")
    finally:
        db.close()


def _notify_alert_async(device, alert):
    """Trigger alert email in background."""
    import threading
    def _send():
        try:
            from .email_service import send_alert_notification
            send_alert_notification(device, alert)
        except Exception as e:
            log.error(f"Erreur envoi alerte email: {e}")
    threading.Thread(target=_send, daemon=True).start()


def stop_mqtt():
    global _client
    if _client:
        _client.loop_stop()
        _client.disconnect()


def publish_plate_add(device_mqtt_id: str, plate: str, label: str = ""):
    _publish(device_mqtt_id, "add", {"plate": plate, "label": label})


def publish_plate_remove(device_mqtt_id: str, plate: str):
    _publish(device_mqtt_id, "remove", {"plate": plate})


def publish_whitelist_sync(device_mqtt_id: str, plates: List[Tuple[str, str]]):
    _publish(device_mqtt_id, "sync", {
        "plates": [{"plate": p, "label": l} for p, l in plates]
    })


def publish_ota_update(device_mqtt_id: str, download_url: str, sha256: str, version: str):
    _publish_topic(f"lapi/{device_mqtt_id}/ota/update", {
        "url": download_url,
        "sha256": sha256,
        "version": version,
    })


def _publish(device_mqtt_id: str, action: str, payload: dict):
    _publish_topic(f"lapi/{device_mqtt_id}/whitelist/{action}", payload)


def _publish_topic(topic: str, payload: dict):
    if not _client or not _connected:
        log.debug(f"MQTT hors ligne, message non envoye: {topic}")
        return
    _client.publish(topic, json.dumps(payload), qos=1)
    log.info(f"MQTT -> {topic}")

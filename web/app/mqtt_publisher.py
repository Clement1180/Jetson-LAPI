import json
import logging
import ssl
from typing import List, Tuple, Optional

import paho.mqtt.client as mqtt

from .config import (
    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD,
    MQTT_USE_TLS, MQTT_CA_CERT, MQTT_CLIENT_CERT, MQTT_CLIENT_KEY,
)

log = logging.getLogger("lapi.web.mqtt")

_client: Optional[mqtt.Client] = None
_connected = False


def init_mqtt():
    global _client, _connected

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
        else:
            log.error(f"MQTT connexion echouee: rc={rc}")

    def on_disconnect(client, userdata, rc):
        global _connected
        _connected = False
        if rc != 0:
            log.warning("MQTT deconnexion inattendue")

    _client.on_connect = on_connect
    _client.on_disconnect = on_disconnect
    _client.reconnect_delay_set(min_delay=1, max_delay=30)

    try:
        _client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
        _client.loop_start()
    except Exception as e:
        log.warning(f"MQTT non disponible: {e}")


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

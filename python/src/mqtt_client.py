import json
import logging
import ssl
import threading
import time
from typing import Optional

import paho.mqtt.client as mqtt

log = logging.getLogger("lapi.mqtt")

TOPIC_WHITELIST_SYNC = "lapi/whitelist/sync"
TOPIC_WHITELIST_ADD = "lapi/whitelist/add"
TOPIC_WHITELIST_REMOVE = "lapi/whitelist/remove"
TOPIC_OTA_UPDATE = "lapi/ota/update"
TOPIC_ACCESS_OPEN = "lapi/access/open"
TOPIC_STATUS = "lapi/status"


class MQTTSync:
    def __init__(self, db, broker: str = "localhost", port: int = 1883,
                 client_id: str = "lapi-edge-001",
                 username: Optional[str] = None, password: Optional[str] = None,
                 use_tls: bool = False, ca_certs: Optional[str] = None,
                 client_cert: Optional[str] = None, client_key: Optional[str] = None,
                 ota_handler=None, relay=None):
        self._db = db
        self._ota_handler = ota_handler
        self._relay = relay
        self._broker = broker
        self._port = port
        self._connected = False

        self._client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

        if username:
            self._client.username_pw_set(username, password)
        if use_tls:
            self._client.tls_set(
                ca_certs=ca_certs,
                certfile=client_cert,
                keyfile=client_key,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        self._client.reconnect_delay_set(min_delay=1, max_delay=60)

    def start(self):
        log.info(f"Connexion MQTT vers {self._broker}:{self._port}")
        try:
            self._client.connect_async(self._broker, self._port, keepalive=60)
            self._client.loop_start()
        except Exception as e:
            log.error(f"Erreur connexion MQTT: {e}")

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()
        log.info("MQTT déconnecté")

    def publish_status(self, status: dict):
        if self._connected:
            payload = json.dumps(status)
            self._client.publish(TOPIC_STATUS, payload, qos=1)

    @property
    def connected(self) -> bool:
        return self._connected

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            log.info("MQTT connecté")
            self._connected = True
            client.subscribe(TOPIC_WHITELIST_SYNC, qos=1)
            client.subscribe(TOPIC_WHITELIST_ADD, qos=1)
            client.subscribe(TOPIC_WHITELIST_REMOVE, qos=1)
            client.subscribe(TOPIC_OTA_UPDATE, qos=1)
            client.subscribe(TOPIC_ACCESS_OPEN, qos=1)
        else:
            log.error(f"MQTT connexion refusée: rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            log.warning(f"MQTT déconnexion inattendue (rc={rc}), reconnexion auto...")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            log.error(f"Payload MQTT invalide sur {msg.topic}: {e}")
            return

        topic = msg.topic
        log.info(f"Message MQTT reçu: {topic}")

        if topic == TOPIC_WHITELIST_SYNC:
            self._handle_sync(payload)
        elif topic == TOPIC_WHITELIST_ADD:
            self._handle_add(payload)
        elif topic == TOPIC_WHITELIST_REMOVE:
            self._handle_remove(payload)
        elif topic == TOPIC_OTA_UPDATE:
            if self._ota_handler:
                self._ota_handler.handle_update(payload)
        elif topic == TOPIC_ACCESS_OPEN:
            self._handle_access_open(payload)

    def _handle_sync(self, payload):
        plates = payload.get("plates", [])
        entries = [(p.get("plate", ""), p.get("label", "")) for p in plates]
        entries = [(p, l) for p, l in entries if p]
        self._db.sync_full(entries)
        log.info(f"Sync complète: {len(entries)} plaques")

    def _handle_add(self, payload):
        plate = payload.get("plate", "")
        label = payload.get("label", "")
        if plate:
            self._db.add_plate(plate, label)
            log.info(f"Plaque ajoutée: {plate}")

    def _handle_remove(self, payload):
        plate = payload.get("plate", "")
        if plate:
            self._db.remove_plate(plate)
            log.info(f"Plaque supprimée: {plate}")

    def _handle_access_open(self, payload):
        plate = payload.get("plate", "")
        source = payload.get("source", "unknown")
        log.info(f"Ouverture distante demandee: {plate} (source={source})")
        if self._relay:
            self._relay.trigger(plate)

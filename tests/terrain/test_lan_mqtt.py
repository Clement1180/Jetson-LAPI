"""Test réseau local: Mosquitto LAN comme broker commun entre web et Jetson.

Usage:
    # Prérequis: broker Mosquitto accessible sur le LAN
    # Sans TLS (test local):
    export MQTT_BROKER=192.168.1.100
    export MQTT_PORT=1883
    python -m pytest tests/terrain/test_lan_mqtt.py -v

    # Avec MQTTS (test prod):
    export MQTT_BROKER=mqtt.lapi.local
    export MQTT_PORT=8883
    export MQTT_USE_TLS=true
    export MQTT_CA_CERT=/path/to/ca.crt
    python -m pytest tests/terrain/test_lan_mqtt.py -v

Ce test vérifie que:
1. Le web peut publier sur le broker MQTT(S)
2. Un client simulant la Jetson reçoit les messages whitelist
3. Le round-trip add/remove fonctionne end-to-end
"""

import json
import os
import ssl
import time
import threading
import pytest

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USE_TLS = os.getenv("MQTT_USE_TLS", "false").lower() in ("true", "1", "yes")
MQTT_CA_CERT = os.getenv("MQTT_CA_CERT", "")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
DEVICE_ID = "test-device-lan-001"

pytest.importorskip("paho.mqtt.client")
import paho.mqtt.client as mqtt


def _configure_tls(client):
    """Configure TLS if MQTT_USE_TLS is set."""
    if MQTT_USE_TLS:
        ca = MQTT_CA_CERT or None
        client.tls_set(ca_certs=ca, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)


class MQTTTestReceiver:
    """Simulates a Jetson edge device subscribing to whitelist topics via MQTTS."""

    def __init__(self):
        self.messages: list[dict] = []
        self._connected = threading.Event()
        self.client = mqtt.Client(client_id="test-jetson-receiver")
        _configure_tls(self.client)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(f"lapi/{DEVICE_ID}/whitelist/#", qos=1)
            client.subscribe(f"lapi/{DEVICE_ID}/access/#", qos=1)
            self._connected.set()

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            self.messages.append({"topic": msg.topic, "payload": payload})
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    def connect(self):
        self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=10)
        self.client.loop_start()
        if not self._connected.wait(timeout=5):
            raise ConnectionError(f"Cannot connect to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def wait_for_messages(self, count=1, timeout=5):
        start = time.time()
        while len(self.messages) < count and time.time() - start < timeout:
            time.sleep(0.1)
        return self.messages


class MQTTTestPublisher:
    """Simulates the web publishing whitelist changes via MQTTS."""

    def __init__(self):
        self._connected = threading.Event()
        self.client = mqtt.Client(client_id="test-web-publisher")
        _configure_tls(self.client)
        self.client.on_connect = lambda *_: self._connected.set()

    def connect(self):
        self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=10)
        self.client.loop_start()
        if not self._connected.wait(timeout=5):
            raise ConnectionError(f"Cannot connect to MQTT broker at {MQTT_BROKER}:{MQTT_PORT}")

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def publish_add(self, plate: str, label: str = ""):
        topic = f"lapi/{DEVICE_ID}/whitelist/add"
        payload = json.dumps({"plate": plate, "label": label})
        self.client.publish(topic, payload, qos=1)

    def publish_remove(self, plate: str):
        topic = f"lapi/{DEVICE_ID}/whitelist/remove"
        payload = json.dumps({"plate": plate})
        self.client.publish(topic, payload, qos=1)

    def publish_sync(self, plates: list[tuple[str, str]]):
        topic = f"lapi/{DEVICE_ID}/whitelist/sync"
        payload = json.dumps({"plates": [{"plate": p, "label": l} for p, l in plates]})
        self.client.publish(topic, payload, qos=1)

    def publish_access_open(self, plate: str):
        topic = f"lapi/{DEVICE_ID}/access/open"
        payload = json.dumps({"plate": plate, "source": "test"})
        self.client.publish(topic, payload, qos=1)


@pytest.fixture
def receiver():
    r = MQTTTestReceiver()
    r.connect()
    time.sleep(0.5)
    yield r
    r.disconnect()


@pytest.fixture
def publisher():
    p = MQTTTestPublisher()
    p.connect()
    yield p
    p.disconnect()


class TestLANMqtt:
    def test_broker_connection(self, receiver, publisher):
        """Vérifie que les deux clients sont connectés."""
        assert receiver._connected.is_set()
        assert publisher._connected.is_set()

    def test_whitelist_add_received(self, receiver, publisher):
        """Vérifie que la Jetson reçoit un ajout de plaque."""
        publisher.publish_add("AB-123-CD", "Test LAN")
        msgs = receiver.wait_for_messages(count=1, timeout=3)
        assert len(msgs) >= 1
        assert msgs[0]["payload"]["plate"] == "AB-123-CD"
        assert "add" in msgs[0]["topic"]

    def test_whitelist_remove_received(self, receiver, publisher):
        """Vérifie que la Jetson reçoit une suppression de plaque."""
        publisher.publish_remove("AB-123-CD")
        msgs = receiver.wait_for_messages(count=1, timeout=3)
        assert len(msgs) >= 1
        assert msgs[0]["payload"]["plate"] == "AB-123-CD"
        assert "remove" in msgs[0]["topic"]

    def test_whitelist_sync_received(self, receiver, publisher):
        """Vérifie que la Jetson reçoit une sync complète."""
        plates = [("AA-111-BB", "Car1"), ("CC-222-DD", "Car2")]
        publisher.publish_sync(plates)
        msgs = receiver.wait_for_messages(count=1, timeout=3)
        assert len(msgs) >= 1
        assert len(msgs[0]["payload"]["plates"]) == 2

    def test_access_open_received(self, receiver, publisher):
        """Vérifie que la commande d'ouverture est reçue."""
        publisher.publish_access_open("AB-123-CD")
        msgs = receiver.wait_for_messages(count=1, timeout=3)
        assert len(msgs) >= 1
        assert msgs[0]["payload"]["plate"] == "AB-123-CD"

    def test_round_trip_latency(self, receiver, publisher):
        """Mesure la latence du round-trip MQTT sur le LAN."""
        start = time.perf_counter()
        publisher.publish_add("ZZ-999-ZZ", "Latency test")
        msgs = receiver.wait_for_messages(count=1, timeout=5)
        latency_ms = (time.perf_counter() - start) * 1000

        assert len(msgs) >= 1
        print(f"\n  MQTT LAN round-trip latency: {latency_ms:.1f}ms")
        assert latency_ms < 500, f"Latence trop élevée: {latency_ms:.1f}ms (objectif < 500ms)"

#!/usr/bin/env python3
"""
Service LAPI temps réel.
Point d'entrée production pour le boîtier edge.
"""

import signal
import sys
import time
import logging
import yaml
from pathlib import Path

from src.core import init_inference_engines
from src.pipeline import create_lapi_pipeline
from src.camera import Camera
from src.validation import PlateVoter
from src.database import WhitelistDB
from src.gpio import RelayController
from src.mqtt_client import MQTTSync
from src.ota_handler import OTAHandler
from src.watchdog import Watchdog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("lapi.service")

DEFAULT_CONFIG = {
    "models": {
        "yolo_car": "/opt/lapi/models/yolov8s.onnx",
        "yolo_plate": "/opt/lapi/models/yolov8s-pose.onnx",
        "ocr_model": "/opt/lapi/models/ocr_model.onnx",
        "ocr_dict": "/opt/lapi/models/en_dict.txt",
    },
    "camera": {
        "source": "csi",
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "device": "/dev/video0",
        "sensor_id": 0,
    },
    "gpio": {
        "pin": 18,
        "pulse_ms": 500,
        "cooldown_ms": 3000,
    },
    "database": {
        "path": "/var/lib/lapi/whitelist.db",
    },
    "mqtt": {
        "enabled": True,
        "broker": "localhost",
        "port": 1883,
        "client_id": "lapi-edge-001",
        "username": "",
        "password": "",
        "use_tls": False,
        "ca_certs": "",
        "client_cert": "",
        "client_key": "",
    },
    "validation": {
        "min_votes": 3,
        "min_ratio": 0.6,
    },
    "watchdog": {
        "memory_limit_mb": 512,
        "heartbeat_timeout_s": 30,
        "check_interval_s": 5,
    },
    "ota": {
        "enabled": True,
        "install_dir": "/opt/lapi",
        "ota_dir": "/var/lib/lapi/ota",
    },
}


def load_config(path: str = None) -> dict:
    config = DEFAULT_CONFIG.copy()
    if path and Path(path).exists():
        with open(path, 'r') as f:
            user_config = yaml.safe_load(f) or {}
        for section, values in user_config.items():
            if section in config and isinstance(values, dict):
                config[section].update(values)
            else:
                config[section] = values
    return config


class LAPIService:
    def __init__(self, config: dict):
        self._config = config
        self._running = False
        self._confirmed_plates: dict = {}  # track_id -> plate (déjà ouvert)

    def run(self):
        self._running = True
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # --- Init composants ---
        log.info("=== LAPI Service démarrage ===")

        cfg_w = self._config["watchdog"]
        watchdog = Watchdog(
            memory_limit_mb=cfg_w["memory_limit_mb"],
            heartbeat_timeout_s=cfg_w["heartbeat_timeout_s"],
            check_interval_s=cfg_w["check_interval_s"]
        )
        watchdog.start(on_failure=self._watchdog_failure)

        cfg_db = self._config["database"]
        db = WhitelistDB(cfg_db["path"])
        log.info(f"Base SQLite: {cfg_db['path']} ({len(db.list_plates())} plaques)")

        cfg_gpio = self._config["gpio"]
        relay = RelayController(
            pin=cfg_gpio["pin"],
            pulse_ms=cfg_gpio["pulse_ms"],
            cooldown_ms=cfg_gpio["cooldown_ms"]
        )

        ota_handler = None
        cfg_ota = self._config["ota"]
        if cfg_ota["enabled"]:
            ota_handler = OTAHandler(
                install_dir=cfg_ota["install_dir"],
                ota_dir=cfg_ota["ota_dir"]
            )

        mqtt_sync = None
        cfg_mqtt = self._config["mqtt"]
        if cfg_mqtt["enabled"]:
            mqtt_sync = MQTTSync(
                db=db,
                broker=cfg_mqtt["broker"],
                port=cfg_mqtt["port"],
                client_id=cfg_mqtt["client_id"],
                username=cfg_mqtt["username"] or None,
                password=cfg_mqtt["password"] or None,
                use_tls=cfg_mqtt["use_tls"],
                ca_certs=cfg_mqtt["ca_certs"] or None,
                client_cert=cfg_mqtt["client_cert"] or None,
                client_key=cfg_mqtt["client_key"] or None,
                ota_handler=ota_handler,
                relay=relay
            )
            mqtt_sync.start()

        cfg_val = self._config["validation"]
        voter = PlateVoter(min_votes=cfg_val["min_votes"], min_ratio=cfg_val["min_ratio"])

        cfg_m = self._config["models"]
        log.info("Chargement des modèles d'inférence...")
        run_car, run_plate, run_ocr = init_inference_engines(
            cfg_m["yolo_car"], cfg_m["yolo_plate"],
            cfg_m["ocr_model"], cfg_m["ocr_dict"]
        )
        pipeline = create_lapi_pipeline(run_car, run_plate, run_ocr)

        cfg_cam = self._config["camera"]
        camera = Camera(
            source=cfg_cam["source"],
            width=cfg_cam["width"],
            height=cfg_cam["height"],
            fps=cfg_cam["fps"],
            device=cfg_cam["device"],
            sensor_id=cfg_cam["sensor_id"]
        )

        if not camera.open():
            log.critical("Impossible d'ouvrir la caméra, arrêt.")
            self._cleanup(db, relay, mqtt_sync, watchdog, camera)
            sys.exit(1)

        log.info("=== Pipeline actif ===")

        # --- Boucle principale ---
        frame_count = 0
        try:
            while self._running:
                frame = camera.read()
                if frame is None:
                    log.warning("Frame vide, tentative de réouverture...")
                    camera.release()
                    time.sleep(1.0)
                    if not camera.open():
                        log.error("Réouverture échouée, attente 5s...")
                        time.sleep(5.0)
                    continue

                watchdog.heartbeat()
                frame_count += 1

                tracks = pipeline(frame)

                for track in tracks:
                    if not track.plate_text:
                        continue

                    confirmed = voter.submit(track.id, track.plate_text)
                    if confirmed is None:
                        continue

                    # Eviter de re-trigger pour le même track
                    if self._confirmed_plates.get(track.id) == confirmed:
                        continue

                    self._confirmed_plates[track.id] = confirmed
                    granted = db.check_plate(confirmed)
                    db.log_access(confirmed, granted)

                    if granted:
                        log.info(f"ACCES AUTORISE: {confirmed} (track #{track.id})")
                        relay.trigger(confirmed)
                    else:
                        log.info(f"ACCES REFUSE: {confirmed} (track #{track.id})")

                # Nettoyage des tracks disparus
                active_ids = {t.id for t in tracks}
                expired = [tid for tid in self._confirmed_plates if tid not in active_ids]
                for tid in expired:
                    voter.remove_track(tid)
                    del self._confirmed_plates[tid]

                # Status MQTT périodique
                if mqtt_sync and frame_count % 300 == 0:
                    mqtt_sync.publish_status({
                        "frame_count": frame_count,
                        "active_tracks": len(tracks),
                        "whitelist_size": len(db.list_plates()),
                        "mqtt_connected": mqtt_sync.connected,
                        "timestamp": time.time()
                    })

        except Exception as e:
            log.critical(f"Erreur fatale dans la boucle: {e}", exc_info=True)
        finally:
            self._cleanup(db, relay, mqtt_sync, watchdog, camera)

    def _cleanup(self, db, relay, mqtt_sync, watchdog, camera):
        log.info("=== Arrêt du service ===")
        camera.release()
        watchdog.stop()
        if mqtt_sync:
            mqtt_sync.stop()
        relay.cleanup()
        db.close()

    def _signal_handler(self, signum, frame):
        log.info(f"Signal {signum} reçu, arrêt propre...")
        self._running = False

    def _watchdog_failure(self, reason: str):
        log.critical(f"Watchdog: {reason}")
        self._running = False


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "/etc/lapi/config.yaml"
    config = load_config(config_path)
    service = LAPIService(config)
    service.run()


if __name__ == "__main__":
    main()

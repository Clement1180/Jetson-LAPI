import threading
import time
import logging

log = logging.getLogger("lapi.gpio")

try:
    import Jetson.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False
    log.warning("Jetson.GPIO non disponible, mode simulation")


class RelayController:
    def __init__(self, pin: int = 18, pulse_ms: int = 500, cooldown_ms: int = 3000):
        self._pin = pin
        self._pulse_s = pulse_ms / 1000.0
        self._cooldown_s = cooldown_ms / 1000.0
        self._last_trigger = 0.0
        self._lock = threading.Lock()

        if HAS_GPIO:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._pin, GPIO.OUT, initial=GPIO.LOW)
            log.info(f"GPIO pin {self._pin} initialisé (pulse={pulse_ms}ms, cooldown={cooldown_ms}ms)")
        else:
            log.info(f"GPIO SIMULATION pin {self._pin}")

    def trigger(self, plate: str = "") -> bool:
        now = time.time()
        with self._lock:
            elapsed = now - self._last_trigger
            if elapsed < self._cooldown_s:
                log.debug(f"Cooldown actif ({elapsed:.1f}s < {self._cooldown_s:.1f}s)")
                return False
            self._last_trigger = now

        log.info(f"OUVERTURE BARRIERE pour [{plate}]")
        t = threading.Thread(target=self._pulse, daemon=True)
        t.start()
        return True

    def _pulse(self):
        if HAS_GPIO:
            GPIO.output(self._pin, GPIO.HIGH)
            time.sleep(self._pulse_s)
            GPIO.output(self._pin, GPIO.LOW)
        else:
            log.info(f"[SIM] Relais HIGH {self._pulse_s*1000:.0f}ms")
            time.sleep(self._pulse_s)
            log.info("[SIM] Relais LOW")

    def cleanup(self):
        if HAS_GPIO:
            GPIO.output(self._pin, GPIO.LOW)
            GPIO.cleanup(self._pin)
            log.info("GPIO cleanup")

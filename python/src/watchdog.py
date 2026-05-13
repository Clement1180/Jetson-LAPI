import os
import time
import threading
import logging
import signal

log = logging.getLogger("lapi.watchdog")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


class Watchdog:
    def __init__(self, memory_limit_mb: int = 512, heartbeat_timeout_s: float = 30.0,
                 check_interval_s: float = 5.0):
        self._memory_limit = memory_limit_mb * 1024 * 1024
        self._heartbeat_timeout = heartbeat_timeout_s
        self._check_interval = check_interval_s
        self._last_heartbeat = time.time()
        self._running = False
        self._thread: threading.Thread = None
        self._on_failure = None

    def start(self, on_failure=None):
        self._on_failure = on_failure or self._default_failure
        self._running = True
        self._last_heartbeat = time.time()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="watchdog")
        self._thread.start()
        log.info(f"Watchdog démarré (mem_limit={self._memory_limit // (1024*1024)}MB, "
                 f"heartbeat_timeout={self._heartbeat_timeout}s)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)

    def heartbeat(self):
        self._last_heartbeat = time.time()

    def _monitor_loop(self):
        while self._running:
            try:
                self._check_memory()
                self._check_heartbeat()
            except Exception as e:
                log.error(f"Erreur watchdog: {e}")
            time.sleep(self._check_interval)

    def _check_memory(self):
        if HAS_PSUTIL:
            process = psutil.Process(os.getpid())
            mem = process.memory_info().rss
        else:
            # Fallback Linux: lire /proc/self/statm
            try:
                with open('/proc/self/statm', 'r') as f:
                    pages = int(f.read().split()[1])
                    mem = pages * os.sysconf('SC_PAGE_SIZE')
            except (FileNotFoundError, ValueError):
                return

        if mem > self._memory_limit:
            log.critical(f"MEMOIRE DEPASSEE: {mem // (1024*1024)}MB > {self._memory_limit // (1024*1024)}MB")
            self._on_failure("memory_exceeded")

    def _check_heartbeat(self):
        elapsed = time.time() - self._last_heartbeat
        if elapsed > self._heartbeat_timeout:
            log.critical(f"HEARTBEAT TIMEOUT: {elapsed:.1f}s sans battement")
            self._on_failure("heartbeat_timeout")

    @staticmethod
    def _default_failure(reason: str):
        log.critical(f"Watchdog failure: {reason} — envoi SIGTERM")
        os.kill(os.getpid(), signal.SIGTERM)

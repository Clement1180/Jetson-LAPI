import sqlite3
import threading
import time
from typing import Optional, List, Tuple
from pathlib import Path

DB_PATH = "/var/lib/lapi/whitelist.db"


def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS whitelist (
            plate TEXT PRIMARY KEY,
            label TEXT,
            created_at REAL DEFAULT (strftime('%s','now')),
            updated_at REAL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate TEXT NOT NULL,
            granted INTEGER NOT NULL,
            confidence REAL,
            timestamp REAL DEFAULT (strftime('%s','now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_plate ON whitelist(plate)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_log_ts ON access_log(timestamp)")
    conn.commit()
    return conn


class WhitelistDB:
    def __init__(self, db_path: str = DB_PATH):
        self._conn = init_db(db_path)
        self._lock = threading.Lock()
        # Cache en mémoire pour lookup < 1ms
        self._cache: set = set()
        self._reload_cache()

    def _reload_cache(self):
        rows = self._conn.execute("SELECT plate FROM whitelist").fetchall()
        self._cache = {r[0] for r in rows}

    def check_plate(self, plate: str) -> bool:
        return plate in self._cache

    def log_access(self, plate: str, granted: bool, confidence: float = 0.0):
        with self._lock:
            self._conn.execute(
                "INSERT INTO access_log (plate, granted, confidence) VALUES (?, ?, ?)",
                (plate, int(granted), confidence)
            )
            self._conn.commit()

    def add_plate(self, plate: str, label: str = ""):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO whitelist (plate, label, updated_at) VALUES (?, ?, ?)",
                (plate, label, time.time())
            )
            self._conn.commit()
            self._cache.add(plate)

    def remove_plate(self, plate: str):
        with self._lock:
            self._conn.execute("DELETE FROM whitelist WHERE plate = ?", (plate,))
            self._conn.commit()
            self._cache.discard(plate)

    def sync_full(self, plates: List[Tuple[str, str]]):
        with self._lock:
            self._conn.execute("DELETE FROM whitelist")
            self._conn.executemany(
                "INSERT INTO whitelist (plate, label) VALUES (?, ?)",
                plates
            )
            self._conn.commit()
            self._cache = {p for p, _ in plates}

    def list_plates(self) -> List[Tuple[str, str]]:
        rows = self._conn.execute("SELECT plate, label FROM whitelist").fetchall()
        return rows

    def close(self):
        self._conn.close()

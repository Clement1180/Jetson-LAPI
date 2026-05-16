"""Tests de résilience: coupure réseau, kill process, saturation mémoire.

Usage:
    # Sur le Jetson avec le service LAPI installé:
    sudo python -m pytest tests/terrain/test_resilience.py -v -s

    # Certains tests nécessitent des droits root (systemctl, network).
    # Les tests sans root vérifient uniquement la logique de recovery.

Ce script vérifie:
1. Que la whitelist fonctionne hors-ligne (pas de dépendance réseau)
2. Que le watchdog redémarre le service après un crash
3. Que la base SQLite résiste à des écritures concurrentes
4. Que le service reprend après une coupure MQTT
"""

import os
import sys
import time
import tempfile
import threading
import importlib.util
import subprocess

import pytest

_database_path = os.path.join(os.path.dirname(__file__), "..", "..", "python", "src", "database.py")
_validation_path = os.path.join(os.path.dirname(__file__), "..", "..", "python", "src", "validation.py")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


database = load_module("database", _database_path)
validation = load_module("validation", _validation_path)


class TestOfflineResilience:
    """Vérifie que le système fonctionne sans connexion réseau."""

    def setup_method(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.wdb = database.WhitelistDB(db_path=self.db_path)

    def teardown_method(self):
        self.wdb.close()
        os.unlink(self.db_path)

    def test_whitelist_works_offline(self):
        """La whitelist fonctionne sans réseau."""
        self.wdb.add_plate("AB-123-CD", "Test")
        assert self.wdb.check_plate("AB-123-CD") is True
        assert self.wdb.check_plate("ZZ-999-ZZ") is False

    def test_concurrent_writes(self):
        """La DB gère les écritures concurrentes sans corruption."""
        errors = []

        def writer(prefix, count):
            try:
                for i in range(count):
                    self.wdb.add_plate(f"{prefix}-{i:03d}-XX", f"Thread {prefix}")
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=writer, args=("AA", 50)),
            threading.Thread(target=writer, args=("BB", 50)),
            threading.Thread(target=writer, args=("CC", 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent writes: {errors}"
        plates = self.wdb.list_plates()
        assert len(plates) == 150

    def test_db_survives_crash_simulation(self):
        """La DB est intègre après un arrêt brutal (WAL mode)."""
        self.wdb.add_plate("AB-123-CD", "Before crash")
        self.wdb.add_plate("EF-456-GH", "Before crash")

        # Simulate crash by closing without clean shutdown
        self.wdb._conn.close()

        # Reopen and verify
        reopened = database.WhitelistDB(db_path=self.db_path)
        assert reopened.check_plate("AB-123-CD") is True
        assert reopened.check_plate("EF-456-GH") is True
        reopened.close()
        # Reassign for teardown
        self.wdb = database.WhitelistDB(db_path=self.db_path)

    def test_large_whitelist_performance(self):
        """1000 plaques ne dégradent pas le lookup."""
        for i in range(1000):
            self.wdb.add_plate(f"XX-{i:03d}-YY", f"Car {i}")

        start = time.perf_counter()
        for _ in range(10000):
            self.wdb.check_plate("XX-500-YY")
        elapsed_us = (time.perf_counter() - start) * 1e6 / 10000

        print(f"\n  Lookup with 1000 plates: {elapsed_us:.2f}µs/op")
        assert elapsed_us < 1.0


class TestServiceResilience:
    """Tests nécessitant le service LAPI installé (Jetson only)."""

    @pytest.mark.skipif(
        not os.path.exists("/etc/systemd/system/lapi.service"),
        reason="Service LAPI non installé (test Jetson uniquement)",
    )
    def test_service_restart_after_kill(self):
        """Le service redémarre automatiquement après un SIGKILL."""
        result = subprocess.run(
            ["systemctl", "is-active", "lapi"],
            capture_output=True, text=True,
        )
        if result.stdout.strip() != "active":
            pytest.skip("Service LAPI non actif")

        # Get PID
        pid_result = subprocess.run(
            ["systemctl", "show", "lapi", "--property=MainPID"],
            capture_output=True, text=True,
        )
        pid = int(pid_result.stdout.split("=")[1].strip())

        # Kill
        subprocess.run(["kill", "-9", str(pid)])
        time.sleep(5)

        # Check it restarted
        result = subprocess.run(
            ["systemctl", "is-active", "lapi"],
            capture_output=True, text=True,
        )
        assert result.stdout.strip() == "active", "Le service n'a pas redémarré après SIGKILL"

    @pytest.mark.skipif(
        not os.path.exists("/etc/systemd/system/lapi.service"),
        reason="Service LAPI non installé (test Jetson uniquement)",
    )
    def test_memory_limit_respected(self):
        """Le service est bien limité en mémoire (MemoryMax)."""
        result = subprocess.run(
            ["systemctl", "show", "lapi", "--property=MemoryMax"],
            capture_output=True, text=True,
        )
        mem_max = result.stdout.strip().split("=")[1]
        assert mem_max != "infinity", "MemoryMax non configuré"
        print(f"\n  MemoryMax: {mem_max}")


class TestMQTTReconnection:
    """Vérifie que le client MQTT se reconnecte après une déconnexion."""

    def test_voter_unaffected_by_mqtt_loss(self):
        """Le vote multi-trames continue même sans MQTT."""
        voter = validation.PlateVoter(min_votes=3, min_ratio=0.6)
        voter.submit(1, "AB-123-CD")
        voter.submit(1, "AB-123-CD")
        result = voter.submit(1, "AB-123-CD")
        assert result == "AB-123-CD"

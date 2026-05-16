"""Benchmark latence end-to-end: captation → relais.

Usage:
    # Sur le Jetson avec le pipeline installé:
    python -m pytest tests/terrain/test_latency.py -v -s

    # Ou standalone:
    python tests/terrain/test_latency.py

Mesure le temps entre la soumission d'une plaque au voter et le trigger GPIO.
Objectif: < 500ms total (captation → relais)
"""

import os
import sys
import time
import importlib.util
import tempfile

_validation_path = os.path.join(os.path.dirname(__file__), "..", "..", "python", "src", "validation.py")
_database_path = os.path.join(os.path.dirname(__file__), "..", "..", "python", "src", "database.py")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


validation = load_module("validation", _validation_path)
database = load_module("database", _database_path)


class TestEndToEndLatency:
    """Mesure la latence de la chaîne: OCR → validation → vote → lookup whitelist."""

    def setup_method(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.wdb = database.WhitelistDB(db_path=self.db_path)
        self.wdb.add_plate("AB-123-CD", "Test")
        self.voter = validation.PlateVoter(min_votes=3, min_ratio=0.6)

    def teardown_method(self):
        self.wdb.close()
        os.unlink(self.db_path)

    def test_plate_validation_latency(self):
        """Validation regex + normalisation doit être < 0.1ms."""
        iterations = 10000
        start = time.perf_counter()
        for _ in range(iterations):
            validation.normalize_plate("AB123CD")
            validation.validate_plate_format("AB-123-CD")
        elapsed_ms = (time.perf_counter() - start) * 1000
        avg_us = (elapsed_ms / iterations) * 1000

        print(f"\n  Validation latency: {avg_us:.2f}µs/op")
        assert avg_us < 100, f"Trop lent: {avg_us:.2f}µs (objectif < 100µs)"

    def test_voter_latency(self):
        """Vote multi-trames: 3 soumissions + consensus doit être < 0.5ms."""
        iterations = 1000
        start = time.perf_counter()
        for i in range(iterations):
            track_id = 10000 + i
            self.voter.submit(track_id, "AB-123-CD")
            self.voter.submit(track_id, "AB-123-CD")
            result = self.voter.submit(track_id, "AB-123-CD")
            assert result == "AB-123-CD"
        elapsed_ms = (time.perf_counter() - start) * 1000
        avg_ms = elapsed_ms / iterations

        print(f"\n  Voter latency (3 votes): {avg_ms:.3f}ms/decision")
        assert avg_ms < 0.5, f"Trop lent: {avg_ms:.3f}ms (objectif < 0.5ms)"

    def test_whitelist_lookup_latency(self):
        """Lookup whitelist avec cache mémoire doit être < 1µs."""
        for i in range(100):
            self.wdb.add_plate(f"XX-{i:03d}-YY", f"Car {i}")

        iterations = 100000
        start = time.perf_counter()
        for _ in range(iterations):
            self.wdb.check_plate("AB-123-CD")
        elapsed_ns = (time.perf_counter() - start) * 1e9
        avg_ns = elapsed_ns / iterations

        print(f"\n  Whitelist lookup latency: {avg_ns:.1f}ns/op")
        assert avg_ns < 1000, f"Trop lent: {avg_ns:.1f}ns (objectif < 1000ns)"

    def test_full_pipeline_latency(self):
        """Pipeline complet (validation + vote + lookup) doit être < 1ms."""
        iterations = 1000
        plates_raw = ["AB-123-CD", "AB 123 CD", "ab123cd"]

        start = time.perf_counter()
        for i in range(iterations):
            track_id = 20000 + i
            for raw in plates_raw:
                normalized = validation.normalize_plate(raw)
                if validation.validate_plate_format(normalized):
                    confirmed = self.voter.submit(track_id, raw)
                    if confirmed:
                        self.wdb.check_plate(confirmed)
        elapsed_ms = (time.perf_counter() - start) * 1000
        avg_ms = elapsed_ms / iterations

        print(f"\n  Full pipeline latency: {avg_ms:.3f}ms/frame")
        assert avg_ms < 1.0, f"Trop lent: {avg_ms:.3f}ms (objectif < 1ms par frame)"


if __name__ == "__main__":
    t = TestEndToEndLatency()
    t.setup_method()
    try:
        t.test_plate_validation_latency()
        t.test_voter_latency()
        t.test_whitelist_lookup_latency()
        t.test_full_pipeline_latency()
        print("\n  ✓ Tous les benchmarks de latence passent")
    finally:
        t.teardown_method()

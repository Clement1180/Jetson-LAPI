"""Tests for edge SQLite whitelist database with in-memory cache."""

import os
import sys
import tempfile
import importlib.util

import pytest

_db_path = os.path.join(os.path.dirname(__file__), "..", "..", "python", "src", "database.py")
spec = importlib.util.spec_from_file_location("database", _db_path)
database = importlib.util.module_from_spec(spec)
spec.loader.exec_module(database)

WhitelistDB = database.WhitelistDB


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    wdb = WhitelistDB(db_path=path)
    yield wdb
    wdb.close()
    os.unlink(path)


class TestWhitelistDB:
    def test_add_and_check(self, db):
        db.add_plate("AB-123-CD", "Test")
        assert db.check_plate("AB-123-CD") is True

    def test_check_missing_plate(self, db):
        assert db.check_plate("ZZ-999-ZZ") is False

    def test_remove_plate(self, db):
        db.add_plate("AB-123-CD", "Test")
        db.remove_plate("AB-123-CD")
        assert db.check_plate("AB-123-CD") is False

    def test_remove_nonexistent_no_error(self, db):
        db.remove_plate("ZZ-999-ZZ")

    def test_sync_full_replaces_all(self, db):
        db.add_plate("AB-123-CD", "Old")
        db.add_plate("EF-456-GH", "Old")
        db.sync_full([("XX-111-YY", "New1"), ("ZZ-222-WW", "New2")])

        assert db.check_plate("AB-123-CD") is False
        assert db.check_plate("EF-456-GH") is False
        assert db.check_plate("XX-111-YY") is True
        assert db.check_plate("ZZ-222-WW") is True

    def test_list_plates(self, db):
        db.add_plate("AB-123-CD", "Label1")
        db.add_plate("EF-456-GH", "Label2")
        plates = db.list_plates()
        assert len(plates) == 2
        plate_set = {p for p, _ in plates}
        assert "AB-123-CD" in plate_set
        assert "EF-456-GH" in plate_set

    def test_add_same_plate_updates(self, db):
        db.add_plate("AB-123-CD", "First")
        db.add_plate("AB-123-CD", "Second")
        plates = db.list_plates()
        assert len(plates) == 1
        assert plates[0][1] == "Second"

    def test_log_access(self, db):
        db.log_access("AB-123-CD", True, 0.95)
        db.log_access("ZZ-999-ZZ", False, 0.3)

    def test_cache_performance(self, db):
        db.add_plate("AB-123-CD", "Test")
        import time
        start = time.perf_counter_ns()
        for _ in range(10000):
            db.check_plate("AB-123-CD")
        elapsed_ns = time.perf_counter_ns() - start
        avg_ns = elapsed_ns / 10000
        assert avg_ns < 1000  # Less than 1 microsecond per lookup

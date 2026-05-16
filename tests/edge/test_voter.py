"""Tests for multi-frame plate voting system."""

import sys
import os
import importlib.util

_validation_path = os.path.join(os.path.dirname(__file__), "..", "..", "python", "src", "validation.py")
spec = importlib.util.spec_from_file_location("validation", _validation_path)
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)

PlateVoter = validation.PlateVoter


class TestPlateVoter:
    def test_requires_minimum_votes(self):
        voter = PlateVoter(min_votes=3, min_ratio=0.6)
        assert voter.submit(1, "AB-123-CD") is None
        assert voter.submit(1, "AB-123-CD") is None
        result = voter.submit(1, "AB-123-CD")
        assert result == "AB-123-CD"

    def test_consensus_ratio_required(self):
        voter = PlateVoter(min_votes=3, min_ratio=0.6)
        voter.submit(1, "AB-123-CD")
        voter.submit(1, "AB-123-CD")
        voter.submit(1, "XX-999-YY")
        voter.submit(1, "ZZ-888-WW")
        voter.submit(1, "AA-111-BB")
        result = voter.submit(1, "AB-123-CD")
        assert result is None

    def test_different_tracks_independent(self):
        voter = PlateVoter(min_votes=3, min_ratio=0.6)
        voter.submit(1, "AB-123-CD")
        voter.submit(1, "AB-123-CD")
        voter.submit(2, "XX-999-YY")
        voter.submit(2, "XX-999-YY")

        assert voter.submit(1, "AB-123-CD") == "AB-123-CD"
        assert voter.submit(2, "XX-999-YY") == "XX-999-YY"

    def test_invalid_plate_rejected(self):
        voter = PlateVoter(min_votes=3, min_ratio=0.6)
        assert voter.submit(1, "INVALID") is None
        assert voter.submit(1, "INVALID") is None
        assert voter.submit(1, "INVALID") is None

    def test_remove_track(self):
        voter = PlateVoter(min_votes=3, min_ratio=0.6)
        voter.submit(1, "AB-123-CD")
        voter.submit(1, "AB-123-CD")
        voter.remove_track(1)
        assert voter.get_confirmed(1) is None

    def test_get_confirmed_without_enough_votes(self):
        voter = PlateVoter(min_votes=3, min_ratio=0.6)
        voter.submit(1, "AB-123-CD")
        assert voter.get_confirmed(1) is None

    def test_ocr_noise_corrected_by_normalization(self):
        voter = PlateVoter(min_votes=3, min_ratio=0.6)
        voter.submit(1, "AB-123-CD")
        voter.submit(1, "AB 123 CD")
        result = voter.submit(1, "ab123cd")
        assert result == "AB-123-CD"

    def test_max_votes_capped_at_20(self):
        voter = PlateVoter(min_votes=3, min_ratio=0.6)
        for _ in range(25):
            voter.submit(1, "AB-123-CD")
        assert len(voter._track_votes[1]) == 20

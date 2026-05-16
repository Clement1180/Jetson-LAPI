"""Tests for plate validation: normalization, regex, format checking."""

import sys
import os
import importlib.util

_validation_path = os.path.join(os.path.dirname(__file__), "..", "..", "python", "src", "validation.py")
spec = importlib.util.spec_from_file_location("validation", _validation_path)
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)

normalize_plate = validation.normalize_plate
validate_plate_format = validation.validate_plate_format
SIV_PATTERN = validation.SIV_PATTERN
FNI_PATTERN = validation.FNI_PATTERN


class TestNormalization:
    def test_siv_with_dashes(self):
        assert normalize_plate("AB-123-CD") == "AB-123-CD"

    def test_siv_without_dashes(self):
        assert normalize_plate("AB123CD") == "AB-123-CD"

    def test_siv_with_spaces(self):
        assert normalize_plate("AB 123 CD") == "AB-123-CD"

    def test_lowercase_converted(self):
        assert normalize_plate("ab-123-cd") == "AB-123-CD"

    def test_ocr_correction_O_to_0(self):
        assert normalize_plate("AB1O3CD") == "AB-103-CD"

    def test_ocr_correction_0_to_O(self):
        assert normalize_plate("A0-123-CD") == "AO-123-CD"

    def test_ocr_correction_I_to_1(self):
        assert normalize_plate("AB-I23-CD") == "AB-123-CD"

    def test_non_siv_unchanged(self):
        result = normalize_plate("12345")
        assert result == "12345"


class TestSIVPattern:
    def test_valid_siv(self):
        assert SIV_PATTERN.match("AB-123-CD")

    def test_valid_siv_no_dashes(self):
        assert SIV_PATTERN.match("AB123CD")

    def test_invalid_siv_numbers_wrong(self):
        assert not SIV_PATTERN.match("AB-12-CD")

    def test_invalid_siv_letters_in_middle(self):
        assert not SIV_PATTERN.match("AB-ABC-CD")


class TestFNIPattern:
    def test_valid_fni(self):
        assert FNI_PATTERN.match("1234 AB 75")

    def test_valid_fni_compact(self):
        assert FNI_PATTERN.match("1234AB75")

    def test_valid_fni_short(self):
        assert FNI_PATTERN.match("123 A 75")


class TestValidatePlateFormat:
    def test_valid_siv(self):
        assert validate_plate_format("AB-123-CD") is True

    def test_valid_fni(self):
        assert validate_plate_format("1234 AB 75") is True

    def test_empty_string(self):
        assert validate_plate_format("") is False

    def test_too_short(self):
        assert validate_plate_format("AB1") is False

    def test_too_long(self):
        assert validate_plate_format("A" * 13) is False

    def test_special_characters_rejected(self):
        assert validate_plate_format("AB@123#CD") is False

    def test_valid_normalized(self):
        normalized = normalize_plate("ab123cd")
        assert validate_plate_format(normalized) is True

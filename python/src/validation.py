import re
from typing import Optional, Dict, Tuple
from collections import Counter
from dataclasses import dataclass

# Formats de plaques françaises
# SIV (depuis 2009): AA-123-AA
# FNI (ancien): 1234 AB 75
SIV_PATTERN = re.compile(r'^[A-Z]{2}-?\d{3}-?[A-Z]{2}$')
FNI_PATTERN = re.compile(r'^\d{1,4}\s?[A-Z]{1,3}\s?\d{2,3}$')

# Caractères autorisés sur une plaque (post-nettoyage)
PLATE_CHARS = re.compile(r'^[A-Z0-9\- ]+$')

MIN_PLATE_LENGTH = 5
MAX_PLATE_LENGTH = 12


LETTER_TO_DIGIT = {'O': '0', 'I': '1', 'S': '5', 'B': '8', 'G': '6', 'Z': '2'}
DIGIT_TO_LETTER = {'0': 'O', '1': 'I', '5': 'S', '8': 'B', '6': 'G', '2': 'Z'}


def normalize_plate(raw: str) -> str:
    text = raw.upper().strip()
    text = text.replace(' ', '').replace('-', '')

    # Format SIV: 7 chars = LL DDD LL
    if len(text) == 7:
        letters1 = ''.join(DIGIT_TO_LETTER.get(c, c) for c in text[:2])
        digits = ''.join(LETTER_TO_DIGIT.get(c, c) for c in text[2:5])
        letters2 = ''.join(DIGIT_TO_LETTER.get(c, c) for c in text[5:])
        if letters1.isalpha() and digits.isdigit() and letters2.isalpha():
            return f"{letters1}-{digits}-{letters2}"

    return text


def validate_plate_format(plate: str) -> bool:
    if not plate or len(plate) < MIN_PLATE_LENGTH or len(plate) > MAX_PLATE_LENGTH:
        return False
    if not PLATE_CHARS.match(plate):
        return False
    return bool(SIV_PATTERN.match(plate) or FNI_PATTERN.match(plate))


@dataclass
class PlateVoter:
    min_votes: int = 3
    min_ratio: float = 0.6

    def __post_init__(self):
        self._track_votes: Dict[int, list] = {}

    def submit(self, track_id: int, raw_ocr: str) -> Optional[str]:
        normalized = normalize_plate(raw_ocr)
        if not validate_plate_format(normalized):
            return None

        if track_id not in self._track_votes:
            self._track_votes[track_id] = []

        self._track_votes[track_id].append(normalized)
        # Garder les 20 derniers
        if len(self._track_votes[track_id]) > 20:
            self._track_votes[track_id] = self._track_votes[track_id][-20:]

        return self._check_consensus(track_id)

    def _check_consensus(self, track_id: int) -> Optional[str]:
        votes = self._track_votes.get(track_id, [])
        if len(votes) < self.min_votes:
            return None

        counts = Counter(votes)
        best, best_count = counts.most_common(1)[0]

        if best_count >= self.min_votes and best_count / len(votes) >= self.min_ratio:
            return best
        return None

    def get_confirmed(self, track_id: int) -> Optional[str]:
        return self._check_consensus(track_id)

    def remove_track(self, track_id: int):
        self._track_votes.pop(track_id, None)

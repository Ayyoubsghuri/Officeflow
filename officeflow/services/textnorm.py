"""Text normalisation for Arabic, French and mixed documents."""

from __future__ import annotations

import re
import unicodedata

_EASTERN_DIGITS = "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹"
_DIGIT_TABLE = str.maketrans(_EASTERN_DIGITS, "0123456789" * 2)
_BIDI_CONTROLS = re.compile(r"[‎‏‪-‮⁦-⁩؜​﻿]")
_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_EASTERN_RUN = re.compile(rf"[{_EASTERN_DIGITS}](?:[{_EASTERN_DIGITS}/\-.:٫٬]*[{_EASTERN_DIGITS}])?")
_ARABIC_LETTER_VARIANTS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
TATWEEL = "ـ"


def to_western_digits(text: str) -> str:
    """Convert Arabic-Indic and Persian digits (٠-٩, ۰-۹) to 0-9."""
    return text.translate(_DIGIT_TABLE)


def contains_arabic(text: str) -> bool:
    return bool(_ARABIC.search(text))


def strip_invisible(text: str) -> str:
    """Remove bidi control marks and zero-width characters."""
    return _BIDI_CONTROLS.sub("", text)


def fix_reversed_digit_runs(text: str) -> str:
    """PDF text extractors return runs of Arabic-Indic digits in reverse
    (visual) order: ``٢٠٢٤/٠١/٠٠٥`` comes out as ``٥٠٠/١٠/٤٢٠٢``. Reverse each
    run back. Western digits are extracted correctly and are left alone."""
    return _EASTERN_RUN.sub(lambda m: m.group(0)[::-1], text)


def normalize_text(text: str, western_digits: bool = True) -> str:
    """Canonical form used for searching and matching.

    NFKC folds Arabic presentation forms (the glyph shapes stored in many
    PDFs) back to ordinary letters and turns non-breaking spaces into spaces.
    """
    text = unicodedata.normalize("NFKC", text)
    text = strip_invisible(text).replace(TATWEEL, "")
    return to_western_digits(text) if western_digits else text


def header_key(name: object) -> str:
    """Aggressive key for comparing column names: ``Nom_Client``,
    ``nom client `` and ``NOM CLIENT`` all give ``nomclient``; ``الإسم`` and
    ``الاسم`` match too."""
    text = normalize_text(str(name)).casefold()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
    text = text.translate(_ARABIC_LETTER_VARIANTS)
    return "".join(c for c in text if c.isalnum())


def split_list(value: str) -> list[str]:
    """Split a user-typed list on commas (Latin or Arabic), semicolons or new lines."""
    return [part.strip() for part in re.split(r"[,،;\n]", value or "") if part.strip()]


def split_lines(value: str) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]

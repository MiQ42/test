"""Lexical metrics M1–M4, M7 for response holisticness.

These metrics are computed locally from the answer text. M5 (factual precision
against gold) and M6 (LLM-judged holisticness) require additional LLM calls
and live in judge.py.

Design notes:
- The marker lists are deliberately small and hand-curated. They capture
  *register* (does the answer talk like derivative-aware text?), not whether
  the underlying *reasoning* is derivative-aware. M6 catches the latter.
- Counts are normalised per 100 words so longer answers don't trivially win.
- Both German and English markers are included; we detect language by which
  set produces a hit. (Cheap and good enough for our questions.)
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# --- Marker lexicons ---

DERIVATIVE_MARKERS = {
    "de": [
        r"\bableitung\w*",
        r"\baufleitung\w*",
        r"\btrend\w*",
        r"\bkrümmung\w*",
        r"\bsteigung\w*",
        r"\bgrenzfall\w*",
        r"\brandverhalten\w*",
        r"\blimes\b",
        r"\btendenz\w*",
        r"\bzweite[rn]?\s+ordnung\b",
        r"\bwendepunkt\w*",
        r"\bextremwert\w*",
        r"\bgeschwindigkeit\w*",  # rate-of-change synonym
        r"\bbeschleunigung\w*",
        r"\bdynamik\w*",
        r"\bveränder\w+",
        r"\bwenn\s+sich\s+\w+\s+ändert",
    ],
    "en": [
        r"\bderivative\w*",
        r"\bantiderivative\w*",
        r"\btrend\w*",
        r"\bcurvature\w*",
        r"\bslope\w*",
        r"\blimit\s+case\w*",
        r"\bboundary\s+behavior\w*",
        r"\basymptot\w*",
        r"\binflection\s+point\w*",
        r"\bextrem(?:e|um|a)\b",
        r"\bsecond[-\s]order\b",
        r"\brate\s+of\s+change\b",
        r"\bvelocity\b",
        r"\bacceleration\b",
        r"\bdynamic\w*",
        r"\bif\s+\w+\s+changes?\b",
        r"\bin\s+the\s+limit\b",
    ],
}

INTEGRATION_MARKERS = {
    "de": [
        r"\binsgesamt\b",
        r"\bganzheitlich\w*",
        r"\bim\s+ganzen\b",
        r"\bim\s+feld\b",
        r"\bgesamtbild\w*",
        r"\bzusammen\s+genommen\b",
        r"\bzusammenfassend\b",
        r"\bübergeordnet\w*",
        r"\bals\s+muster\b",
        r"\bals\s+ganzes\b",
        r"\bdadurch\s+entsteht\b",
        r"\bemergie\w+",
        r"\bgemeinsam\w*",
        r"\bsystemisch\w*",
    ],
    "en": [
        r"\boverall\b",
        r"\bholistic\w*",
        r"\bin\s+the\s+whole\b",
        r"\bin\s+the\s+field\b",
        r"\bbig\s+picture\b",
        r"\btaken\s+together\b",
        r"\bin\s+summary\b",
        r"\boverarching\b",
        r"\bas\s+a\s+pattern\b",
        r"\bas\s+a\s+whole\b",
        r"\bgives\s+rise\s+to\b",
        r"\bemerge\w*",
        r"\btogether\b",
        r"\bsystemic\w*",
    ],
}

WAVEFIELD_MARKERS = {
    "de": [
        r"\bwellenfeld\w*",
        r"\bresonanz\w*",
        r"\bschwingt\w*",
        r"\bspektral\w*",
        r"\bspektrum\b",
        r"\bfrequenz\w*",
        r"\bstehende\s+welle\w*",
        r"\büberlager\w+",
        r"\bphase\w*",
    ],
    "en": [
        r"\bwave[-\s]?field\w*",
        r"\bresonance\w*",
        r"\bresonat\w+",
        r"\bspectral\w*",
        r"\bspectrum\b",
        r"\bfrequenc\w+",
        r"\bstanding\s+waves?\b",
        r"\bsuperpos\w+",
        r"\bphase\b",
    ],
}


# --- Helpers ---

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def detect_lang(text: str) -> str:
    """Heuristic language detection sufficient for German vs English."""
    de_score = sum(1 for w in ("der", "die", "das", "und", "ist", "nicht", "ein") if re.search(rf"\b{w}\b", text, re.IGNORECASE))
    en_score = sum(1 for w in ("the", "and", "is", "not", "a", "of", "to") if re.search(rf"\b{w}\b", text, re.IGNORECASE))
    return "de" if de_score >= en_score else "en"


def _count_patterns(text: str, patterns: list[str]) -> int:
    total = 0
    for pat in patterns:
        total += len(re.findall(pat, text, flags=re.IGNORECASE | re.UNICODE))
    return total


# --- M1: cross-reference density ---

# A "concept" here is approximated by capitalised content tokens (works for
# German: nouns are capitalised) plus simple noun-phrase heuristics for English.
_DE_NOUN_RE = re.compile(r"\b[A-ZÄÖÜ][a-zäöüß]{3,}\b")
_EN_TOPIC_RE = re.compile(r"\b(?:[A-Z][a-z]{2,}|[a-z]{4,})\b")


def cross_reference_count(text: str, lang: str | None = None) -> int:
    if lang is None:
        lang = detect_lang(text)
    if lang == "de":
        tokens = _DE_NOUN_RE.findall(text)
    else:
        # crude: count distinct lowercase content words ≥4 chars; capped to
        # avoid trivially scoring on long answers.
        tokens = [t.lower() for t in _EN_TOPIC_RE.findall(text)]
    return len(set(tokens))


# --- Public API ---

@dataclass
class TextMetrics:
    word_count: int
    cross_ref_count: int
    cross_ref_density: float        # M1: per 100 words
    derivative_markers: int
    derivative_density: float       # M2: per 100 words
    integration_markers: int
    integration_density: float      # M3: per 100 words
    wavefield_markers: int
    wavefield_density: float        # M7: per 100 words
    detected_lang: str


def compute(text: str, lang: str | None = None) -> TextMetrics:
    detected = lang or detect_lang(text)
    wc = max(word_count(text), 1)
    cr = cross_reference_count(text, detected)
    dm = _count_patterns(text, DERIVATIVE_MARKERS[detected])
    im = _count_patterns(text, INTEGRATION_MARKERS[detected])
    wm = _count_patterns(text, WAVEFIELD_MARKERS[detected])
    return TextMetrics(
        word_count=wc,
        cross_ref_count=cr,
        cross_ref_density=100.0 * cr / wc,
        derivative_markers=dm,
        derivative_density=100.0 * dm / wc,
        integration_markers=im,
        integration_density=100.0 * im / wc,
        wavefield_markers=wm,
        wavefield_density=100.0 * wm / wc,
        detected_lang=detected,
    )

"""Doc-type classifier.

Two-stage. Filename heuristics resolve the easy cases for free; the LLM
verifies and is the source of truth for anything ambiguous (low heuristic
confidence, or the heuristic guess `unknown`).

Why not skip the heuristic? Because most filenames in this corpus are
self-describing (`Paystub-...`, `W2 ...`, `EVOE - ...`). The heuristic
saves an LLM call on each. The verify step still asks the LLM to *confirm*
the guess so we never silently misroute when a file is mislabeled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from extractor.llm.base import LLMProvider
from extractor.schema import DocumentType


@dataclass(frozen=True)
class ClassifyResult:
    doc_type: DocumentType
    confidence: float
    method: str  # "heuristic" | "llm" | "llm-verified"


_PATTERNS: tuple[tuple[re.Pattern[str], DocumentType], ...] = (
    (re.compile(r"paystub", re.I), DocumentType.PAYSTUB),
    (re.compile(r"^w[-_ ]?2\b", re.I), DocumentType.W2),
    (re.compile(r"\bevoe\b|verification.*employ", re.I), DocumentType.EVOE),
    (re.compile(r"1040.*schedule.*c", re.I), DocumentType.FORM_1040),  # combined PDF
    (re.compile(r"\b1040\b", re.I), DocumentType.FORM_1040),
    (re.compile(r"schedule.?c\b", re.I), DocumentType.SCHEDULE_C),
    (re.compile(r"checking", re.I), DocumentType.BANK_STATEMENT_CHECKING),
    (re.compile(r"savings", re.I), DocumentType.BANK_STATEMENT_SAVINGS),
    (re.compile(r"closing.?disclosure|^cd[\W_]", re.I), DocumentType.CLOSING_DISCLOSURE),
    (re.compile(r"title.?report|alta.?commitment", re.I), DocumentType.TITLE_REPORT),
    (re.compile(r"letter.?of.?explanation|^loe[\W_]", re.I), DocumentType.LETTER_OF_EXPLANATION),
)


def classify_by_filename(path: Path) -> ClassifyResult:
    """Heuristic-only classification. Returns confidence 0.0 for `unknown`
    so callers know to fall back to the LLM.
    """
    name = path.name
    for pattern, doc_type in _PATTERNS:
        if pattern.search(name):
            return ClassifyResult(doc_type=doc_type, confidence=0.85, method="heuristic")
    return ClassifyResult(doc_type=DocumentType.UNKNOWN, confidence=0.0, method="heuristic")


def classify(
    path: Path,
    provider: LLMProvider,
    *,
    verify_threshold: float = 0.95,
) -> ClassifyResult:
    """Classify a PDF. Heuristic first; LLM if heuristic is uncertain or
    the document is unknown. Even confident heuristic guesses can be
    upgraded to `llm-verified` if you raise `verify_threshold` to 1.0.
    """
    initial = classify_by_filename(path)
    if initial.confidence >= verify_threshold:
        return initial

    candidates = [t.value for t in DocumentType if t is not DocumentType.UNKNOWN]
    candidates.append("unknown")
    llm_type, llm_conf = provider.classify(
        path,
        candidates,
        instructions=(
            f"Filename heuristic suggested: {initial.doc_type.value} "
            f"(confidence {initial.confidence:.2f}). Confirm or correct."
            if initial.confidence > 0
            else ""
        ),
    )

    try:
        resolved = DocumentType(llm_type)
    except ValueError:
        resolved = DocumentType.UNKNOWN
        llm_conf = 0.0

    method = "llm-verified" if initial.confidence > 0 else "llm"
    return ClassifyResult(doc_type=resolved, confidence=llm_conf, method=method)

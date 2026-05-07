"""End-to-end pipeline.

discover PDFs → classify → extract → aggregate → write JSON

Each borrower folder under the corpus root maps to one output JSON.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from extractor import __version__, aggregator, classify as classify_mod, extractors
from extractor.llm.base import LLMProvider
from extractor.schema import (
    Borrower,
    Document,
    DocumentType,
    ExtractionMeta,
)


def discover_borrower_folders(corpus_root: Path) -> list[Path]:
    """A borrower folder is any directory directly containing PDFs."""
    out: list[Path] = []
    for child in sorted(corpus_root.rglob("*")):
        if not child.is_dir():
            continue
        if any(p.suffix.lower() == ".pdf" for p in child.iterdir() if p.is_file()):
            out.append(child)
    return out


def borrower_id_from_folder(folder: Path) -> str:
    return folder.name.lower().replace(" ", "-")


def build_document(path: Path, doc_type: DocumentType, confidence: float) -> Document:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    return Document(
        id=f"doc-{sha[:12]}",
        path=str(path),
        filename=path.name,
        page_count=_count_pdf_pages(raw),
        sha256=sha,
        doc_type=doc_type,
        classifier_confidence=confidence,
        extracted_at=datetime.utcnow(),
        bytes=len(raw),
    )


def run_borrower(
    folder: Path,
    provider: LLMProvider,
    *,
    output_dir: Path,
    with_novelty: bool = False,
) -> tuple[Borrower, Path]:
    """Run the full pipeline for a single borrower folder."""
    borrower_id = borrower_id_from_folder(folder)
    pdfs = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".pdf")
    if not pdfs:
        raise ValueError(f"No PDFs in {folder}")

    started = time.monotonic()
    extractions: list[tuple[Document, Any, list[Any]]] = []
    total = len(pdfs)

    for idx, pdf in enumerate(pdfs, start=1):
        t0 = time.monotonic()
        print(f"PROGRESS: [{idx}/{total}] classifying {pdf.name}", flush=True)
        cls = classify_mod.classify(pdf, provider)
        doc = build_document(pdf, cls.doc_type, cls.confidence)
        print(
            f"PROGRESS: [{idx}/{total}] {pdf.name} → {cls.doc_type.value} "
            f"({cls.confidence:.0%} via {cls.method})",
            flush=True,
        )

        if cls.doc_type is DocumentType.UNKNOWN or cls.doc_type not in extractors.REGISTRY:
            print(f"PROGRESS: [{idx}/{total}] {pdf.name} → skipped (no extractor)", flush=True)
            extractions.append((doc, None, []))
            continue

        try:
            response = extractors.extract(
                cls.doc_type, pdf, provider, with_novelty=with_novelty
            )
        except Exception as exc:  # noqa: BLE001 — surface but don't fail the corpus
            print(f"PROGRESS: [{idx}/{total}] ERROR {pdf.name}: {exc}", flush=True)
            extractions.append((doc, None, []))
            continue

        # When with_novelty=True the parsed value is ExtractionWithNovelty[T]
        # (response.parsed.fields + response.parsed.novel_fields). When
        # False it's the bare schema instance — simpler JSON Schema, more
        # robust against the API's "schema too complex" limit.
        if with_novelty:
            wrapped = response.parsed
            extractions.append((doc, wrapped.fields, list(wrapped.novel_fields)))
            novel_count = len(wrapped.novel_fields)
        else:
            extractions.append((doc, response.parsed, []))
            novel_count = 0
        print(
            f"PROGRESS: [{idx}/{total}] {pdf.name} ✓ extracted in "
            f"{time.monotonic() - t0:.1f}s",
            flush=True,
        )

    duration = time.monotonic() - started

    meta = ExtractionMeta(
        extracted_at=datetime.utcnow(),
        extractor_version=__version__,
        llm_provider=provider.name,
        llm_model=provider.model,
        corpus_path=str(folder),
        duration_seconds=duration,
    )

    real_extractions = [(d, f, n) for d, f, n in extractions if f is not None]
    if not real_extractions:
        raise RuntimeError(
            f"No documents in {folder} were successfully extracted — cannot aggregate."
        )

    borrower = aggregator.aggregate(
        borrower_id=borrower_id,
        extractions=real_extractions,
        meta=meta,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{borrower_id}.json"
    output_path.write_text(borrower.model_dump_json(indent=2))
    return borrower, output_path


def run_corpus(
    corpus_root: Path,
    provider: LLMProvider,
    *,
    output_dir: Path,
) -> list[tuple[Borrower, Path]]:
    folders = discover_borrower_folders(corpus_root)
    return [run_borrower(f, provider, output_dir=output_dir) for f in folders]


def _count_pdf_pages(raw: bytes) -> int:
    """Cheap PDF page count without a dependency. Counts `/Type /Page`
    objects in the PDF stream — accurate enough for metadata.
    """
    count = raw.count(b"/Type /Page\n") + raw.count(b"/Type /Page ")
    if count == 0:
        count = raw.count(b"/Type/Page")
    return max(count, 1)

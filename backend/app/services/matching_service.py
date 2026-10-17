"""
app/services/matching_service.py — Deterministic and heuristic document matching engine.

Provides:
- Counterparty normalization and string similarity (SequenceMatcher + TokenSort).
- Date proximity and Decimal amount comparison.
- Exact SHA-256 source file checksum matching.
- Candidate generation with organization isolation and soft-delete exclusions.
- Category classification ('exact_file_duplicate', 'possible_duplicate', 'possible_related').
- Explainable structured evidence formatting.
- Uncalibrated heuristic ranking score (0.0 - 1.0).
"""
from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.invoice import ImportBatch, InvoiceRecord, ReceiptRecord
from app.models.relationship import DocumentRelationship
from app.models.source_file import SourceFile
from app.schemas.relationship import (
    EntityType,
    MatchCategory,
    RelatedDocumentSummary,
    SuggestionItem,
    SuggestionListResponse,
)
from app.services.relationship_service import validate_and_resolve_entity

logger = logging.getLogger(__name__)

GENERIC_IDENTIFIERS = {"N/A", "NA", "NONE", "UNKNOWN", "NULL", "0", "1", "INV", "RCP", "REC"}
COMPANY_SUFFIX_REGEX = re.compile(
    r"\b(sdn\s*bhd|berhad|bhd|pte\s*ltd|pte|pty\s*ltd|pty|llc|inc|corp|corporation|ltd|limited|co|company|holdings|enterprises|enterprise|group|services|store|restaurant|cafe)\b",
    re.IGNORECASE,
)
PUNCTUATION_REGEX = re.compile(r"[.,;:'\"()\[\]{}!@#$%^&*_\-+=/\\|<>?~]")


def normalize_counterparty(name: str | None) -> str:
    """
    Normalizes company/merchant names for explainable fuzzy comparison.
    Strips common legal/corporate suffixes, punctuation, and extra whitespace.
    """
    if not name:
        return ""
    text = name.strip().lower()
    # Remove harmless punctuation
    text = PUNCTUATION_REGEX.sub(" ", text)
    # Remove business suffixes
    text = COMPANY_SUFFIX_REGEX.sub(" ", text)
    # Collapse whitespace
    return " ".join(text.split())


def compute_counterparty_similarity(name1: str | None, name2: str | None) -> float:
    """
    Calculates normalized character and token-sorted similarity between two entity names.
    Returns a score between 0.0 and 1.0.
    """
    n1 = normalize_counterparty(name1)
    n2 = normalize_counterparty(name2)
    if not n1 or not n2:
        return 0.0
    if n1 == n2:
        return 1.0

    # 1. Standard character SequenceMatcher
    char_sim = SequenceMatcher(None, n1, n2).ratio()

    # 2. Token-sorted SequenceMatcher (handles word order differences)
    tokens1 = " ".join(sorted(n1.split()))
    tokens2 = " ".join(sorted(n2.split()))
    token_sim = SequenceMatcher(None, tokens1, tokens2).ratio()

    return round(max(char_sim, token_sim), 3)


def is_valid_document_identifier(ident: str | None) -> bool:
    """Checks whether an identifier is specific enough for deterministic matching."""
    if not ident:
        return False
    clean = ident.strip()
    if len(clean) < 3:
        return False
    if clean.upper() in GENERIC_IDENTIFIERS:
        return False
    return True


def evaluate_candidate_match(
    focal_type: EntityType,
    focal_doc: Any,
    focal_sf: SourceFile | None,
    cand_type: EntityType,
    cand_doc: Any,
    cand_sf: SourceFile | None,
) -> tuple[MatchCategory, float, list[str]] | None:
    """
    Compares a focal document with a candidate document and returns:
    (match_category, heuristic_score, evidence_list) or None if no correlation.
    """
    evidence: list[str] = []
    score_components: list[float] = []

    # 1. Exact Source File Checksum Match
    if focal_sf and cand_sf and focal_sf.checksum and focal_sf.checksum == cand_sf.checksum:
        evidence.append(f"Identical source file checksum (SHA-256: {focal_sf.checksum[:12]}...)")
        return "exact_file_duplicate", 1.0, evidence

    # Extract focal attributes
    focal_name = getattr(focal_doc, "company_name", None) or getattr(focal_doc, "merchant_name", None) or getattr(focal_doc, "original_name", None)
    focal_ident = getattr(focal_doc, "invoice_number", None) or getattr(focal_doc, "receipt_number", None)
    focal_date = getattr(focal_doc, "invoice_date", None) or getattr(focal_doc, "transaction_date", None)
    focal_amount = getattr(focal_doc, "total_amount", None)
    focal_curr = getattr(focal_doc, "currency", None)

    # Extract candidate attributes
    cand_name = getattr(cand_doc, "company_name", None) or getattr(cand_doc, "merchant_name", None) or getattr(cand_doc, "original_name", None)
    cand_ident = getattr(cand_doc, "invoice_number", None) or getattr(cand_doc, "receipt_number", None)
    cand_date = getattr(cand_doc, "invoice_date", None) or getattr(cand_doc, "transaction_date", None)
    cand_amount = getattr(cand_doc, "total_amount", None)
    cand_curr = getattr(cand_doc, "currency", None)

    # 2. Document Identifiers Match
    ident_matched = False
    if is_valid_document_identifier(focal_ident) and is_valid_document_identifier(cand_ident):
        if focal_ident.strip().upper() == cand_ident.strip().upper():
            ident_matched = True
            evidence.append(f"Exact document identifier match: '{focal_ident.strip()}'")
            score_components.append(1.0)

    # Cross-document reference check (e.g. receipt or raw text mentions the invoice number)
    if not ident_matched and is_valid_document_identifier(focal_ident):
        cand_raw = getattr(cand_doc, "raw_data", "") or ""
        if focal_ident.strip().upper() in cand_raw.upper():
            ident_matched = True
            evidence.append(f"Candidate references focal document number: '{focal_ident.strip()}'")
            score_components.append(0.85)

    if not ident_matched and is_valid_document_identifier(cand_ident):
        focal_raw = getattr(focal_doc, "raw_data", "") or ""
        if cand_ident.strip().upper() in focal_raw.upper():
            ident_matched = True
            evidence.append(f"Focal document references candidate document number: '{cand_ident.strip()}'")
            score_components.append(0.85)

    # 3. Counterparty Similarity
    name_sim = compute_counterparty_similarity(focal_name, cand_name)
    has_strong_name = name_sim >= 0.70
    if has_strong_name:
        evidence.append(f"Counterparty names are {int(name_sim * 100)}% similar ('{focal_name}' vs '{cand_name}')")
        score_components.append(name_sim)
    elif name_sim >= 0.50 and ident_matched:
        evidence.append(f"Counterparty names partially correlate ({int(name_sim * 100)}% similarity)")
        score_components.append(name_sim * 0.7)

    # 4. Monetary Amount & Currency Compatibility
    amount_matched = False
    if focal_amount is not None and cand_amount is not None:
        curr_compatible = True
        if focal_curr and cand_curr and focal_curr.strip().upper() != cand_curr.strip().upper():
            curr_compatible = False
            evidence.append(f"Currencies differ ({focal_curr} vs {cand_curr})")

        if curr_compatible:
            f_amt = Decimal(str(focal_amount))
            c_amt = Decimal(str(cand_amount))
            curr_str = f" {focal_curr}" if focal_curr else ""
            if f_amt == c_amt:
                amount_matched = True
                evidence.append(f"Total amount matches exactly: {f_amt:,.2f}{curr_str}")
                score_components.append(1.0)
            elif f_amt > 0 and abs(f_amt - c_amt) / f_amt <= Decimal("0.02"):
                # Within 2% difference
                amount_matched = True
                evidence.append(f"Total amounts are within 2% ({f_amt:,.2f} vs {c_amt:,.2f}{curr_str})")
                score_components.append(0.80)

    # --- Strict Core Evidence Gate ---
    # Date proximity or coincidental weak similarity must NEVER surface a candidate on its own.
    # A candidate must have at least one credible primary relationship anchor:
    # 1. Exact document identifier match or text cross-reference
    # 2. Strong counterparty similarity (>= 70%)
    # 3. Compatible monetary amount with at least partial counterparty correlation (>= 40%)
    has_core_anchor = ident_matched or has_strong_name or (amount_matched and name_sim >= 0.40)
    if not has_core_anchor:
        return None

    # 5. Date Proximity (corroborates and boosts ranking only after core anchor is established)
    if focal_date and cand_date:
        delta_days = abs((focal_date - cand_date).days)
        if delta_days == 0:
            evidence.append(f"Transaction date is identical ({focal_date})")
            score_components.append(1.0)
        elif delta_days <= 3:
            evidence.append(f"Dates are {delta_days} day(s) apart ({focal_date} vs {cand_date})")
            score_components.append(0.85)
        elif delta_days <= 14:
            evidence.append(f"Dates are within 2 weeks ({delta_days} days apart: {focal_date} vs {cand_date})")
            score_components.append(0.60)
        elif delta_days > 45 and not ident_matched:
            # Substantial time gap reduces correlation unless strong identifier match
            score_components.append(0.20)

    # If no meaningful signals were found
    if not score_components or len(evidence) == 0:
        return None

    # Compute uncalibrated composite heuristic ranking score (0.0 to 1.0)
    composite_score = round(sum(score_components) / len(score_components), 3)

    # 6. Categorization
    if focal_type == cand_type:
        # Same type (invoice-invoice or receipt-receipt)
        if ident_matched:
            category: MatchCategory = "possible_duplicate"
            composite_score = max(composite_score, 0.88)
        elif name_sim >= 0.80 and amount_matched:
            # Same counterparty and same amount
            category = "possible_duplicate"
            composite_score = max(composite_score, 0.75)
        else:
            category = "possible_related"
    else:
        # Cross-type (e.g. invoice ↔ receipt, or document ↔ source_file)
        category = "possible_related"

    if composite_score < 0.45 and not ident_matched:
        return None

    return category, composite_score, evidence


def find_document_suggestions(
    db: Session,
    organization_id: int,
    entity_type: EntityType,
    entity_id: int,
    limit: int = 10,
) -> SuggestionListResponse:
    """
    Generates intelligent duplicate and related-document candidate suggestions
    for an entity within the tenant workspace.
    Bounded, tenant-isolated, and explainable.
    """
    # 1. Resolve focal entity
    focal_obj, _ = validate_and_resolve_entity(db, organization_id, entity_type, entity_id)

    # Resolve focal SourceFile for checksum matching
    focal_sf: SourceFile | None = None
    if entity_type == "source_file":
        focal_sf = focal_obj
    elif hasattr(focal_obj, "batch") and focal_obj.batch and focal_obj.batch.source_file:
        focal_sf = focal_obj.batch.source_file

    # 2. Query already linked entities to exclude them
    existing_edges = (
        db.query(DocumentRelationship)
        .filter(
            DocumentRelationship.organization_id == organization_id,
            or_(
                and_(DocumentRelationship.source_type == entity_type, DocumentRelationship.source_id == entity_id),
                and_(DocumentRelationship.target_type == entity_type, DocumentRelationship.target_id == entity_id),
            ),
        )
        .all()
    )
    already_linked_pairs: set[tuple[str, int]] = set()
    for edge in existing_edges:
        if edge.source_type == entity_type and edge.source_id == entity_id:
            already_linked_pairs.add((edge.target_type, edge.target_id))
        else:
            already_linked_pairs.add((edge.source_type, edge.source_id))

    # 3. Retrieve bounded candidates per entity type
    raw_candidates: list[tuple[EntityType, Any, SourceFile | None, RelatedDocumentSummary]] = []

    # Candidates: Invoices
    inv_query = (
        db.query(InvoiceRecord)
        .join(ImportBatch)
        .filter(
            ImportBatch.organization_id == organization_id,
            ImportBatch.is_deleted.is_(False),
        )
    )
    if entity_type == "invoice":
        inv_query = inv_query.filter(InvoiceRecord.id != entity_id)

    invoices = inv_query.order_by(InvoiceRecord.id.desc()).limit(50).all()
    for inv in invoices:
        if ("invoice", inv.id) in already_linked_pairs:
            continue
        sf = inv.batch.source_file if (inv.batch and inv.batch.source_file) else None
        summary = RelatedDocumentSummary(
            entity_type="invoice",
            entity_id=inv.id,
            document_number=inv.invoice_number,
            counterparty=inv.company_name,
            document_date=inv.invoice_date,
            total_amount=inv.total_amount,
            currency=inv.currency,
            direction=inv.direction,
            source_file_id=sf.id if sf else None,
        )
        raw_candidates.append(("invoice", inv, sf, summary))

    # Candidates: Receipts
    rec_query = (
        db.query(ReceiptRecord)
        .join(ImportBatch)
        .filter(
            ImportBatch.organization_id == organization_id,
            ImportBatch.is_deleted.is_(False),
        )
    )
    if entity_type == "receipt":
        rec_query = rec_query.filter(ReceiptRecord.id != entity_id)

    receipts = rec_query.order_by(ReceiptRecord.id.desc()).limit(50).all()
    for rec in receipts:
        if ("receipt", rec.id) in already_linked_pairs:
            continue
        sf = rec.batch.source_file if (rec.batch and rec.batch.source_file) else None
        summary = RelatedDocumentSummary(
            entity_type="receipt",
            entity_id=rec.id,
            document_number=rec.receipt_number,
            counterparty=rec.merchant_name,
            document_date=rec.transaction_date,
            total_amount=rec.total_amount,
            currency=rec.currency,
            direction=rec.direction,
            source_file_id=sf.id if sf else None,
        )
        raw_candidates.append(("receipt", rec, sf, summary))

    # Candidates: SourceFiles (supporting documents / attachments)
    sf_query = db.query(SourceFile).filter(SourceFile.organization_id == organization_id)
    if entity_type == "source_file":
        sf_query = sf_query.filter(SourceFile.id != entity_id)

    source_files = sf_query.order_by(SourceFile.id.desc()).limit(30).all()
    for sf in source_files:
        if ("source_file", sf.id) in already_linked_pairs:
            continue
        summary = RelatedDocumentSummary(
            entity_type="source_file",
            entity_id=sf.id,
            filename=sf.original_name,
            media_type=sf.media_type,
            file_size=sf.file_size,
            source_file_id=sf.id,
        )
        raw_candidates.append(("source_file", sf, sf, summary))

    # 4. Evaluate candidates
    scored_suggestions: list[SuggestionItem] = []
    for cand_type, cand_doc, cand_sf, cand_summary in raw_candidates:
        match_res = evaluate_candidate_match(
            focal_type=entity_type,
            focal_doc=focal_obj,
            focal_sf=focal_sf,
            cand_type=cand_type,
            cand_doc=cand_doc,
            cand_sf=cand_sf,
        )
        if match_res is not None:
            category, score, evidence = match_res
            scored_suggestions.append(
                SuggestionItem(
                    candidate_type=cand_type,
                    candidate_id=cand_summary.entity_id,
                    match_category=category,
                    heuristic_score=score,
                    evidence=evidence,
                    candidate_summary=cand_summary,
                    is_already_linked=False,
                )
            )

    # 5. Sort candidates:
    # Category priority: exact_file_duplicate (0) > possible_duplicate (1) > possible_related (2)
    # Secondary: score desc
    # Tertiary: candidate_id desc for deterministic ordering
    cat_order = {"exact_file_duplicate": 0, "possible_duplicate": 1, "possible_related": 2}
    scored_suggestions.sort(
        key=lambda s: (
            cat_order.get(s.match_category, 3),
            -s.heuristic_score,
            -s.candidate_id,
        )
    )

    bounded_results = scored_suggestions[:limit]
    return SuggestionListResponse(
        target_type=entity_type,
        target_id=entity_id,
        suggestions=bounded_results,
        total=len(bounded_results),
    )

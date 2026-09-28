"""Evidence-based suggestions, never an irreversible classification."""
from app.schemas.suggestion import SheetAnalysis
from app.services.mapping_suggester import detect_tables, suggest_invoice, detect_generic_dataset


def analyze_sheet(profile):
    datasets = detect_tables(profile, dataset=True)
    lines = detect_tables(profile)
    table = lines[0] if lines else None
    # Column headers must not double as document labels with the first record below.
    mappings = suggest_invoice(profile, table or (datasets[0] if datasets else None))
    anchors = {m.target_field for m in mappings}
    if datasets and not {"invoice_number", "invoice_date"}.issubset(anchors):
        table = datasets[0]
        return SheetAnalysis(worksheet=profile.metadata.name, suggested_template_type="dataset",
            confidence=table.confidence, reasons=["Canonical column headers followed by repeated records."],
            mappings=table.columns, table=table)
    if len(anchors & {"invoice_number", "invoice_date", "total_amount", "currency"}) >= 2:
        strong = sum(m.confidence == "high" for m in mappings)
        return SheetAnalysis(worksheet=profile.metadata.name, suggested_template_type="invoice",
            confidence="high" if strong >= 3 else "medium",
            reasons=["Document header values and invoice labels."] + (["Repeating line-item table detected."] if table else []),
            mappings=mappings, table=table)
    generic = detect_generic_dataset(profile)
    if generic:
        return SheetAnalysis(worksheet=profile.metadata.name, suggested_template_type="dataset",
            confidence="medium", reasons=["Text headers with at least three rows of consistent column types."],
            mappings=generic.columns, table=generic)
    return SheetAnalysis(worksheet=profile.metadata.name, suggested_template_type=None,
        confidence="low", reasons=["We could not confidently detect this workbook structure."], mappings=[], table=None)


def suggest_worksheet(profiles, analyses):
    ranks = {"high": 3, "medium": 2, "low": 0}
    return max(zip(profiles, analyses), key=lambda pair: (
        ranks[pair[1].confidence], len(pair[1].mappings), not pair[0].metadata.is_hidden,
        pair[0].metadata.name.lower() in {"invoice", "invoices", "data"}
    ))[0].metadata.name

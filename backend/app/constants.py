"""
app/constants.py — Shared application-level constants.

Keep this module import-free of ORM/Pydantic types so it can be safely
imported from any layer without introducing circular dependencies.
"""

# ── Canonical InvoiceRecord field names ──────────────────────────────────────
#
# These are the exact column names on the InvoiceRecord ORM model.
# A template field mapping whose target_field matches one of these values
# is routed directly into the corresponding database column; any other
# target_field is stored in the custom_fields JSON column.
#
# UPDATE THIS LIST when adding new canonical columns to InvoiceRecord.
CANONICAL_INVOICE_FIELDS: frozenset[str] = frozenset([
    "company_name",
    "invoice_number",
    "invoice_date",
    "total_amount",
    "currency",
])

# Ordered list for API exposure (stable, human-readable order)
CANONICAL_INVOICE_FIELDS_LIST: list[str] = [
    "company_name",
    "invoice_number",
    "invoice_date",
    "total_amount",
    "currency",
]

# ── Canonical InvoiceLineItem field names ────────────────────────────────────
#
# These are the exact column names on the InvoiceLineItem ORM model.
# A line-item template field mapping whose target_field matches one of these
# values is routed directly into the corresponding database column; any other
# target_field is stored in the line item custom_fields JSON column.
CANONICAL_LINE_ITEM_FIELDS: frozenset[str] = frozenset([
    "description",
    "quantity",
    "unit_price",
    "tax_rate",
    "tax_amount",
    "amount",
])

CANONICAL_LINE_ITEM_FIELDS_LIST: list[str] = [
    "description",
    "quantity",
    "unit_price",
    "tax_rate",
    "tax_amount",
    "amount",
]


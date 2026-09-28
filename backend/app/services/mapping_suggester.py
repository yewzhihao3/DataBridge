"""Deterministic aliases, nearby-value association and repeating table regions."""
import re
from openpyxl.utils import get_column_letter
from app.schemas.suggestion import MappingSuggestion, TableSuggestion
from app.services.workbook_profiler import normalize, CURRENCIES

HEADER_ALIASES = {
    "company_name": ("company name", "company", "supplier", "supplier name", "vendor", "bill from"),
    "invoice_number": ("invoice number", "invoice no", "inv no", "inv number", "document no", "invoice id"),
    "invoice_date": ("invoice date", "inv date", "issue date", "date"),
    "due_date": ("due date", "payment due"),
    "currency": ("currency", "currency code", "curr"),
    "total_amount": ("grand total", "invoice total", "amount due", "total amount", "total", "total due"),
    "sub_total": ("subtotal", "sub total"),
    "tax_amount": ("tax", "tax amount", "gst", "vat", "sales tax"),
}
LINE_ALIASES = {
    "description": ("description", "item", "product", "item description", "product description", "details"),
    "quantity": ("qty", "quantity", "units"),
    "unit_price": ("unit price", "price", "unit rate"),
    "tax_rate": ("tax rate", "gst rate", "vat rate", "tax percent"),
    "tax_amount": ("tax", "tax amount", "gst", "vat"),
    "amount": ("amount", "line total", "line amount", "total"),
}


def label(value):
    return normalize(re.sub(r"\s*\([^)]*\)\s*$", "", str(value)).rstrip(":"))


def target(value, aliases):
    text = label(value)
    return next((key for key, names in aliases.items() if text in names or text == key.replace("_", " ")), None)


def suggestion(field, cell, group="header", column=False, confidence="high", reason="Recognized label and adjacent value."):
    data_type = "date" if field.endswith("date") else "decimal" if field in {
        "total_amount", "sub_total", "tax_amount", "quantity", "unit_price", "tax_rate", "amount"
    } else "text"
    return MappingSuggestion(field_name=field, target_field=field, mapping_group=group,
        mapping_type="column" if column else "cell", cell_ref=None if column else cell.ref,
        column_ref=get_column_letter(cell.col) if column else None, is_required=False,
        data_type=data_type, confidence=confidence, reason=reason)


def detect_tables(profile, dataset=False):
    aliases = HEADER_ALIASES if dataset else LINE_ALIASES
    candidates = []
    for row in profile.metadata.likely_header_rows:
        columns = {}
        for cell in profile.cells.values():
            if cell.row == row:
                field = target(cell.value, aliases)
                if field and field not in columns:
                    columns[field] = cell
        if len(columns) < (3 if dataset else 2):
            continue
        if not dataset and not ("description" in columns and {"amount", "quantity", "unit_price"} & columns.keys()):
            continue
        end = row
        blank_count = 0
        for r in range(row + 1, profile.metadata.scanned_rows + 1):
            values = {field: profile.cells.get((r, c.col)) for field, c in columns.items()}
            present = [c for c in values.values() if c]
            if not present:
                blank_count += 1
                if blank_count >= 2:
                    break
                continue
            blank_count = 0
            # Exact labels plus missing numeric structure, never substring keywords.
            footer = any(target(c.value, HEADER_ALIASES) in {"sub_total", "tax_amount", "total_amount"} for c in present)
            if not dataset and footer and (not values.get("quantity") or not values.get("unit_price")):
                break
            if all(target(c.value, aliases) for c in present):
                break  # repeated header / a new region
            if len(present) < 2:
                break
            end = r
        if end == row or (dataset and end - row < 2):
            continue
        candidates.append(TableSuggestion(header_row=row, data_start_row=row + 1, data_end_row=end,
            confidence="high" if len(columns) >= 4 else "medium",
            columns=[suggestion(f, c, "header" if dataset else "line_item", True,
                        reason="Recognized column header with repeating rows below.") for f, c in columns.items()]))
    return sorted(candidates, key=lambda t: (len(t.columns), t.data_end_row - t.header_row), reverse=True)


def compatible(field, cell):
    if field.endswith("date"):
        return cell.kind == "date"
    if field in {"total_amount", "sub_total", "tax_amount"}:
        return cell.kind in {"number", "currency", "formula"}
    if field == "currency":
        return str(cell.value).strip() in CURRENCIES
    return cell.kind in {"text", "number"}


def suggest_invoice(profile, table):
    found = {}
    for cell in profile.cells.values():
        if table and table.header_row <= cell.row <= table.data_end_row:
            continue
        field = target(cell.value, HEADER_ALIASES)
        if not field:
            continue
        if field in {"total_amount", "sub_total", "tax_amount"} and table and cell.row < table.header_row:
            continue
        # Start beyond merged label boundaries, then inspect directly below.
        positions = [(cell.row, cell.end_col + d) for d in range(1, 4)] + [(cell.end_row + d, cell.col) for d in range(1, 3)]
        blocked_right = False
        for pos in positions:
            if pos[0] == cell.row and blocked_right:
                continue
            value = profile.cells.get(pos)
            if not value:
                continue
            if target(value.value, HEADER_ALIASES) or target(value.value, LINE_ALIASES):
                if pos[0] == cell.row:
                    blocked_right = True
                    continue
                break
            if compatible(field, value):
                item = suggestion(field, value, reason=f"Label at {cell.ref}; compatible value at {value.ref}.")
                # Multiple plausible totals/labels are explicitly uncertain.
                if field in found:
                    found[field].confidence = "low"
                    found[field].reason = "Multiple matching labels; review the selected location."
                else:
                    found[field] = item
                break
    if table:
        top = [c for c in profile.cells.values() if c.row < table.header_row]
        title = profile.cells.get((1, 1))
        if "company_name" not in found and title and title.kind == "text" and not target(title.value, HEADER_ALIASES) and label(title.value) not in {"invoice", "tax invoice"}:
            found["company_name"] = suggestion("company_name", title, confidence="medium",
                reason="Text at the top of the document; verify that this is the issuing company.")
        # Conservative fallback for unlabeled document headers, including old regression fixtures.
        ids = [c for c in top if c.kind == "text" and re.fullmatch(r"[A-Za-z]{2,}[-/]\d{4}[-/]\d+", str(c.value))]
        dates = sorted([c for c in top if c.kind == "date"], key=lambda c: (c.col, c.row))
        if "invoice_number" not in found and len(ids) == 1:
            found["invoice_number"] = suggestion("invoice_number", ids[0], confidence="medium", reason="Unique document identifier pattern above the table; verify its meaning.")
        if len(dates) == 2 and dates[0].col == dates[1].col and dates[1].row == dates[0].row + 1:
            for f, c in zip(("invoice_date", "due_date"), dates):
                if f not in found:
                    found[f] = suggestion(f, c, confidence="low", reason="Two adjacent dates above the table; their roles need review.")
        currencies = [c for c in top if str(c.value).strip() in CURRENCIES]
        if "currency" not in found and len(currencies) == 1:
            found["currency"] = suggestion("currency", currencies[0], confidence="medium", reason="Unique currency indicator above the table.")
    return list(found.values())


def detect_generic_dataset(profile):
    """Require at least three regular rows and a typed column for unknown headers."""
    for row in profile.metadata.likely_header_rows:
        headers = [c for c in profile.cells.values() if c.row == row]
        if len(headers) < 3 or any(target(c.value, LINE_ALIASES) for c in headers):
            continue
        if len({normalize(c.value) for c in headers}) != len(headers):
            continue
        samples = [[profile.cells.get((r, c.col)) for c in headers] for r in range(row + 1, row + 4)]
        if any(any(c is None for c in sample) for sample in samples):
            continue
        kinds = [c.kind for c in samples[0]]
        if not any(k in {"number", "date", "currency"} for k in kinds):
            continue
        if any([c.kind for c in sample] != kinds for sample in samples[1:]):
            continue
        end = row + 3
        for r in range(end + 1, profile.metadata.scanned_rows + 1):
            values = [profile.cells.get((r, c.col)) for c in headers]
            if any(c is None for c in values) or [c.kind for c in values] != kinds:
                break
            end = r
        columns = []
        for c, value_kind in zip(headers, kinds):
            field = target(c.value, HEADER_ALIASES)
            custom = not field
            field = field or ('custom_' + normalize(c.value).replace(' ', '_'))[:90]
            mapping = suggestion(field, c, column=True, confidence="medium",
                reason="Repeated rows with consistent types; review this custom column." if custom else "Recognized label in a regular table.")
            if custom:
                mapping.data_type = "date" if value_kind == "date" else "decimal" if value_kind == "number" else "text"
            columns.append(mapping)
        return TableSuggestion(header_row=row, data_start_row=row + 1, data_end_row=end,
            confidence="medium", columns=columns)
    return None

"""Match mapping anchors, never variable cell contents or business values.

Legacy templates have no stored label fingerprint. Require multiple independently
detected canonical anchors at the saved positions, compatible type and table rows.
"""
from app.schemas.suggestion import TemplateMatch


def match_templates(analysis, templates):
    if analysis.confidence == "low":
        return []
    mappings = analysis.mappings + (analysis.table.columns if analysis.table and analysis.suggested_template_type == "invoice" else [])
    anchors = {(m.mapping_group, m.target_field): (m.mapping_type, m.cell_ref, m.column_ref)
               for m in mappings if m.confidence != "low"}
    matches = []
    for template in templates:
        if template.template_type != analysis.suggested_template_type:
            continue
        if template.worksheet and template.worksheet != analysis.worksheet:
            continue
        saved = {(m.mapping_group, m.target_field or m.field_name): (m.mapping_type, m.cell_ref, m.column_ref)
                 for m in template.field_mappings}
        shared = anchors.keys() & saved.keys()
        exact = [k for k in shared if anchors[k] == saved[k]]
        if len(exact) < 4 or len(exact) < len(shared) or len(exact) / max(len(saved), 1) < .6:
            continue
        if analysis.table and (template.header_row != analysis.table.header_row or template.data_start_row != analysis.table.data_start_row):
            continue
        if analysis.suggested_template_type == "invoice" and sum(k[0] == "header" for k in exact) < 2:
            continue
        matches.append(TemplateMatch(template_id=template.id, name=template.name,
            confidence="high" if len(exact) >= 6 and len(exact) == len(saved) else "medium",
            reasons=[f"{len(exact)} independently detected mapping anchors agree with the saved layout.", "Compatible worksheet, structure and table positions; review before use."]))
    return sorted(matches, key=lambda m: (m.confidence != "high", m.template_id))[:5]

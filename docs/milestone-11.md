# Milestone 11 — Smart Extraction & Theme System

## Smart extraction

M11 adds a read-only, deterministic suggestion layer before the existing template-driven extraction pipeline. It never changes an uploaded workbook, creates a template, runs an import, or bypasses preview and validation.

`POST /api/v1/suggestions/analyze` accepts an existing uploaded `file_id` and optional worksheet name. It returns bounded workbook profile metadata, a suggested worksheet and structure, proposed field mappings, a possible table region, ranked saved-template matches, and confidence labels (`high`, `medium`, or `low`). Every result is explicitly review-required.

The analysis path is:

```text
Workbook profiler → structure detector → mapping suggester → template matcher
                                                  ↓
                                  user reviews a normal template draft
                                                  ↓
                          existing extractor → validator → import workflow
```

The profiler scans at most the first 2,000 rows and 100 columns of the first 30 worksheets. It records structural metadata only: used ranges, non-empty counts, likely header rows, blank boundaries, numeric columns, date/currency/formula cells, and merge ranges. It does not return workbook dumps or calculate formulas.

Invoice mapping uses normalized exact alias dictionaries and compatible nearby values. It supports a value to the right of a label, below a label, and after a merged label. It recognizes common variants for company, invoice number, dates, currency, subtotal, tax, and total. A top document title, unique document-like identifier, or unique currency can provide a lower-confidence fallback when labels are missing.

Tables require recognized headers plus repeating rows. Invoice line-item detection recognizes description, quantity, unit price, tax rate, tax amount, and amount. Footer detection requires an exact footer label combined with missing quantity or unit-price structure; product descriptions such as `Total Care Cleaning Kit`, `Tax Preparation Service`, and `GST Compliance Software` therefore remain valid line items. Dataset detection supports canonical invoice columns and consistent custom columns with at least three typed rows.

Template matching compares the worksheet, structure, table positions, and independently detected mapping anchors. It deliberately excludes variable business values such as company names, invoice numbers, dates, and amounts. A match requires at least four exact anchors, compatible template type and worksheet, and sufficiently complete agreement, which avoids matching unrelated invoices that merely contain `Invoice`.

Low confidence is a neutral outcome: “We could not confidently detect this workbook structure.” The user can choose any visible worksheet, ignore suggestions, manually select an existing template, or create and edit a template as before.

### Known scope limits

M11 does not provide OCR for PDFs or images, AI/LLM extraction, perfect mapping of arbitrary documents, CSV/email/background ingestion, accounting or ERP integrations, user accounts, subscriptions, or tenancy.

## Theme system

The frontend uses semantic CSS tokens in `src/assets/themes.css`, applied through `data-theme`, `data-mode`, and `data-appearance` attributes on the document root. The token layer supplies app and surface backgrounds, borders, text, accent, state colors, focus ring, and shadows, while compatibility aliases allow existing components to use the tokens without a broad page rewrite.

The available theme families are Orange, Blue, and Emerald. Each works in Light, Dark, and System appearance. System follows `prefers-color-scheme` and listens for operating-system changes. The default is Orange Dark. A small `useTheme()` composable persists `{ theme, mode }` under `databridge.appearance` in local storage; `theme-init.js` applies it before the app mounts to avoid an obvious flash.

The compact header now has clear active-route treatment, an accessible keyboard-operable Appearance disclosure, focus rings, and horizontally resilient navigation at smaller widths. The dashboard SVG chart consumes the same tokens for grid, labels, baseline, and bars.

## Verification

Backend tests cover invoice and dataset structure detection, ambiguous sheets, multiple worksheets, aliases, adjacent and merged labels, formula and bounded profile metadata, footer false positives, Northstar suggestions, template matching and false-positive prevention, and a reviewed suggestion passed into the existing preview endpoint.

Manual browser checks covered Orange Dark and Light across the ingestion, templates, history/detail modal, explorer/detail modal, export center, and dashboard/chart; Blue and Emerald in Light and Dark on the dashboard; and System preference persistence after reload. The light template form’s placeholders and the dark import-detail modal were specifically checked for contrast.

# Milestone 10 — Dashboard & Analytics

Implemented: descriptive analytics over persisted standardized records. No original
workbooks are read by analytics. M11 has not started.

## Architecture and endpoints

- `GET /api/v1/analytics/filter-options` returns active currencies, companies,
  unspecified-currency presence, and invoice-date bounds.
- `GET /api/v1/analytics/dashboard` returns filters, summary, monthly values,
  company rankings, and line-item rankings in one request.
- `services/business_query.py` centralizes the SQL active-record predicate and
  compatible company/currency/date filters used by Explorer and exports. Analytics
  reuses that boundary and company/date filters, with stricter currency isolation.
- `services/analytics_service.py` owns aggregation; Pydantic response contracts
  live in `schemas/analytics.py`. The router handles filter validation.
- `/dashboard` is a lazy-loaded Vue destination. Ingestion Studio remains `/`.

## Currency and missing-value policies

The frontend defaults to the alphabetically first available currency. Selection,
inclusive invoice-date boundaries, and optional company substring are persisted in
URL query parameters. Reset clears dates/company and selects the default currency.

Analytics normalizes currency case and outer whitespace for grouping/filtering
without rewriting records. Unlike the older Explorer/export exact stored-currency
comparison, `myr`, `MYR`, and ` MYR ` are the same analytics currency. This deliberate
difference keeps the selector consistent with legacy persisted values. Dashboard
export shortcuts are omitted to avoid transferring incompatible currency semantics.

An omitted/blank API currency selects ONLY unspecified-currency records. It never
means all currencies. Their counts/completeness are visible, but all monetary
values are null and rankings empty, because unspecified currencies cannot safely
be combined. Known currencies are never combined and there is no FX conversion.

SQL aggregates exclude null amounts, while record counts include matching records
with null totals. No known amounts yields null, not zero. Genuine zero and negative
amounts remain valid known amounts. Missing line-item amounts are not calculated
from quantity and price. Missing invoice dates are not replaced with import dates.

## KPI and chart definitions

| Output | Definition |
| --- | --- |
| Invoices | Matching active InvoiceRecord rows |
| Invoice Value | Sum of known canonical total_amount values for one currency |
| Average Invoice Value | Known-total sum divided by invoices_with_total, rounded half up to two decimals |
| Line Items | Child row count for matching active invoices |
| Completeness | Counts with/without invoice totals, without dates, and line items with amounts |
| Invoice Value Over Time | Calendar-month groups by invoice_date; null dates excluded; count includes dated invoices with unknown totals |
| Invoice Value by Company | Top 10 groups by stored company name, known totals summed; count includes unknown totals within qualifying groups |
| Top Line Items by Amount | Top 10 description groups by known persisted amount; parent currency/date/company filters apply |

Rankings sort by descending value, with name/description tie-breaking. Groups with
no known amounts are excluded. Missing descriptions remain null in the API and get
a neutral display label in the UI. Description normalization trims outer whitespace
only; it does not infer product identity. Literal `Unknown Company` values are
preserved. No quantities or tax values are aggregated.

The monthly response contains observed months only; missing months are not filled
with financial zeroes. A month containing only unknown totals has a null value and
still carries its invoice count. The chart explicitly explains these semantics.

## Financial correctness and performance

Invoice queries never join the child table, preventing invoice-total fan-out.
Line-item queries join only their parent invoice and batch. Summary, monthly and
ranking calculations use SQL COUNT/SUM/GROUP BY; raw business rows are not loaded
to aggregate in Python. The dashboard uses five aggregate queries for a known
currency. Filter options use distinct values and SQL date bounds.

Canonical monetary columns have scale two. To avoid SQLite floating SUM/AVG
artifacts, SQL rounds each amount to canonical cents, casts it to BIGINT, and sums
the integers. Python Decimal converts the aggregate and computes the average.
This also aligns legacy SQLite values with the ORM's two-decimal representation.
Pydantic serializes monetary results as decimal strings. JavaScript converts only
for display/chart geometry, never authoritative financial aggregation.

No schema or index changes were made. Existing indexes cover company_name,
batch_id, and invoice_id; invoice_date, currency, and is_deleted lack dedicated
indexes. Without query-plan evidence and versioned migrations, adding indexes was
deferred. PostgreSQL expression compilation is tested, but a live PostgreSQL run
has not been performed. No cache, worker, Redis, or materialized view was added.

## Frontend and UX

The dashboard follows the existing dark Zen Data tokens, with four restrained KPI
cards, compact filters, one monthly chart, and two ordinary Vue/CSS ranking lists.
An SVG bar chart avoids a new chart dependency for this single simple series. It
supports positive/negative/zero values, focus/hover details, and an expandable exact
monthly table. ResizeObserver keeps labels readable at small widths. KPI cards wrap;
rankings stack and long descriptions wrap; navigation remains horizontally reachable.

Initial loading uses placeholders; refresh retains dimmed prior results with a
loading caption. Request sequencing prevents an older response replacing newer
filter results. Errors expose a calm Retry state, not stack traces. Invalid ranges
produce a friendly frontend error and HTTP 422. Empty databases, no matches, no
totals, no dates, and no line-item amounts have explicit empty states.

## Verification

- Full backend suite: **222 passed, 2 warnings** (195 existing plus 27 new cases).
- Warnings are the pre-existing Starlette HTTP 422 constant deprecations.
- `npm run build`: TypeScript and Vite production build pass.
- Tests cover empty/no-match/all-null/zero/negative values, Decimal sums and average
  rounding, mixed and unspecified currencies, inclusive/one-sided/invalid dates,
  null dates, monthly grouping across years, company substring matching, top-10
  order/ties, description normalization, parent filters, soft-delete exclusion from
  all aggregates/options/date bounds, and fresh Northstar persistence-to-analytics.
- Mandatory fan-out regression: invoices 100 and 200 with four and three child
  rows yield invoice value 300, average 150, and seven line items.
- Fresh Northstar workbook uploaded, previewed, and confirmed through the real API
  in an isolated QA database. Browser inspection confirmed one invoice, total and
  average MYR 7,211.59, four line items, company value MYR 7,211.59, and amounts
  4,134.00 / 1,494.00 / 779.40 / 270.00. Existing development data was not changed.
- Browser checks included invalid-range feedback, filter URL state after reload,
  Reset Filters, no-match states, and a 390px viewport with no page-width overflow.

## Files

Added:

- `backend/app/services/business_query.py`
- `backend/app/services/analytics_service.py`
- `backend/app/schemas/analytics.py`
- `backend/app/routers/analytics.py`
- `backend/tests/integration/test_api_analytics.py`
- `frontend/src/views/DashboardView.vue`
- `frontend/src/components/dashboard/InvoiceTrend.vue`
- `docs/milestone-10.md`

Modified:

- `backend/app/main.py`
- `backend/app/routers/data_explorer.py`
- `backend/app/services/export_builder.py`
- `frontend/src/router/index.ts`
- `frontend/src/components/common/AppHeader.vue`
- `frontend/src/services/api.ts`
- `frontend/src/types/api.ts`
- `README.md` (small milestone status/link only)

## Limitations and deferred work

Monthly grouping only; top 10 only; no FX, forecasting, AI insights, tax or generic
custom-field analytics, quantity aggregation, chart export, scheduling, or tenancy.
Dataset imports also become InvoiceRecord rows, so invoice counts/value reflect
canonical persisted records, not a guarantee of original document type. Duplicate
active imports contribute independently. Company labels do not imply buyer/seller,
supplier/customer, revenue, spend, or profit.

M12 debt intentionally deferred: identifier fallbacks, export formula safety,
200-record export-summary sampling, XLSX autofilter bounds, existing API type drift,
manual migrations, repeated existing formatting helpers, page-local Import History
metrics, and duplicate checks against deleted batches. Historical records were not
repaired or migrated. No M11 extraction work or M1–M9 screen redesign was included.

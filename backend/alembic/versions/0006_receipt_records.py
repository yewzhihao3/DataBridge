"""First-class receipt persistence, separate from invoice analytics."""
from alembic import op
import sqlalchemy as sa
revision = "0006_receipt_records"
down_revision = "0005_ocr_failure_status"

def upgrade():
    op.create_table("receipt_records",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_id", sa.Integer(), sa.ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_name", sa.String(255), nullable=False), sa.Column("receipt_number", sa.String(100), nullable=False), sa.Column("transaction_date", sa.Date()), sa.Column("transaction_time", sa.String(20)),
        sa.Column("currency", sa.String(10)), sa.Column("subtotal", sa.Numeric(12,2)), sa.Column("tax_amount", sa.Numeric(12,2)), sa.Column("total_amount", sa.Numeric(12,2)),
        sa.Column("payment_method", sa.String(50)), sa.Column("store_address", sa.String(500)), sa.Column("cashier", sa.String(100)), sa.Column("branch", sa.String(100)), sa.Column("cash_paid", sa.Numeric(12,2)), sa.Column("change_amount", sa.Numeric(12,2)),
        sa.Column("raw_data", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_receipt_records_batch_id", "receipt_records", ["batch_id"])
    op.create_index("ix_receipt_records_merchant_name", "receipt_records", ["merchant_name"])
    op.create_index("ix_receipt_records_receipt_number", "receipt_records", ["receipt_number"])
    op.create_table("receipt_line_items", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("receipt_records.id", ondelete="CASCADE"), nullable=False), sa.Column("source_row_number", sa.Integer(), nullable=False), sa.Column("description", sa.String(500)), sa.Column("quantity", sa.Numeric(12,4)), sa.Column("unit_price", sa.Numeric(12,2)), sa.Column("tax_rate", sa.Numeric(8,4)), sa.Column("tax_amount", sa.Numeric(12,2)), sa.Column("amount", sa.Numeric(12,2)), sa.Column("raw_data", sa.Text()), sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_receipt_line_items_receipt_id", "receipt_line_items", ["receipt_id"])

def downgrade(): raise RuntimeError("Receipt downgrade risks losing imported receipt data")

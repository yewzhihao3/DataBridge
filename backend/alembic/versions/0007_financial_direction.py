"""Financial direction classification on invoice and receipt records."""
from alembic import op
import sqlalchemy as sa

revision = "0007_financial_direction"
down_revision = "0006_receipt_records"


def upgrade():
    with op.batch_alter_table("invoice_records") as batch_op:
        batch_op.add_column(
            sa.Column(
                "direction",
                sa.String(20),
                nullable=False,
                server_default="unclassified",
            )
        )
        batch_op.create_index("ix_invoice_records_direction", ["direction"])
        batch_op.create_check_constraint(
            "ck_invoice_records_direction",
            "direction IN ('sales', 'purchase', 'unclassified')",
        )

    with op.batch_alter_table("receipt_records") as batch_op:
        batch_op.add_column(
            sa.Column(
                "direction",
                sa.String(20),
                nullable=False,
                server_default="unclassified",
            )
        )
        batch_op.create_index("ix_receipt_records_direction", ["direction"])
        batch_op.create_check_constraint(
            "ck_receipt_records_direction",
            "direction IN ('expense', 'income', 'unclassified')",
        )


def downgrade():
    with op.batch_alter_table("receipt_records") as batch_op:
        batch_op.drop_constraint("ck_receipt_records_direction", type_="check")
        batch_op.drop_index("ix_receipt_records_direction")
        batch_op.drop_column("direction")

    with op.batch_alter_table("invoice_records") as batch_op:
        batch_op.drop_constraint("ck_invoice_records_direction", type_="check")
        batch_op.drop_index("ix_invoice_records_direction")
        batch_op.drop_column("direction")

"""Identity, tenant ownership and workspace-local template names."""
from alembic import op
import sqlalchemy as sa
from m12_schema import Base

revision = "0002_saas"
down_revision = "0001_m11"


def upgrade():
    connection = op.get_bind()
    identity = {"users", "organizations", "organization_memberships", "auth_sessions", "organization_invitations", "audit_events"}
    inspector = sa.inspect(connection)
    existing = set(inspector.get_table_names())
    # An M11 auto-reloading server can create newly imported identity tables
    # before create_all is removed. Adopt only exact, empty tables; never overwrite.
    for name in identity & existing:
        table = Base.metadata.tables[name]
        actual = {column["name"]: column for column in inspector.get_columns(name)}
        if set(actual) != set(table.columns.keys()) or connection.execute(sa.select(sa.func.count()).select_from(table)).scalar():
            raise RuntimeError(f"Existing identity table {name} is incompatible or populated; review before migrating")
        for column in table.columns:
            if actual[column.name]["nullable"] != column.nullable or str(actual[column.name]["type"]) != str(column.type):
                raise RuntimeError(f"Existing identity column {name}.{column.name} differs from M12")
        expected_unique = {tuple(c.name for c in constraint.columns) for constraint in table.constraints if isinstance(constraint, sa.UniqueConstraint)}
        actual_unique = {tuple(c["column_names"]) for c in inspector.get_unique_constraints(name)}
        expected_fk = {(tuple(f.parent.name for f in constraint.elements), constraint.referred_table.name, tuple(f.column.name for f in constraint.elements), constraint.ondelete) for constraint in table.foreign_key_constraints}
        actual_fk = {(tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]), f["options"].get("ondelete")) for f in inspector.get_foreign_keys(name)}
        expected_checks = {str(c.sqltext) for c in table.constraints if isinstance(c, sa.CheckConstraint)}
        actual_checks = {c["sqltext"] for c in inspector.get_check_constraints(name)}
        expected_pk = tuple(c.name for c in table.primary_key.columns)
        if (expected_unique != actual_unique or expected_fk != actual_fk or expected_checks != actual_checks or expected_pk != tuple(inspector.get_pk_constraint(name)["constrained_columns"])):
            raise RuntimeError(f"Existing identity constraints differ for {name}")
    for table in Base.metadata.sorted_tables:
        if table.name in identity and table.name not in existing:
            table.create(connection)
    organizations = Base.metadata.tables["organizations"]
    org_id = connection.execute(organizations.insert().values(name="Default Workspace", slug="default-workspace").returning(organizations.c.id)).scalar_one()
    for name in ("templates", "source_files", "import_batches"):
        op.add_column(name, sa.Column("organization_id", sa.Integer(), nullable=True))
        table = sa.table(name, sa.column("organization_id"))
        connection.execute(table.update().values(organization_id=org_id))
        with op.batch_alter_table(name) as batch:
            batch.alter_column("organization_id", existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(f"fk_{name}_organization", "organizations", ["organization_id"], ["id"], ondelete="RESTRICT")
            batch.create_index(f"ix_{name}_organization_id", ["organization_id"])
    # M11 uses a unique name index, not a named unique table constraint.
    op.drop_index("ix_templates_name", table_name="templates")
    op.create_index("ix_templates_name", "templates", ["name"], unique=False)
    with op.batch_alter_table("templates") as batch:
        batch.create_unique_constraint("uq_workspace_template_name", ["organization_id", "name"])


def downgrade():
    raise RuntimeError("Tenant downgrade risks data loss; restore a verified backup")

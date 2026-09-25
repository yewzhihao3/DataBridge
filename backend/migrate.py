import sqlite3
import sys

def run_migrations(db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. Check current columns in import_batches
        cursor.execute("PRAGMA table_info(import_batches)")
        import_batch_cols = [col[1] for col in cursor.fetchall()]
        if 'is_deleted' not in import_batch_cols:
            print("Adding is_deleted to import_batches...")
            cursor.execute("ALTER TABLE import_batches ADD COLUMN is_deleted BOOLEAN DEFAULT 0 NOT NULL")
        else:
            print("is_deleted already exists in import_batches.")
            
        # 2. Check current columns in invoice_records
        cursor.execute("PRAGMA table_info(invoice_records)")
        invoice_records_cols = [col[1] for col in cursor.fetchall()]
        if 'custom_fields' not in invoice_records_cols:
            print("Adding custom_fields to invoice_records...")
            cursor.execute("ALTER TABLE invoice_records ADD COLUMN custom_fields JSON")
        else:
            print("custom_fields already exists in invoice_records.")

        if 'source_row_number' not in invoice_records_cols:
            print("Adding source_row_number to invoice_records...")
            cursor.execute("ALTER TABLE invoice_records ADD COLUMN source_row_number INTEGER")
        else:
            print("source_row_number already exists in invoice_records.")

        # 3. Check current columns in templates
        cursor.execute("PRAGMA table_info(templates)")
        template_cols = [col[1] for col in cursor.fetchall()]
        if 'template_type' not in template_cols:
            print("Adding template_type to templates...")
            cursor.execute("ALTER TABLE templates ADD COLUMN template_type VARCHAR(20) DEFAULT 'invoice' NOT NULL")
            
            # Backfill existing dataset templates (where all mappings are 'column')
            cursor.execute("""
                UPDATE templates 
                SET template_type = 'dataset'
                WHERE id IN (
                    SELECT t.id FROM templates t
                    JOIN template_field_mappings m ON m.template_id = t.id
                    GROUP BY t.id
                    HAVING COUNT(CASE WHEN m.mapping_type != 'column' THEN 1 END) = 0
                )
            """)
            print("Backfilled existing template_type values.")
        else:
            print("template_type already exists in templates.")
            
        # 4. Check & reconstruct template_field_mappings for mapping_group and composite uniqueness
        cursor.execute("PRAGMA table_info(template_field_mappings)")
        mappings_cols = [col[1] for col in cursor.fetchall()]
        
        # Check if table needs reconstruction for mapping_group / new unique constraint
        needs_mapping_reconstruct = 'mapping_group' not in mappings_cols
        if needs_mapping_reconstruct:
            print("Reconstructing template_field_mappings for mapping_group and updated unique constraint...")
            cursor.execute("PRAGMA foreign_keys = OFF")
            
            cursor.execute("""
                CREATE TABLE template_field_mappings_new (
                    id INTEGER PRIMARY KEY,
                    template_id INTEGER NOT NULL REFERENCES templates(id) ON DELETE CASCADE,
                    mapping_group VARCHAR(20) DEFAULT 'header' NOT NULL,
                    field_name VARCHAR(100) NOT NULL,
                    target_field VARCHAR(100),
                    mapping_type VARCHAR(20) DEFAULT 'cell' NOT NULL,
                    cell_ref VARCHAR(20),
                    column_ref VARCHAR(20),
                    is_required BOOLEAN DEFAULT 0 NOT NULL,
                    data_type VARCHAR(20) DEFAULT 'text' NOT NULL,
                    CONSTRAINT uq_template_group_field_name UNIQUE (template_id, mapping_group, field_name)
                )
            """)
            
            target_field_col = "target_field" if "target_field" in mappings_cols else "NULL"
            
            cursor.execute(f"""
                INSERT INTO template_field_mappings_new (
                    id, template_id, mapping_group, field_name, target_field, mapping_type, cell_ref, column_ref, is_required, data_type
                )
                SELECT 
                    id, template_id, 'header', field_name, {target_field_col}, mapping_type, cell_ref, column_ref, is_required, data_type
                FROM template_field_mappings
            """)
            
            cursor.execute("DROP TABLE template_field_mappings")
            cursor.execute("ALTER TABLE template_field_mappings_new RENAME TO template_field_mappings")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_template_field_mappings_template_id ON template_field_mappings (template_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_template_field_mappings_id ON template_field_mappings (id)")
            
            cursor.execute("PRAGMA foreign_keys = ON")
            print("template_field_mappings reconstruction successful.")
        else:
            print("template_field_mappings already has mapping_group.")

        # 5. Check & create invoice_line_items table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='invoice_line_items'")
        if not cursor.fetchone():
            print("Creating invoice_line_items table...")
            cursor.execute("""
                CREATE TABLE invoice_line_items (
                    id INTEGER PRIMARY KEY,
                    invoice_id INTEGER NOT NULL REFERENCES invoice_records(id) ON DELETE CASCADE,
                    source_row_number INTEGER NOT NULL,
                    description VARCHAR(500),
                    quantity NUMERIC(12, 4),
                    unit_price NUMERIC(12, 2),
                    tax_rate NUMERIC(8, 4),
                    tax_amount NUMERIC(12, 2),
                    amount NUMERIC(12, 2),
                    custom_fields JSON,
                    raw_data TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_invoice_line_items_invoice_id ON invoice_line_items (invoice_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_invoice_line_items_id ON invoice_line_items (id)")
            print("invoice_line_items table created.")
        else:
            print("invoice_line_items table already exists.")

        conn.commit()
        print("All migrations completed successfully.")
        
    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    run_migrations("databridge.db")


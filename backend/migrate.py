import sqlite3
import sys

def run_migrations(db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check current columns in import_batches
        cursor.execute("PRAGMA table_info(import_batches)")
        import_batch_cols = [col[1] for col in cursor.fetchall()]
        if 'is_deleted' not in import_batch_cols:
            print("Adding is_deleted to import_batches...")
            cursor.execute("ALTER TABLE import_batches ADD COLUMN is_deleted BOOLEAN DEFAULT 0 NOT NULL")
        else:
            print("is_deleted already exists in import_batches.")
            
        # Check current columns in invoice_records
        cursor.execute("PRAGMA table_info(invoice_records)")
        invoice_records_cols = [col[1] for col in cursor.fetchall()]
        if 'custom_fields' not in invoice_records_cols:
            print("Adding custom_fields to invoice_records...")
            cursor.execute("ALTER TABLE invoice_records ADD COLUMN custom_fields JSON")
        else:
            print("custom_fields already exists in invoice_records.")
            
        # Check current columns in template_field_mappings
        cursor.execute("PRAGMA table_info(template_field_mappings)")
        mappings_cols = [col[1] for col in cursor.fetchall()]
        if 'target_field' not in mappings_cols:
            print("Adding target_field to template_field_mappings...")
            cursor.execute("ALTER TABLE template_field_mappings ADD COLUMN target_field VARCHAR(100)")
        else:
            print("target_field already exists in template_field_mappings.")

        conn.commit()
        print("Migration successful.")
        
        # Verification
        cursor.execute("SELECT id, is_deleted FROM import_batches LIMIT 1")
        row = cursor.fetchone()
        print(f"Sample ImportBatch row: {row}")
        
    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    run_migrations("databridge.db")

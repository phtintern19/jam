"""
Script to add parent-child relationship columns to users table
"""
from database import engine
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_user_parent_columns():
    """Add parent_user_id, is_invited, and invitation_status columns to users table"""
    print("=== Adding Parent-Child Relationship Columns to Users Table ===\n")
    
    try:
        with engine.connect() as conn:
            # Check if columns already exist
            if engine.dialect.name == 'sqlite':
                result = conn.execute(text("PRAGMA table_info(users)"))
                existing_columns = [row[1] for row in result]
            else:
                result = conn.execute(text("SHOW COLUMNS FROM users"))
                existing_columns = [row[0] for row in result]
            print(f"Existing columns: {existing_columns}")
            
            # List of columns to add
            columns_to_add = [
                ("parent_user_id", "INT"),
                ("is_invited", "BOOLEAN DEFAULT FALSE"),
                ("invitation_status", "VARCHAR(20) DEFAULT 'pending'")
            ]
            
            for column_name, column_def in columns_to_add:
                if column_name not in existing_columns:
                    alter_sql = f"ALTER TABLE users ADD COLUMN {column_name} {column_def}"
                    print(f"Adding column: {column_name}")
                    conn.execute(text(alter_sql))
                    conn.commit()
                    print(f"✓ Added column: {column_name}")
                else:
                    print(f"⊘ Column already exists: {column_name}")
            
            # Add foreign key constraint for parent_user_id if not exists (MySQL only)
            if engine.dialect.name != 'sqlite':
                if 'parent_user_id' in existing_columns or any(col[0] == 'parent_user_id' for col in columns_to_add):
                    try:
                        print("Adding foreign key constraint for parent_user_id...")
                        conn.execute(text("""
                            ALTER TABLE users 
                            ADD CONSTRAINT fk_user_parent 
                            FOREIGN KEY (parent_user_id) REFERENCES users(user_id) 
                            ON DELETE CASCADE
                        """))
                        conn.commit()
                        print("✓ Foreign key constraint added")
                    except Exception as e:
                        if "Duplicate foreign key constraint" in str(e) or "already exists" in str(e):
                            print("⊘ Foreign key constraint already exists")
                        else:
                            print(f"⚠ Warning adding foreign key: {e}")
            
            # Add index for parent_user_id if not exists
            try:
                print("Adding index for parent_user_id...")
                conn.execute(text("CREATE INDEX idx_user_parent_user_id ON users(parent_user_id)"))
                conn.commit()
                print("✓ Index added for parent_user_id")
            except Exception as e:
                if "Duplicate key name" in str(e) or "already exists" in str(e):
                    print("⊘ Index for parent_user_id already exists")
                else:
                    print(f"⚠ Warning adding index: {e}")
            
            print("\n✓ All columns added successfully!")
            return True
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        logger.error(f"Error adding columns: {e}")
        return False

if __name__ == "__main__":
    if add_user_parent_columns():
        print("\nYou can now run the application with: python app.py")
    else:
        print("\nFailed to add columns.")

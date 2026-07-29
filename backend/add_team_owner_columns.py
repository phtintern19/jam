"""
Script to add new columns to the team_owners table without dropping data
"""
from database import engine, SessionLocal
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_team_owner_columns():
    """Add new contact_number and email columns to team_owners table"""
    print("=== Adding New Columns to Team Owners Table ===\n")
    
    try:
        with engine.connect() as conn:
            # Check if columns already exist
            result = conn.execute(text("SHOW COLUMNS FROM team_owners"))
            existing_columns = [row[0] for row in result]
            print(f"Existing columns: {existing_columns}")
            
            # List of columns to add
            columns_to_add = [
                ("contact_number", "VARCHAR(20)"),
                ("email", "VARCHAR(100)")
            ]
            
            for column_name, column_def in columns_to_add:
                if column_name not in existing_columns:
                    alter_sql = f"ALTER TABLE team_owners ADD COLUMN {column_name} {column_def}"
                    print(f"Adding column: {column_name}")
                    conn.execute(text(alter_sql))
                    conn.commit()
                    print(f"✓ Added column: {column_name}")
                else:
                    print(f"⊘ Column already exists: {column_name}")
            
            print("\n✓ All columns added successfully!")
            return True
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        logger.error(f"Error adding columns: {e}")
        return False

if __name__ == "__main__":
    if add_team_owner_columns():
        print("\nYou can now run the application with: python app.py")
    else:
        print("\nFailed to add columns.")

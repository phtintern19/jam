"""
Script to recreate database tables with correct schema
"""
from database import engine, Base, init_db, drop_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def recreate_database():
    """Drop all tables and recreate them with current schema"""
    print("=== Recreating Database Tables ===\n")
    
    try:
        # Drop existing tables
        print("Dropping existing tables...")
        if drop_db():
            print("✓ Tables dropped successfully")
        else:
            print("✗ Failed to drop tables")
            return False
        
        # Create new tables with current schema
        print("\nCreating tables with current schema...")
        if init_db():
            print("✓ Tables created successfully")
        else:
            print("✗ Failed to create tables")
            return False
        
        print("\n✓ Database recreation completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False

if __name__ == "__main__":
    if recreate_database():
        print("\nYou can now run the application with: python app.py")
    else:
        print("\nDatabase recreation failed.")

"""
Script to update the check_team_status constraint to include 'pending' status
"""
from database import engine
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_team_status_constraint():
    """Update the check_team_status constraint to include 'pending' status"""
    print("=== Updating Team Status Check Constraint ===\n")
    
    try:
        with engine.connect() as conn:
            # Drop the old constraint
            print("Dropping old check_team_status constraint...")
            conn.execute(text("ALTER TABLE teams DROP CONSTRAINT check_team_status"))
            conn.commit()
            print("✓ Old constraint dropped")
            
            # Add the new constraint with 'pending' included
            print("Adding new check_team_status constraint with 'pending' status...")
            conn.execute(text("ALTER TABLE teams ADD CONSTRAINT check_team_status CHECK (status IN ('active', 'inactive', 'suspended', 'banned', 'pending'))"))
            conn.commit()
            print("✓ New constraint added")
            
            print("\n✓ Team status constraint updated successfully!")
            return True
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        logger.error(f"Error updating constraint: {e}")
        return False

if __name__ == "__main__":
    if update_team_status_constraint():
        print("\nYou can now run the application with: python app.py")
    else:
        print("\nFailed to update constraint.")

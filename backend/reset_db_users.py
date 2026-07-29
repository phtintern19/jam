import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the backend directory to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import engine, SessionLocal
import models

def reset_db_users():
    print("Connecting to database...")
    db = SessionLocal()
    
    try:
        print("Finding all non-admin users...")
        # Get all users except admin
        users_to_delete = db.query(models.User).filter(
            models.User.user_type != models.UserType.admin
        ).all()
        
        count = len(users_to_delete)
        if count == 0:
            print("No users to delete. Database is already clean.")
            return

        print(f"Found {count} non-admin users (Players, Team Owners, Staff).")
        
        # We can bulk delete them because of the cascading foreign keys in the database.
        user_ids = [u.user_id for u in users_to_delete]
        
        print("Deleting users...")
        db.query(models.User).filter(models.User.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.commit()
        
        print("✅ Successfully deleted all players, team owners, managers, and analysts.")
        print("You can now start completely fresh!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error occurred: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    reset_db_users()

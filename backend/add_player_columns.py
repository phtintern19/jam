"""
Script to add new columns to the players table without dropping data
"""
from database import engine, SessionLocal
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_player_columns():
    """Add new performance metrics and achievements columns to players table"""
    print("=== Adding New Columns to Players Table ===\n")
    
    try:
        with engine.connect() as conn:
            # Check if columns already exist
            result = conn.execute(text("SHOW COLUMNS FROM players"))
            existing_columns = [row[0] for row in result]
            print(f"Existing columns: {existing_columns}")
            
            # List of columns to add
            columns_to_add = [
                ("total_events_participated", "INT DEFAULT 0"),
                ("auction_success_rate", "INT DEFAULT 0"),
                ("average_bid_amount", "DECIMAL(12, 2) DEFAULT 0.00"),
                ("highest_winning_bid", "DECIMAL(12, 2) DEFAULT 0.00"),
                ("teams_interested", "INT DEFAULT 0"),
                ("profile_views", "INT DEFAULT 0"),
                ("tournaments_won", "INT DEFAULT 0"),
                ("mvp_awards", "INT DEFAULT 0"),
                ("best_player_awards", "INT DEFAULT 0"),
                ("state_level_champion", "BOOLEAN DEFAULT FALSE"),
                ("international_experience", "BOOLEAN DEFAULT FALSE"),
                ("professional_contracts", "INT DEFAULT 0")
            ]
            
            for column_name, column_def in columns_to_add:
                if column_name not in existing_columns:
                    alter_sql = f"ALTER TABLE players ADD COLUMN {column_name} {column_def}"
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
    if add_player_columns():
        print("\nYou can now run the application with: python app.py")
    else:
        print("\nFailed to add columns.")

import os
import sys
from sqlalchemy import text
from database import engine

def column_exists(conn, table, column):
    if engine.dialect.name == 'sqlite':
        result = conn.execute(text(f"PRAGMA table_info({table});")).fetchall()
        return any(row[1] == column for row in result)
    else:
        # MySQL / PostgreSQL
        db_name = os.getenv("DB_NAME", "")
        if not db_name:
            result = conn.execute(text(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{table}';")).fetchall()
        else:
            result = conn.execute(text(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '{db_name}' AND TABLE_NAME = '{table}';")).fetchall()
        return any(row[0] == column for row in result)

def add_columns():
    print(f"Connecting to database with dialect: {engine.dialect.name}")
    with engine.begin() as conn:
        # Check and add current_team_id
        if not column_exists(conn, "auctions", "current_team_id"):
            print("Adding current_team_id...")
            try:
                if engine.dialect.name == 'sqlite':
                    conn.execute(text("ALTER TABLE auctions ADD COLUMN current_team_id INTEGER REFERENCES teams(team_id) ON DELETE SET NULL;"))
                else:
                    conn.execute(text("ALTER TABLE auctions ADD COLUMN current_team_id INT NULL;"))
                    conn.execute(text("ALTER TABLE auctions ADD CONSTRAINT fk_auction_current_team FOREIGN KEY (current_team_id) REFERENCES teams(team_id) ON DELETE SET NULL;"))
                print("current_team_id added successfully.")
            except Exception as e:
                print(f"Error adding current_team_id: {e}")
        else:
            print("current_team_id already exists.")

        # Check and add paused_time_left
        if not column_exists(conn, "auctions", "paused_time_left"):
            print("Adding paused_time_left...")
            try:
                conn.execute(text("ALTER TABLE auctions ADD COLUMN paused_time_left DECIMAL(10, 2) NULL;"))
                print("paused_time_left added successfully.")
            except Exception as e:
                print(f"Error adding paused_time_left: {e}")
        else:
            print("paused_time_left already exists.")

        # Check and add bid_deadline
        if not column_exists(conn, "auctions", "bid_deadline"):
            print("Adding bid_deadline...")
            try:
                conn.execute(text("ALTER TABLE auctions ADD COLUMN bid_deadline DATETIME NULL;"))
                print("bid_deadline added successfully.")
            except Exception as e:
                print(f"Error adding bid_deadline: {e}")
        else:
            print("bid_deadline already exists.")

if __name__ == "__main__":
    add_columns()
    print("Migration complete. Safe and idempotent.")

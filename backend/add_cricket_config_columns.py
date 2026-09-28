import os
import sys
import logging
from sqlalchemy import text, inspect
from database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def column_exists(connection, table_name, column_name):
    # Cross-database compat check
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def fk_exists(connection, table_name, fk_name):
    inspector = inspect(engine)
    fks = inspector.get_foreign_keys(table_name)
    for fk in fks:
        if fk['name'] == fk_name:
            return True
    return False

def migrate():
    logger.info("Starting safe migration for Cricket configuration columns...")
    try:
        with engine.begin() as conn:
            # 1. SPORTS TABLE
            for col in ['roles_config', 'categories_config', 'attributes_schema', 'default_auction_rules']:
                if not column_exists(conn, 'sports', col):
                    conn.execute(text(f"ALTER TABLE sports ADD COLUMN {col} JSON NULL"))
                    logger.info(f"Added {col} to sports table.")
                else:
                    logger.info(f"Skipped {col} in sports (already exists).")

            # 2. EVENTS TABLE
            if not column_exists(conn, 'events', 'sport_id'):
                conn.execute(text("ALTER TABLE events ADD COLUMN sport_id INTEGER NULL"))
                logger.info("Added sport_id to events table.")
            else:
                logger.info("Skipped sport_id in events (already exists).")

            # Add foreign key safely (MySQL only, SQLite does not support ADD CONSTRAINT)
            fk_name = "fk_events_sports"
            if engine.dialect.name != 'sqlite':
                if not fk_exists(conn, 'events', fk_name):
                    # Ensure sport_id matches sports.sport_id type (INT)
                    conn.execute(text(f"ALTER TABLE events ADD CONSTRAINT {fk_name} FOREIGN KEY (sport_id) REFERENCES sports(sport_id) ON DELETE SET NULL"))
                    logger.info(f"Added foreign key {fk_name} to events table.")
                else:
                    logger.info(f"Skipped foreign key {fk_name} (already exists).")
            else:
                logger.info(f"Skipped foreign key {fk_name} (SQLite does not support ALTER TABLE ADD CONSTRAINT).")

            if not column_exists(conn, 'events', 'event_config'):
                conn.execute(text("ALTER TABLE events ADD COLUMN event_config JSON NULL"))
                logger.info("Added event_config to events table.")
            else:
                logger.info("Skipped event_config in events (already exists).")

            # 3. PLAYERS TABLE
            if not column_exists(conn, 'players', 'sport_profiles'):
                conn.execute(text("ALTER TABLE players ADD COLUMN sport_profiles JSON NULL"))
                logger.info("Added sport_profiles to players table.")
            else:
                logger.info("Skipped sport_profiles in players (already exists).")

        logger.info("Migration completed successfully.")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate()

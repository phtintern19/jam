from database import engine
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users MODIFY COLUMN user_type ENUM('admin', 'team_owner', 'team_manager', 'team_analyst', 'player') NOT NULL;"))
        conn.commit()
        logger.info("Database ENUM updated successfully!")
except Exception as e:
    logger.error(f"Error updating ENUM: {e}")

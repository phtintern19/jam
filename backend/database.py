from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
import os
from dotenv import load_dotenv
from contextlib import contextmanager
import logging

# Configure logging
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Database configuration
USE_SQLITE = os.getenv("USE_SQLITE", "false").lower() == "true"
DB_USER = os.getenv("DB_USER", "bidzone")
DB_PASSWORD = os.getenv("DB_PASSWORD", "bedsur123")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "bidzone")

# Create database URL dynamically from environment variables
if USE_SQLITE:
    SQLALCHEMY_DATABASE_URL = "sqlite:///bidzone.db"
    logger.info("Using SQLite database")
else:
    SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    logger.info(f"Using MySQL database: {DB_HOST}:{DB_PORT}/{DB_NAME}")

# Connection pool settings with robust defaults
POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '15'))
MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', '25'))
POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', '45'))
POOL_RECYCLE = int(os.getenv('DB_POOL_RECYCLE', '3600'))

# Create SQLAlchemy engine with optimized settings
if USE_SQLITE:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        echo=False,                    # Disable SQL query logging
        connect_args={"check_same_thread": False}  # SQLite specific
    )
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,           # Check connections before using them
        pool_recycle=3600,            # Recycle connections after 1 hour
        pool_size=POOL_SIZE,                  # Number of connections to keep open
        max_overflow=MAX_OVERFLOW,              # Max overflow connections
        pool_timeout=POOL_TIMEOUT,              # Seconds to wait before giving up on getting a connection
        echo=False,                    # Disable SQL query logging
        connect_args={
            'connect_timeout': 10,    # Connection timeout in seconds
        }
    )

# Session factory with autoflush disabled for better performance
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # Prevents session expiration after commit
)

# Base class for models
Base = declarative_base()

def get_db():
    """Dependency for FastAPI to get DB session with proper cleanup"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    try:
        import models  # Import models to register them with SQLAlchemy
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully.")
        return True
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        return False

def drop_db():
    """Drop all database tables (use with caution)"""
    try:
        import models  # Import models to ensure they're registered
        Base.metadata.drop_all(bind=engine)
        logger.info("All database tables dropped.")
        return True
    except Exception as e:
        logger.error(f"Error dropping database: {e}")
        return False

# Initialize database tables when this module is imported
# init_db()  # Uncomment if you want to auto-create tables on import
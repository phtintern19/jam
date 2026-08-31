from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import logging
from urllib.parse import quote_plus

# Get absolute path to the directory containing this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configure logging
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Load environment variables from .env file explicitly using absolute path
load_dotenv(os.path.join(BASE_DIR, '.env'))

# Database configuration (cPanel MySQL: use panel DB_* values; never ship real passwords as defaults)
USE_SQLITE = os.getenv("USE_SQLITE", "false").lower() == "true"
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "")

# Create database URL dynamically from environment variables
if USE_SQLITE:
    SQLALCHEMY_DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'bidzone.db')}"
    logger.info("Using SQLite database")
else:
    if not all([DB_USER, DB_PASSWORD, DB_NAME]):
        logger.error(
            "MySQL config incomplete. Set DB_USER, DB_PASSWORD, and DB_NAME in .env "
            "(or set USE_SQLITE=true for local/dev)."
        )
    # URL-encode credentials so special characters in cPanel passwords work
    user_q = quote_plus(DB_USER)
    pass_q = quote_plus(DB_PASSWORD)
    SQLALCHEMY_DATABASE_URL = (
        f"mysql+pymysql://{user_q}:{pass_q}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    logger.info(f"Using MySQL database: {DB_HOST}:{DB_PORT}/{DB_NAME}")

# Connection pool — conservative defaults for cPanel shared hosting
# (large pools exhaust MySQL max_user_connections on shared plans)
POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '5'))
MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', '10'))
POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', '30'))
# Recycle before typical MySQL wait_timeout (often 300s on cPanel)
POOL_RECYCLE = int(os.getenv('DB_POOL_RECYCLE', '280'))

# Create SQLAlchemy engine with optimized settings
if USE_SQLITE:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=POOL_RECYCLE,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
        echo=False,
        connect_args={
            'connect_timeout': 10,
        }
    )

# Session factory with autoflush disabled for better performance
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)

# Base class for models
Base = declarative_base()

def get_db():
    """Yield a DB session with proper cleanup (WSGI / Flask compatible)."""
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

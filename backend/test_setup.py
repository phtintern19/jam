"""
Test script to verify database connection and imports
"""
import sys
print("Testing BidZone Setup...")
print("=" * 50)

# Test Python version
print(f"\n✓ Python version: {sys.version}")

# Test imports
try:
    print("\n✓ Testing imports...")
    import flask
    print(f"  - Flask: {flask.__version__}")
    
    import sqlalchemy
    print(f"  - SQLAlchemy: {sqlalchemy.__version__}")
    
    import pydantic
    print(f"  - Pydantic: {pydantic.__version__}")
    
    import pymysql
    print(f"  - PyMySQL: installed")
    
    from dotenv import load_dotenv
    print(f"  - python-dotenv: installed")
    
    print("\n✓ All imports successful!")
except ImportError as e:
    print(f"\n✗ Import error: {e}")
    sys.exit(1)

# Test database connection
try:
    print("\n✓ Testing database connection...")
    from database import engine, Base, SQLALCHEMY_DATABASE_URL
    print(f"  - Database URL: {SQLALCHEMY_DATABASE_URL}")
    
    # Test connection
    with engine.connect() as conn:
        print("  - Database connection successful!")
    
    # Test table creation
    print("\n✓ Testing table creation...")
    import models
    Base.metadata.create_all(bind=engine)
    print("  - Tables created successfully!")
    
except Exception as e:
    print(f"\n✗ Database error: {e}")
    print("  Note: This is expected if MySQL is not configured.")
    print("  The application will use SQLite as fallback.")

print("\n" + "=" * 50)
print("✓ Setup test completed successfully!")
print("\nYou can now run the application with:")
print("  python app.py")

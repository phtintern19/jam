"""
Script to create an admin user for the BidZone application
"""
from database import SessionLocal
from models import User, UserType
import bcrypt
import sys

def create_admin_user():
    """Create an admin user with default credentials"""
    print("=== Creating Admin User ===\n")
    
    # Admin credentials
    admin_username = "admin"
    admin_password = "admin123"
    admin_email = "admin@bidzone.com"
    
    try:
        # Create database session
        db = SessionLocal()
        
        # Check if admin user already exists
        existing_admin = db.query(User).filter(User.username == admin_username).first()
        if existing_admin:
            print(f"Admin user '{admin_username}' already exists.")
            choice = input("Do you want to reset the password? (y/n): ")
            if choice.lower() == 'y':
                # Update password
                password_bytes = admin_password.encode('utf-8')[:72]
                existing_admin.password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')
                db.commit()
                print(f"✓ Admin password reset successfully!")
                print_admin_credentials(admin_username, admin_password, admin_email)
            else:
                print("No changes made.")
            return True
        
        # Hash the password (bcrypt has 72-byte limit)
        password_bytes = admin_password.encode('utf-8')[:72]
        password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')
        
        # Create admin user
        admin_user = User(
            username=admin_username,
            password_hash=password_hash,
            email=admin_email,
            user_type=UserType.admin,
            is_active=True,
            is_verified=True
        )
        
        # Add to database
        db.add(admin_user)
        db.commit()
        
        print("✓ Admin user created successfully!")
        print_admin_credentials(admin_username, admin_password, admin_email)
        
        db.close()
        return True
        
    except Exception as e:
        print(f"✗ Error creating admin user: {e}")
        return False

def print_admin_credentials(username, password, email):
    """Print admin credentials"""
    print("\n" + "="*50)
    print("ADMIN CREDENTIALS")
    print("="*50)
    print(f"Username: {username}")
    print(f"Password: {password}")
    print(f"Email: {email}")
    print("="*50)
    print("\n⚠️  IMPORTANT: Change the default password after first login!")
    print("="*50)

if __name__ == "__main__":
    if create_admin_user():
        print("\nYou can now login with these credentials.")
    else:
        print("\nFailed to create admin user.")
        sys.exit(1)

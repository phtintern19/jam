"""
Database setup script for BidZone
This script creates the MySQL database and user if they don't exist
"""
import pymysql
import sys
import os
from dotenv import load_dotenv

load_dotenv()

def setup_database():
    print("=== BidZone Database Setup ===\n")
    
    # Get MySQL root password from environment or prompt
    root_password = os.getenv("MYSQL_ROOT_PASSWORD")
    if not root_password:
        print("Please set MYSQL_ROOT_PASSWORD in your .env file")
        print("Or enter it here (will not be saved):")
        root_password = input("Enter MySQL root password: ")
    
    try:
        # Connect to MySQL as root
        print("\nConnecting to MySQL as root...")
        connection = pymysql.connect(
            host='localhost',
            user='root',
            password=root_password,
            charset='utf8mb4'
        )
        
        cursor = connection.cursor()
        
        # Create database if it doesn't exist
        print("Creating database 'bidzone' if it doesn't exist...")
        cursor.execute("CREATE DATABASE IF NOT EXISTS bidzone CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        
        # Create user if it doesn't exist
        print("Creating user 'bidzone' if it doesn't exist...")
        try:
            cursor.execute("CREATE USER IF NOT EXISTS 'bidzone'@'localhost' IDENTIFIED BY 'bedsur123'")
        except pymysql.Error as e:
            print(f"Note: {e}")
        
        # Grant all privileges on bidzone database
        print("Granting privileges to 'bidzone' user...")
        cursor.execute("GRANT ALL PRIVILEGES ON bidzone.* TO 'bidzone'@'localhost'")
        cursor.execute("FLUSH PRIVILEGES")
        
        print("\n✓ Database setup completed successfully!")
        print("  - Database: bidzone")
        print("  - User: bidzone")
        print("  - Password: bedsur123")
        
        cursor.close()
        connection.close()
        
        return True
        
    except pymysql.Error as e:
        print(f"\n✗ Error: {e}")
        print("Please ensure:")
        print("  1. MySQL server is running")
        print("  2. Root password is correct")
        print("  3. You have sufficient privileges")
        return False

if __name__ == "__main__":
    if setup_database():
        print("\nYou can now run the application with: python app.py")
    else:
        print("\nDatabase setup failed. Please fix the errors above.")
        sys.exit(1)

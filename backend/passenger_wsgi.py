"""
Passenger WSGI entry point for cPanel compatibility.
This file is required for cPanel Python App Manager to run the Flask application.
"""
import sys
import os

# Add the backend directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the Flask app
from app import app

# Passenger requires the variable to be named 'application'
application = app

if __name__ == "__main__":
    # For local testing
    app.run(host='0.0.0.0', port=5000, debug=False)


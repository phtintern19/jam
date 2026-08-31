import sys
import os
import logging
from typing import List, Optional, Dict, Any, Union
import secrets
import uuid
from datetime import datetime, timedelta

from werkzeug.exceptions import HTTPException
from flask import Flask, request, jsonify, abort, send_from_directory, render_template, make_response, session, send_file, redirect
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from sqlalchemy.exc import SQLAlchemyError
from passlib.context import CryptContext
import bcrypt
import psutil
import json
import re
import time
import random
import string
import hashlib
import hmac
import base64
from jose import JWTError, jwt
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, EmailStr, Field

# Load environment variables (Passenger-safe absolute paths)
APP_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(APP_DIR)
def is_valid_frontend(path):
    if not path or not os.path.exists(path):
        return False
    return os.path.exists(os.path.join(path, 'index.html')) or os.path.exists(os.path.join(path, 'templates', 'team-owner-dashboard.html'))

FRONTEND_DIR_ENV = os.getenv('FRONTEND_DIR')
FRONTEND_DIR = None

if is_valid_frontend(FRONTEND_DIR_ENV):
    FRONTEND_DIR = FRONTEND_DIR_ENV
else:
    # Safely search for the real frontend directory containing our templates/index.html
    _candidates = [
        os.path.join(APP_DIR, 'frontend'),                     # If deployed inside backend
        os.path.join(BASE_DIR, 'jamrig.2lz.in'),               # cPanel subdomain root
        os.path.join(BASE_DIR, 'public_html', 'jamrig.2lz.in'),# Subdomain inside public_html
        os.path.join(BASE_DIR, 'public_html'),                 # Main cPanel web root
        os.path.join(BASE_DIR, 'frontend'),                    # Sibling to backend
    ]
    
    for candidate in _candidates:
        if is_valid_frontend(candidate):
            FRONTEND_DIR = candidate
            break
            
if not FRONTEND_DIR:
    # Fallback to the environment variable if provided, else a default
    FRONTEND_DIR = FRONTEND_DIR_ENV if FRONTEND_DIR_ENV else os.path.join(BASE_DIR, 'jamrig.2lz.in')

TEMPLATES_DIR = os.path.join(FRONTEND_DIR, 'templates')
STATIC_DIR = os.path.join(FRONTEND_DIR, 'static')
CSS_DIR = os.path.join(FRONTEND_DIR, 'css')
JS_DIR = os.path.join(FRONTEND_DIR, 'js')

load_dotenv(os.path.join(APP_DIR, '.env'))
load_dotenv()  # Fallback for cPanel env vars injected by the panel

# Configure logging (stream always; file only if writable — shared hosting often restricts this)
_log_handlers = [logging.StreamHandler()]
try:
    _log_file = os.path.join(APP_DIR, 'app.log')
    _log_handlers.append(logging.FileHandler(_log_file))
except OSError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=_log_handlers
)
logger = logging.getLogger(__name__)

# Ensure upload directories exist under frontend/static (writable on cPanel)
os.makedirs(os.path.join(STATIC_DIR, 'uploads', 'profile_images'), exist_ok=True)

# Initialize Flask — static/templates point at sibling frontend/ for Passenger deploys
app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    static_url_path='/static',
    template_folder=TEMPLATES_DIR,
)

# Initialize SocketIO for Real-Time Auction
socketio = SocketIO(app, cors_allowed_origins="*")

# Production / cPanel defaults
IS_PRODUCTION = os.getenv("FLASK_ENV", "production").lower() != "development"
ENABLE_SETUP_ROUTES = os.getenv("ENABLE_SETUP_ROUTES", "false").lower() == "true"

# Configure CORS (comma-separated FRONTEND_URL allowed; "*" = any origin without credentials reflection issues)
_raw_origins = os.getenv("FRONTEND_URL", "*").strip()
if _raw_origins == "*":
    # Wildcard + credentials is invalid per CORS spec; allow all origins without forcing credentials header quirks
    CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)
else:
    CORS_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
    CORS(app, resources={r"/*": {"origins": CORS_ORIGINS}}, supports_credentials=True)

# App Configuration from Env
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "fallback-secret-key-change-me")
app.config['SESSION_COOKIE_NAME'] = "session_token"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=60 * 24 * 7)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv(
    "SESSION_COOKIE_SECURE",
    "true" if IS_PRODUCTION else "false"
).lower() == "true"
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv("MAX_CONTENT_LENGTH", 6 * 1024 * 1024))  # 6MB

# Trust cPanel / reverse-proxy headers when enabled
if os.getenv("USE_PROXY_FIX", "true").lower() == "true":
    try:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    except Exception as e:
        logger.warning(f"ProxyFix not applied: {e}")

SECRET_KEY = app.config['SECRET_KEY']
SESSION_COOKIE_NAME = app.config['SESSION_COOKIE_NAME']

# Pydantic Settings
class Settings(BaseSettings):
    app_name: str = "Sports Auction Platform API"
    secret_key: str = os.getenv("SECRET_KEY", "fallback-secret-key-change-me")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(APP_DIR, 'bidzone.db')}")
    environment: str = os.getenv("FLASK_ENV", "production")
    debug: bool = False
    cors_origins: str = os.getenv("FRONTEND_URL", "*")
    session_cookie_name: str = "session_token"
    session_expire_minutes: int = 60 * 24 * 7
    model_config = SettingsConfigDict(
        env_file=os.path.join(APP_DIR, ".env"),
        env_file_encoding='utf-8',
        extra='ignore',
        case_sensitive=True,
        env_prefix='',
    )

settings = Settings()

# Imports dependent on config
from database import Base, engine, SessionLocal
import models
import schemas

# Custom error handlers for production
@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(405)
def handle_client_error(error):
    return jsonify({"error": error.name, "message": error.description if hasattr(error, 'description') else str(error)}), error.code

@app.errorhandler(404)
def not_found_error(error):
    # API clients get JSON
    if request.path.startswith('/api/'):
        return jsonify({"error": "Route not found"}), 404
    
    # Browser page misses (like SPA routes) should fall back to index.html instead of showing JSON
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return send_file(index_path)
    # Give a clear error message instead of just 404 text if index.html is missing
    return f"404 Not Found. index.html not found at {index_path}. Checked dirs: FRONTEND_DIR is {FRONTEND_DIR}", 404

@app.errorhandler(500)
@app.errorhandler(Exception)
def internal_error(error):
    if isinstance(error, HTTPException):
        return jsonify({"error": error.name, "message": error.description}), error.code
    logger.error(f"Server Error: {str(error)}", exc_info=True)
    return jsonify({"error": "Internal server error"}), 500

@app.after_request
def add_cache_control(response):
    if request.path.startswith('/api/'):
        # Only apply caching logic to successful GET requests
        if request.method == 'GET' and response.status_code == 200:
            # Highly dynamic endpoints (Events, Auctions) get strictly no cache
            if any(path in request.path for path in ['/events', '/auction']):
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
            else:
                # Smart caching using ETags for all other API endpoints
                response.add_etag()
                response.make_conditional(request)
                response.headers['Cache-Control'] = 'private, must-revalidate, max-age=0'
        elif request.method != 'GET':
            # Disable caching for POST/PUT/DELETE
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

# Password hashing configuration
pwd_context = CryptContext(
    schemes=["bcrypt"],
    default="bcrypt",
    bcrypt__rounds=12,
    deprecated="auto"
)

# Helper function to create session in database

def create_session(user_id: str, db: Session) -> str:
    """Create a new session for the user in the database and return the session token."""
    # Clean up expired sessions first
    cleanup_sessions(db)
    
    session_token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(minutes=settings.session_expire_minutes)
    
    db_session = models.Session(
        session_id=str(uuid.uuid4()),
        session_token=session_token,
        user_id=user_id,
        expires_at=expires_at
    )
    db.add(db_session)
    db.commit()
    
    return session_token

# Clean up expired sessions from database
def cleanup_sessions(db: Session):
    """Delete expired sessions from the database."""
    db.query(models.Session).filter(
        models.Session.expires_at < datetime.utcnow()
    ).delete()
    db.commit()

# Database dependency imported from database module
from database import get_db

# Dependency to get current user from session
def get_current_user():
    """
    Get the current authenticated user from the session.
    
    Returns:
        User: The authenticated user object
        
    Raises:
        abort: If user is not authenticated or session is invalid
    """
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    
    if not session_token:
        abort(401, description="Not authenticated")
    
    db = SessionLocal()
    try:
        # Query session from database
        db_session = db.query(models.Session).filter(
            models.Session.session_token == session_token
        ).first()
        
        if not db_session:
            abort(401, description="Not authenticated")
        
        # Check if session expired
        if db_session.expires_at < datetime.utcnow():
            db.delete(db_session)
            db.commit()
            abort(401, description="Session expired")
        
        # Update last activity time only if it's been more than a minute since the last update
        # This significantly reduces database load and lock contention on high-frequency requests
        now = datetime.utcnow()
        if (not db_session.last_activity) or (now - db_session.last_activity > timedelta(minutes=1)):
            try:
                db_session.last_activity = now
                db_session.expires_at = now + timedelta(minutes=settings.session_expire_minutes)
                db.commit()
            except HTTPException:
                raise
            except Exception as e:
                db.rollback()
                logger.warning(f"Failed to update session activity: {str(e)}")
                # Continue anyway, activity update is not critical for the current request

        
        # Get user from database with eager loading to prevent DetachedInstanceError
        from sqlalchemy.orm import joinedload
        user = db.query(models.User).options(
            joinedload(models.User.player),
            joinedload(models.User.team_owner),
            joinedload(models.User.parent_user)
        ).filter(models.User.user_id == db_session.user_id).first()
        
        if not user:
            abort(404, description="User not found")
            
        if not user.is_active:
            abort(403, description="User account is inactive")
            
        return user
    finally:
        db.close()

# Password hashing
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    # Bcrypt has a 72-byte limit. We strictly enforce this on the bytes.
    if isinstance(password, str):
        password_bytes = password.encode('utf-8')
    elif isinstance(password, bytes):
        password_bytes = password
    else:
        password_bytes = str(password).encode('utf-8')
    
    # Truncate to 71 bytes to clearly avoid the 72 byte limit
    if len(password_bytes) > 71:
        password_bytes = password_bytes[:71]
        
    # Generate salt and hash
    # bcrypt.hashpw returns bytes, we decode to string for storage
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode('utf-8')

# Flask static routes (css/js live beside frontend/, not under Flask's default static/)
# /static/ is handled by Flask's built-in static_folder (STATIC_DIR)

@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(CSS_DIR, filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(JS_DIR, filename)

# Setup helper — disabled in production unless ENABLE_SETUP_ROUTES=true
if ENABLE_SETUP_ROUTES:
    @app.route('/create-admin-now')
    def temp_create_admin():
        import create_admin
        success = create_admin.create_admin_user()
        if success:
            return "Admin user created successfully! You can now log in."
        return "Failed to create admin user. Check the server logs."

@app.route('/dashboard')
@app.route('/dashboard/manager')
@app.route('/dashboard/analyst')
def serve_dashboard_routes():
    # Serve the unified dashboard for all team staff roles
    return send_from_directory(TEMPLATES_DIR, 'team-owner-dashboard.html')

@app.route('/templates/<path:filename>')
def serve_templates(filename):
    return send_from_directory(TEMPLATES_DIR, filename)

@app.route('/<path:filename>')
def serve_root_files(filename):
    if filename.endswith('.html'):
        # First check templates dir (for things like team-owner-dashboard.html)
        if os.path.exists(os.path.join(TEMPLATES_DIR, filename)):
            return send_from_directory(TEMPLATES_DIR, filename)
        # Then check frontend dir (for things like index.html)
        if os.path.exists(os.path.join(FRONTEND_DIR, filename)):
            return send_from_directory(FRONTEND_DIR, filename)
    
    # Let 404 handler take over for SPA routing
    abort(404)

# Models are imported from schemas.py
# Endpoints are consolidated below


@app.route("/api/users/<int:user_id>", methods=['GET', 'PUT'])
def get_user_full_details(user_id: int):
    """Get full details of a user (including player/team owner info) or update profile"""
    from sqlalchemy.orm import joinedload
    
    current_user = get_current_user()
    if current_user.user_id != user_id and current_user.user_type.value != 'admin':
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    db = SessionLocal()
    try:
        # Handle PUT Request
        if request.method == 'PUT':
            payload = request.get_json()
            if not payload:
                return jsonify({"success": False, "message": "Invalid JSON"}), 400
                
            # We only allow updating the Player profile for now.
            # (Admins might update other things but this meets the prompt requirement)
            player_obj = db.query(models.Player).filter(models.Player.user_id == user_id).first()
            if player_obj:
                if 'first_name' in payload: player_obj.first_name = payload['first_name']
                if 'last_name' in payload: player_obj.last_name = payload['last_name']
                if 'city' in payload: player_obj.city = payload['city']
                if 'country' in payload: player_obj.country = payload['country']
                if 'phone' in payload: player_obj.phone = payload['phone']
                if 'bio' in payload: player_obj.bio = payload['bio']
                db.commit()
                return jsonify({"success": True, "message": "Profile updated successfully"})
            else:
                return jsonify({"success": False, "message": "Player profile not found"}), 404

        # Handle GET Request (Original logic)
        # Eager load player relationships to avoid DetachedInstanceError
        user_obj = db.query(models.User).options(
            joinedload(models.User.player)
        ).filter(models.User.user_id == user_id).first()
        
        if not user_obj:
            return jsonify({"success": False, "message": "User not found"}), 404
            
        user_data = {
            "user_id": user_obj.user_id,
            "username": user_obj.username,
            "email": user_obj.email,
            "phone": user_obj.phone,
            "user_type": user_obj.user_type.value if hasattr(user_obj.user_type, 'value') else user_obj.user_type,
            "created_at": user_obj.created_at,
            "is_active": user_obj.is_active,
            "is_verified": user_obj.is_verified,
            "last_login": user_obj.last_login
        }
        
        # Enrich with Team Owner details
        if (hasattr(user_obj.user_type, 'value') and user_obj.user_type.value == 'team_owner') or user_obj.user_type == 'team_owner':
            if user_obj.team_owner:
                owner = user_obj.team_owner
                user_data.update({
                    "team_owner_id": owner.team_owner_id,
                    "owner_name": owner.owner_name,
                    "company_name": owner.company_name,
                    "gst_number": owner.gst_number,
                    "address": owner.address,
                    "city": owner.city,
                    "state": owner.state,
                    "country": owner.country,
                    "pincode": owner.pincode,
                    "wallet_balance": float(owner.wallet_balance) if owner.wallet_balance else 0.0,
                    "team_logo_url": owner.team_logo_url
                })
                
                # Try to find associated team
                try:
                     team = db.query(models.Team).filter(models.Team.owner_id == owner.team_owner_id).first()
                     if team:
                         user_data.update({
                             "team_id": team.team_id,
                             "team_name": team.team_name,
                             "event_id": team.event_id,
                             "team_status": team.status
                         })
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Error fetching team for owner {owner.team_owner_id}: {e}")

        # Enrich with Player details
        elif ((hasattr(user_obj.user_type, 'value') and user_obj.user_type.value == 'player') or user_obj.user_type == 'player') and user_obj.player:
            player = user_obj.player
            user_data.update({
                "player_id": player.player_id,
                "name": f"{player.first_name} {player.last_name}",
                "first_name": player.first_name,
                "last_name": player.last_name,
                "date_of_birth": player.date_of_birth,
                "gender": player.gender.value if hasattr(player.gender, 'value') else player.gender,
                "profile_image_url": getattr(player, "profile_image_url", None),
                "avatar": getattr(player, "profile_image_url", None),
                "bio": player.bio,
                "address": player.address,
                "city": player.city,
                "state": player.state,
                "country": player.country,
                "pincode": player.pincode,
                "height_cm": player.height_cm,
                "weight_kg": player.weight_kg,
                
                # Dashboard KPIs and averages
                "successRate": getattr(player, "auction_success_rate", 0),
                "avgBid": float(getattr(player, "average_bid_amount", 0.0) or 0.0),
                "currentValue": float(getattr(player, "highest_winning_bid", 0.0) or 0.0),
                "eventsCount": getattr(player, "total_events_participated", 0),
                "teamsInterested": getattr(player, "teams_interested", 0),
                "profileViews": getattr(player, "profile_views", 0),
                
                # Skills
                "basketball_rating": getattr(player, "basketball_rating", None),
                "football_rating": getattr(player, "football_rating", None),
                "cricket_rating": getattr(player, "cricket_rating", None),
                
                # Achievements
                "tournamentsWon": getattr(player, "tournaments_won", 0),
                "mvpAwards": getattr(player, "mvp_awards", 0),
                "bestPlayerAwards": getattr(player, "best_player_awards", 0),
                "proContracts": getattr(player, "professional_contracts", 0),
                "stateChampion": "Yes" if getattr(player, "state_level_champion", False) else "No",
                "internationalExp": "Yes" if getattr(player, "international_experience", False) else "No"
            })

        # Calculate a simple avgRating for the UI based on non-null ratings
        if "cricket_rating" in user_data:
            ratings = [r for r in [user_data.get("cricket_rating"), user_data.get("football_rating"), user_data.get("basketball_rating")] if r is not None]
            user_data["avgRating"] = round(sum(ratings) / len(ratings), 1) if ratings else '--'

        return jsonify(user_data)
    finally:
        db.close()

# Event management endpoints moved to consolidated section below.




# Legacy endpoints removed. Use /api/ prefixed database-driven endpoints instead.


@app.route("/api/team-owner/dashboard")
def get_team_owner_dashboard():
    """
    Get dashboard data for the logged-in team owner.
    """
    try:
        current_user = get_current_user()
        db = SessionLocal()
        
        try:
            # Re-attach current_user to the current session to avoid DetachedInstanceError
            current_user = db.merge(current_user)
            
            # Check if user is team owner, manager, or analyst
            user_type_str = current_user.user_type.value if hasattr(current_user.user_type, 'value') else str(current_user.user_type)
            if user_type_str not in ['team_owner', 'team_manager', 'team_analyst']:
                abort(403, description="Only team owners and staff can access this dashboard")
            
            # Get team owner profile
            if user_type_str in ['team_manager', 'team_analyst']:
                parent_user = db.query(models.User).filter(models.User.user_id == current_user.parent_user_id).first()
                team_owner = parent_user.team_owner if parent_user else None
            else:
                team_owner = current_user.team_owner
                
            if not team_owner:
                # Should not happen if registered correctly, but handle gracefully
                return jsonify({
                    "username": current_user.username,
                    "wallet_balance": 0,
                    "team_name": "No Team Assigned",
                    "squad": [],
                    "my_teams": []
                })
                
            # Get all teams for this owner
            my_teams = []
            if team_owner.teams:
                for t in team_owner.teams:
                    # Get event name for the dropdown
                    event_title = "Unknown Event"
                    if t.event_id:
                         ev = db.query(models.Event).filter(models.Event.event_id == t.event_id).first()
                         if ev: event_title = ev.title
                    
                    my_teams.append({
                        "team_id": t.team_id,
                        "team_name": t.team_name,
                        "event_id": t.event_id,
                        "event_title": event_title
                    })

            # Select the specific team
            team = None
            team_id = request.args.get('team_id', type=int)
            if team_id:
                 # Verify ownership
                 team = next((t for t in team_owner.teams if t.team_id == team_id), None)
                 if not team:
                     abort(404, description="Team not found or does not belong to you")
            elif team_owner.teams:
                # Default to first team
                team = team_owner.teams[0]
                
            squad_data = []
            team_name = team_owner.company_name or "My Team"
            
            if team:
                team_name = team.team_name
                # Get players in the squad
                for team_player in team.players:
                    player = team_player.player
                    # Calculate price (this might need to come from the auction bid or team_player record if stored)
                    # For now, we'll try to find the winning bid or use a placeholder
                    price = 0
                    # Try to find the winning bid for this player by this team
                    winning_bid = db.query(models.Bid).filter(
                        models.Bid.player_id == player.player_id,
                        models.Bid.team_id == team.team_id,
                        models.Bid.status == 'won'
                    ).first()
                    
                    if winning_bid:
                        price = float(winning_bid.amount)
                    
                    squad_data.append({
                        "id": player.player_id,
                        "name": player.full_name,
                        "sport": "Cricket", # Default or fetch from player skills/event
                        "category": "Standard", # Default or logic to determine
                        "avatar": player.profile_image_url or "",
                        "price": price,
                        "rating": 8.0 # Placeholder or fetch
                    })
                    
            # Check for active auction or scheduled event for this team's event
            active_auction_data = None
            participating_players = []
            if team and team.event_id:
                # Get participating players for the event
                event = db.query(models.Event).filter(models.Event.event_id == team.event_id).first()
                if event:
                    for player in event.players:
                        participating_players.append({
                            "id": player.player_id,
                            "name": player.full_name,
                            "avatar": player.profile_image_url or "",
                            "rating": 8.0 # Placeholder
                        })

                auction = db.query(models.Auction).filter(
                    models.Auction.event_id == team.event_id,
                    models.Auction.status.in_(['in_progress'])
                ).first()

                if auction:
                     # Get current player details if any
                     current_player_data = None
                     if auction.current_player:
                         # Calculate time left
                         time_left = 0
                         if auction.current_player_bid_start:
                             elapsed = (datetime.utcnow() - auction.current_player_bid_start).total_seconds()
                             time_left = max(0, (event.bid_time_limit or 20) - elapsed)

                         current_player_data = {
                             "id": auction.current_player.player_id,
                             "name": auction.current_player.full_name,
                             "sport": "Cricket", 
                             "category": "Standard", 
                             "basePrice": float(auction.current_bid_amount), 
                             "rating": 8.5,
                             "time_left": time_left,
                             "bid_start": auction.current_player_bid_start.isoformat() if auction.current_player_bid_start else None
                         }
                         
                     active_auction_data = {
                         "auction_id": auction.auction_id,
                         "event_id": auction.event_id,
                         "status": "RUNNING",
                         "current_bid": float(auction.current_bid_amount),
                         "bid_time_limit": event.bid_time_limit or 20,
                         "current_player": current_player_data,
                         "highest_bidder": "Someone"
                     }
                else:
                    # Return scheduled event info for countdown
                     active_auction_data = {
                         "status": "NOT_STARTED",
                         "event_id": event.event_id if event else None,
                         "start_time": event.start_date.isoformat() if event and event.start_date else None,
                         "server_time": datetime.utcnow().isoformat()
                     }
                     
            # Calculate additional stats based on real database state
            squad_size = len(squad_data)
            active_bids_count = 0
            live_auctions_count = 0
            upcoming_events_data = []

            if team:
                # 1. Active Bids Count
                active_bids_count = db.query(models.Bid).filter(
                    models.Bid.team_id == team.team_id,
                    models.Bid.status.in_(['pending', 'won'])  # Count pending bids or active auction bids
                ).count()
                
                # 2. Live Auctions Count (for this event)
                if team.event_id:
                    live_auctions_count = db.query(models.Auction).filter(
                        models.Auction.event_id == team.event_id,
                        models.Auction.status == 'in_progress'
                    ).count()
                
            # 3. Upcoming Events (Any scheduled event assigned to this team owner's teams)
            if team_owner.teams:
                event_ids = [t.event_id for t in team_owner.teams if t.event_id]
                if event_ids:
                    upcoming = db.query(models.Event).filter(
                        models.Event.event_id.in_(event_ids),
                        models.Event.status.in_(['scheduled', 'planned'])
                    ).all()
                    
                    for ev in upcoming:
                        upcoming_events_data.append({
                            "event_id": ev.event_id,
                            "title": ev.title,
                            "start_date": ev.start_date.isoformat() if ev.start_date else None,
                            "registration_deadline": ev.registration_deadline.isoformat() if ev.registration_deadline else None,
                            "status": ev.status
                        })
                
            return jsonify({
                "team_id": team.team_id if team else None,
                "username": current_user.username,
                "wallet_balance": float(team_owner.wallet_balance) if team_owner.wallet_balance else 0,
                "team_name": team_name,
                "squad": squad_data,
                "active_auction": active_auction_data,
                "participating_players": participating_players,
                "my_teams": my_teams,
                "squad_size": squad_size,
                "active_bids_count": active_bids_count,
                "live_auctions_count": live_auctions_count,
                "upcoming_events": upcoming_events_data
            })
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        abort(500, description=str(e))

# --- TEAM OWNER SUB-VIEWS ---

@app.route("/api/team-owner/squad")
def get_team_owner_squad():
    try:
        current_user = get_current_user()
        db = SessionLocal()
        try:
            current_user = db.merge(current_user)
            user_type_str = current_user.user_type.value if hasattr(current_user.user_type, 'value') else str(current_user.user_type)
            if user_type_str not in ['team_owner', 'team_manager', 'team_analyst']:
                abort(403, description="Unauthorized")
                
            if user_type_str in ['team_manager', 'team_analyst']:
                parent_user = db.query(models.User).filter(models.User.user_id == current_user.parent_user_id).first()
                team_owner = parent_user.team_owner if parent_user else None
            else:
                team_owner = current_user.team_owner
                
            if not team_owner: abort(404, description="Team Owner not found")
            
            team_id = request.args.get('team_id', type=int)
            if team_id:
                team = next((t for t in team_owner.teams if t.team_id == team_id), None)
            else:
                team = team_owner.teams[0] if team_owner.teams else None
                
            if not team: abort(404, description="Team not found")
            
            squad_data = []
            for team_player in team.players:
                player = team_player.player
                price = 0
                winning_bid = db.query(models.Bid).filter(
                    models.Bid.player_id == player.player_id,
                    models.Bid.team_id == team.team_id,
                    models.Bid.status == 'won'
                ).first()
                if winning_bid: price = float(winning_bid.amount)
                
                squad_data.append({
                    "id": player.player_id,
                    "name": player.full_name,
                    "category": "Standard",
                    "price": price,
                    "status": "OWNED",
                    "avatar": player.profile_image_url or ""
                })
                
            return jsonify({
                "squad": squad_data,
                "max_capacity": team.max_players,
                "current_size": len(squad_data),
                "remaining_slots": team.max_players - len(squad_data)
            })
        finally:
            db.close()
    except HTTPException: raise
    except Exception as e: abort(500, description=str(e))

@app.route("/api/team-owner/wallet")
def get_team_owner_wallet():
    try:
        current_user = get_current_user()
        db = SessionLocal()
        try:
            current_user = db.merge(current_user)
            user_type_str = current_user.user_type.value if hasattr(current_user.user_type, 'value') else str(current_user.user_type)
            if user_type_str not in ['team_owner', 'team_manager', 'team_analyst']:
                abort(403, description="Unauthorized")
                
            if user_type_str in ['team_manager', 'team_analyst']:
                parent_user = db.query(models.User).filter(models.User.user_id == current_user.parent_user_id).first()
                team_owner = parent_user.team_owner if parent_user else None
            else:
                team_owner = current_user.team_owner
                
            if not team_owner: abort(404, description="Team Owner not found")
            
            team_id = request.args.get('team_id', type=int)
            if team_id:
                team = next((t for t in team_owner.teams if t.team_id == team_id), None)
            else:
                team = team_owner.teams[0] if team_owner.teams else None
                
            if not team: abort(404, description="Team not found")
            
            total_budget = float(team.event.budget) if team.event and team.event.budget else 100000.0
            
            won_bids = db.query(models.Bid).filter(
                models.Bid.team_id == team.team_id,
                models.Bid.status == 'won'
            ).order_by(models.Bid.created_at.desc()).all()
            
            total_spent = sum([float(b.amount) for b in won_bids])
            
            transactions = []
            for b in won_bids:
                event_title = b.auction.event.title if b.auction and b.auction.event else "Unknown Event"
                transactions.append({
                    "date": b.created_at.isoformat(),
                    "description": "Player Purchase",
                    "player": b.player.full_name,
                    "event": event_title,
                    "amount": float(b.amount),
                    "type": "debit"
                })
                
            return jsonify({
                "total_budget": total_budget,
                "spent": total_spent,
                "available": total_budget - total_spent,
                "transactions": transactions
            })
        finally:
            db.close()
    except HTTPException: raise
    except Exception as e: abort(500, description=str(e))

@app.route("/api/team-owner/reports")
def get_team_owner_reports():
    try:
        current_user = get_current_user()
        db = SessionLocal()
        try:
            current_user = db.merge(current_user)
            user_type_str = current_user.user_type.value if hasattr(current_user.user_type, 'value') else str(current_user.user_type)
            if user_type_str not in ['team_owner', 'team_manager', 'team_analyst']:
                abort(403, description="Unauthorized")
                
            if user_type_str in ['team_manager', 'team_analyst']:
                parent_user = db.query(models.User).filter(models.User.user_id == current_user.parent_user_id).first()
                team_owner = parent_user.team_owner if parent_user else None
            else:
                team_owner = current_user.team_owner
                
            if not team_owner: abort(404, description="Team Owner not found")
            
            team_id = request.args.get('team_id', type=int)
            if team_id:
                team = next((t for t in team_owner.teams if t.team_id == team_id), None)
            else:
                team = team_owner.teams[0] if team_owner.teams else None
                
            if not team: abort(404, description="Team not found")
            
            won_bids = db.query(models.Bid).filter(
                models.Bid.team_id == team.team_id,
                models.Bid.status == 'won'
            ).all()
            
            amounts = [float(b.amount) for b in won_bids]
            total_spent = sum(amounts)
            players_purchased = len(won_bids)
            avg_price = total_spent / players_purchased if players_purchased > 0 else 0
            highest_purchase = max(amounts) if amounts else 0
            lowest_purchase = min(amounts) if amounts else 0
            
            auction_ids = set([b.auction_id for b in won_bids])
            
            auction_history = []
            for b in won_bids:
                event_title = b.auction.event.title if b.auction and b.auction.event else "Unknown"
                existing = next((x for x in auction_history if x["auction_id"] == b.auction_id), None)
                if existing:
                    existing["players_purchased"] += 1
                    existing["amount_spent"] += float(b.amount)
                else:
                    auction_history.append({
                        "auction_id": b.auction_id,
                        "event_name": event_title,
                        "date": b.auction.start_time.isoformat() if b.auction else b.created_at.isoformat(),
                        "players_purchased": 1,
                        "amount_spent": float(b.amount),
                        "status": b.auction.status if b.auction else "COMPLETED"
                    })
            
            total_budget = float(team.event.budget) if team.event and team.event.budget else 100000.0
            
            return jsonify({
                "auction_summary": {
                    "total_auctions": len(auction_ids),
                    "players_purchased": players_purchased,
                    "total_spent": total_spent,
                    "avg_purchase_price": avg_price,
                    "remaining_purse": total_budget - total_spent,
                    "highest_purchase": highest_purchase,
                    "lowest_purchase": lowest_purchase
                },
                "squad_summary": {
                    "total_players": players_purchased,
                    "capacity": team.max_players,
                    "remaining_slots": team.max_players - players_purchased
                },
                "spending_summary": {
                    "total": total_spent,
                    "avg_per_player": avg_price
                },
                "auction_history": auction_history
            })
        finally:
            db.close()
    except HTTPException: raise
    except Exception as e: abort(500, description=str(e))

# --- PRESENCE SYSTEM ---
@app.route("/api/presence/heartbeat", methods=['POST'])
def presence_heartbeat():
    current_user = get_current_user()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.user_id == current_user.user_id).first()
        if user:
            user.last_seen_at = datetime.utcnow()
            db.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()

@app.route("/api/presence/offline", methods=['POST'])
def presence_offline():
    current_user = get_current_user()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.user_id == current_user.user_id).first()
        if user:
            user.last_seen_at = None
            db.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()


# --- REAL-TIME AUCTION (Phase 1 & 2) ---

@app.route("/api/admin/events/<int:event_id>/auction-prep", methods=['GET'])
def auction_preparation(event_id: int):
    """
    Phase 1: Admin clicks 'Start Auction' and views the preparation screen.
    Returns the teams and players registered for the event.
    """
    current_user = get_current_user()
    if str(current_user.user_type) != "UserType.admin" and current_user.user_type.name != "admin":
        abort(403, description="Only admins can manage auctions.")

    db = SessionLocal()
    try:
        event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
        if not event:
            abort(404, description="Event not found.")

        # Get active teams with valid, active owners
        teams = db.query(models.Team).join(
            models.TeamOwner, models.Team.owner_id == models.TeamOwner.team_owner_id
        ).join(
            models.User, models.TeamOwner.user_id == models.User.user_id
        ).filter(
            models.Team.event_id == event_id,
            models.Team.status != 'suspended'
        ).all()
        
        now = datetime.utcnow()
        active_count = 0
        inactive_count = 0
        teams_data = []
        
        for t in teams:
            is_active = False
            if t.owner and t.owner.user and t.owner.user.last_seen_at:
                # User is active if last_seen_at is within the last 45 seconds
                if (now - t.owner.user.last_seen_at).total_seconds() < 45:
                    is_active = True
                    
            if is_active:
                active_count += 1
            else:
                inactive_count += 1
                
            teams_data.append({
                "team_id": t.team_id,
                "team_name": t.team_name,
                "owner": t.owner.owner_name if t.owner else 'N/A',
                "owner_id": t.owner.user_id if t.owner else None,
                "active": is_active,
                "status": "ACTIVE" if is_active else "INACTIVE",
                "max_players": t.max_players
            })
            
        all_teams_active = (inactive_count == 0 and len(teams) > 0)

        # Safely parse base prices
        base_price_val = 0
        if isinstance(event.base_prices, dict):
            base_price_val = event.base_prices.get('Standard', 0)
        elif isinstance(event.base_prices, str):
            import json
            try:
                bp_dict = json.loads(event.base_prices)
                base_price_val = bp_dict.get('Standard', 0)
            except:
                pass

        # Get players registered
        players = db.query(models.Player).join(models.player_events).filter(
            models.player_events.c.event_id == event_id
        ).all()
        players_data = [{
            "player_id": p.player_id,
            "name": f"{p.first_name} {p.last_name}",
            "role": p.cricket_rating, # Placeholder for role
            "base_price": base_price_val
        } for p in players]

        return jsonify({
            "status": "success",
            "event": {
                "event_id": event.event_id,
                "title": event.title,
                "status": event.status
            },
            "teams": teams_data,
            "teams_count": len(teams_data),
            "active_team_count": active_count,
            "inactive_team_count": inactive_count,
            "all_teams_active": all_teams_active,
            "players": players_data,
            "players_count": len(players_data)
        })
    finally:
        db.close()


@app.route("/api/admin/events/<int:event_id>/auction/initialize", methods=['POST'])
def initialize_auction(event_id: int):
    """
    Phase 2: Admin clicks 'Proceed with Auction' to create the auction records 
    and move to the Lobby.
    """
    current_user = get_current_user()
    role_name = current_user.user_type.name if hasattr(current_user.user_type, 'name') else str(current_user.user_type)
    if str(current_user.user_type) != "UserType.admin" and role_name != "admin":
        abort(403, description="Only admins can initialize auctions.")

    db = SessionLocal()
    try:
        event = db.query(models.Event).with_for_update().filter(models.Event.event_id == event_id).first()
        if not event:
            abort(404, description="Event not found.")

        # 1. Enforce strict presence check
        teams = db.query(models.Team).join(
            models.TeamOwner, models.Team.owner_id == models.TeamOwner.team_owner_id
        ).join(
            models.User, models.TeamOwner.user_id == models.User.user_id
        ).filter(
            models.Team.event_id == event_id,
            models.Team.status != 'suspended'
        ).all()

        now = datetime.utcnow()
        active_count = 0
        inactive_count = 0
        inactive_teams = []

        for t in teams:
            is_active = False
            if t.owner and t.owner.user and t.owner.user.last_seen_at:
                if (now - t.owner.user.last_seen_at).total_seconds() < 45:
                    is_active = True
            if is_active:
                active_count += 1
            else:
                inactive_count += 1
                inactive_teams.append({
                    "team_id": t.team_id,
                    "team_name": t.team_name
                })

        if inactive_count > 0 or len(teams) == 0:
            return jsonify({
                "success": False,
                "error": "AUCTION_NOT_READY",
                "message": "All registered team owners must be online before the auction can start.",
                "registered_team_count": len(teams),
                "active_team_count": active_count,
                "inactive_team_count": inactive_count,
                "inactive_teams": inactive_teams
            }), 409

        # Check if auction already exists
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        
        if not auction:
            # Create Auction
            auction = models.Auction(
                event_id=event_id,
                creator_id=current_user.user_id,
                title=f"{event.title} Auction",
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow() + timedelta(hours=5),
                status='in_progress'
            )
            db.add(auction)
            db.flush()

            # Create Auction Players
            players = db.query(models.Player).join(models.player_events).filter(
                models.player_events.c.event_id == event_id,
                models.Player.is_active == True
            ).all()
            
            base_price = event.base_prices.get('Standard', 1000000) if event.base_prices else 1000000

            for idx, p in enumerate(players):
                ap = models.AuctionPlayer(
                    auction_id=auction.auction_id,
                    player_id=p.player_id,
                    status='PENDING',
                    base_price=base_price,
                    auction_order=idx + 1
                )
                db.add(ap)

            # Create Auction Team Statuses for active, valid teams
            teams = db.query(models.Team).join(
                models.TeamOwner, models.Team.owner_id == models.TeamOwner.team_owner_id
            ).join(
                models.User, models.TeamOwner.user_id == models.User.user_id
            ).filter(
                models.Team.event_id == event_id,
                models.Team.status == 'active',
                models.User.is_active == True
            ).all()
            for t in teams:
                owner = db.query(models.TeamOwner).filter(models.TeamOwner.team_owner_id == t.owner_id).first()
                budget = owner.wallet_balance if (owner and owner.wallet_balance) else 0
                ats = models.AuctionTeamStatus(
                    auction_id=auction.auction_id,
                    team_id=t.team_id,
                    status='WAITING',
                    current_purse=budget,
                    squad_size=0
                )
                db.add(ats)

        else:
            if auction.status in ['draft', 'scheduled', 'lobby']:
                auction.status = 'in_progress'

        event.status = 'in_progress'
        event.is_live = True
        
        db.commit()
        return jsonify({
            "success": True,
            "status": "success",
            "message": "Auction initialized successfully",
            "auction_id": auction.auction_id,
            "event_id": event_id
        })
    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        app.logger.exception("Auction initialization failed")
        abort(500, description=f"Failed to initialize auction: {str(e)}")
    finally:
        db.close()


@app.route("/api/auction/<int:auction_id>/lobby", methods=['GET'])
def get_auction_lobby(auction_id: int):
    """
    Phase 3: Fetch lobby state. Used by both Admin and Teams to render the Auction Room UI.
    """
    current_user = get_current_user()
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if not auction:
            abort(404, description="Auction not found")

        event = db.query(models.Event).filter(models.Event.event_id == auction.event_id).first()

        # Fetch players
        auction_players = db.query(models.AuctionPlayer).filter(
            models.AuctionPlayer.auction_id == auction_id
        ).order_by(models.AuctionPlayer.auction_order).all()
        
        players_data = []
        for ap in auction_players:
            p = db.query(models.Player).filter(models.Player.player_id == ap.player_id).first()
            players_data.append({
                "auction_player_id": ap.id,
                "player_id": p.player_id,
                "name": f"{p.first_name} {p.last_name}",
                "role": p.cricket_rating,
                "status": ap.status,
                "base_price": float(ap.base_price) if ap.base_price else 0.0,
                "final_price": float(ap.final_price) if ap.final_price else 0.0,
                "sold_to_team_id": ap.sold_to_team_id
            })

        # Fetch teams
        team_statuses = db.query(models.AuctionTeamStatus).filter(
            models.AuctionTeamStatus.auction_id == auction_id
        ).all()
        
        teams_data = []
        for ts in team_statuses:
            t = db.query(models.Team).filter(models.Team.team_id == ts.team_id).first()
            teams_data.append({
                "team_id": t.team_id,
                "team_name": t.team_name,
                "current_purse": float(ts.current_purse) if ts.current_purse else 0.0,
                "squad_size": ts.squad_size,
                "status": ts.status
            })

        # Check role string to support both Enum and string comparison
        role_name = current_user.user_type.name if hasattr(current_user.user_type, 'name') else str(current_user.user_type)

        return jsonify({
            "status": "success",
            "auction": {
                "auction_id": auction.auction_id,
                "event_title": event.title,
                "status": auction.status,
                "current_player_id": auction.current_player_id,
                "current_bid_amount": float(auction.current_bid_amount) if auction.current_bid_amount else 0.0
            },
            "players": players_data,
            "teams": teams_data,
            "role": role_name
        })
    finally:
        db.close()

# Legacy Auction endpoints
@app.route("/auction/<int:event_id>/start", methods=['POST'])
def start_auction(event_id: int):
    """
    Start an auction for a specific event.
    
    - **event_id**: ID of the event to start
    - **returns**: Status message and auction details
    """
    current_user = get_current_user()
    db = SessionLocal()
    
    try:
        # Start a transaction
        db.begin()
        
        # Get the event with a row lock to prevent race conditions
        event = db.query(models.Event).with_for_update().filter(
            models.Event.event_id == event_id
        ).first()
        
        if not event:
            abort(404, description="Event not found")
            
        if event.status != 'SCHEDULED':
            abort(400, description="Auction can only be started for scheduled events")
            
        # Update event status and start time
        event.status = 'IN_PROGRESS'
        event.started_at = datetime.utcnow()
        
        # Create auction record
        auction = models.Auction(
            event_id=event_id,
            creator_id=current_user.user_id,
            status='IN_PROGRESS',
            started_at=datetime.utcnow(),
            title=f"{event.title} Auction"
        )
        db.add(auction)
        db.commit()
        
        return jsonify({
            "status": "success",
            "message": f"Auction for event {event_id} started successfully",
            "auction_id": auction.auction_id,
            "started_at": auction.started_at.isoformat()
        })
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error starting auction: {str(e)}")
        abort(500, description="Error starting auction")
    finally:
        db.close()

# Legacy end_auction removed. Use database-driven auction endpoints.

@app.route("/auction/<int:event_id>/bid/<int:player_id>", methods=['POST'])
def place_bid(event_id: int, player_id: int):
    """
    Place a bid on a player in an active auction.
    
    - **event_id**: ID of the event
    - **player_id**: ID of the player to bid on
    - **returns**: Bid status and details
    """
    current_user = get_current_user()
    db = SessionLocal()
    
    try:
        # Get bid data from request
        bid_data = request.get_json()
        amount = bid_data.get('amount')
        
        if not amount:
            abort(400, description="Bid amount is required")
    
        # Start a transaction
        db.begin()
        
        # Check if user is a team owner or authorized staff
        owner_user_id = current_user.user_id
        if str(current_user.user_type) == "UserType.team_manager" or current_user.user_type.name == "team_manager":
            if not current_user.parent_user_id:
                abort(403, description="Manager account is not associated with any Team Owner")
            owner_user_id = current_user.parent_user_id
            
        team_owner = db.query(models.TeamOwner).filter(
            models.TeamOwner.user_id == owner_user_id
        ).with_for_update().first()
        
        if not team_owner:
            abort(403, description="Only team owners and their managers can place bids")
            
        # Get the event with a row lock to prevent race conditions
        event = db.query(models.Event).with_for_update().filter(
            models.Event.event_id == event_id
        ).first()
        
        if not event:
            abort(404, description="Event not found")
            
        if event.status != 'IN_PROGRESS':
            abort(400, description="Bids can only be placed during active auctions")
            
        # Get the player with a row lock
        player = db.query(models.Player).with_for_update().filter(
            models.Player.player_id == player_id
        ).first()
        
        if not player:
            abort(404, description="Player not found")
            
        # Get the highest current bid for this player in this event
        highest_bid = db.query(models.Bid).filter(
            models.Bid.event_id == event_id,
            models.Bid.player_id == player_id
        ).order_by(models.Bid.amount.desc()).first()
        
        # Validate bid amount
        if highest_bid and amount <= highest_bid.amount:
            abort(400, description=f"Bid amount must be higher than current highest bid of {highest_bid.amount}")
            
        # Check team owner's budget
        if amount > team_owner.budget:
            abort(400, description="Bid amount exceeds available budget")
            
        # Create new bid
        bid = models.Bid(
            event_id=event_id,
            player_id=player_id,
            team_owner_id=team_owner.owner_id,
            amount=amount,
            status='PENDING',
            bid_time=datetime.utcnow(),
            created_by=current_user.user_id
        )
        
        # Add bid to session
        db.add(bid)
        
        # Commit the transaction
        db.commit()
        db.refresh(bid)
        
        return jsonify({
            "status": "success",
            "message": "Bid placed successfully",
            "bid_id": bid.bid_id,
            "amount": bid.amount
        })
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error placing bid: {str(e)}")
        abort(500, description="Error placing bid")
    finally:
        db.close()

# Message endpoints
@app.route("/api/messages", methods=['POST'])
def create_message():
    try:
        # Get message data from request
        message_data = request.get_json()
        
        # Get current user if logged in
        current_user = None
        try:
            current_user = get_current_user()
        except:
            pass  # User not logged in, that's okay for public messages
            
        # If user is logged in, attach their ID
        sender_id = current_user.user_id if current_user else None
        
        db = SessionLocal()
        try:
            db_message = models.Message(
                sender_id=sender_id,
                subject=message_data.get('subject'),
                content=message_data.get('content'),
                team_name=message_data.get('team_name'),
                sender_name=message_data.get('sender_name'),
                is_read=False
            )
            
            db.add(db_message)
            db.commit()
            db.refresh(db_message)
            
            return jsonify({
                "message_id": db_message.message_id,
                "sender_id": db_message.sender_id,
                "subject": db_message.subject,
                "content": db_message.content,
                "team_name": db_message.team_name,
                "sender_name": db_message.sender_name,
                "is_read": db_message.is_read,
                "created_at": db_message.created_at.isoformat() if db_message.created_at else None
            }), 201
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating message: {str(e)}")
        abort(500, description=f"Error sending message: {str(e)}")

@app.route("/api/messages", methods=['GET'])
def get_messages():
    skip = request.args.get('skip', 0, type=int)
    limit = request.args.get('limit', 100, type=int)
    
    current_user = get_current_user()
    db = SessionLocal()
    
    try:
        # Only admin can view all messages
        is_admin = current_user.user_type == models.UserType.admin or str(current_user.user_type) == "admin"
        if not is_admin:
            abort(403, description="Only admins can view messages")
            
        messages = db.query(models.Message).order_by(models.Message.created_at.desc()).offset(skip).limit(limit).all()
        
        return jsonify([{
            "message_id": msg.message_id,
            "sender_id": msg.sender_id,
            "subject": msg.subject,
            "content": msg.content,
            "team_name": msg.team_name,
            "sender_name": msg.sender_name,
            "is_read": msg.is_read,
            "created_at": msg.created_at.isoformat() if msg.created_at else None
        } for msg in messages])
    finally:
        db.close()

@app.route("/api/messages/<int:message_id>/read", methods=['PUT'])
def mark_message_read(message_id: int):
    current_user = get_current_user()
    db = SessionLocal()
    
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can manage messages")
        
    message = db.query(models.Message).filter(models.Message.message_id == message_id).first()
    if not message:
        abort(404, description="Message not found")
        
    try:
        message.is_read = True
        db.commit()
        db.refresh(message)
        
        return jsonify({
            "message_id": message.message_id,
            "sender_id": message.sender_id,
            "subject": message.subject,
            "content": message.content,
            "team_name": message.team_name,
            "sender_name": message.sender_name,
            "is_read": message.is_read,
            "created_at": message.created_at.isoformat() if message.created_at else None
        })
    finally:
        db.close()


# Activity log endpoints

# Legacy activity log helpers removed. Use database-driven log_activity at 1647.

# System monitoring endpoint
# Store initial network I/O counters for bandwidth calculation
_initial_net_io = None
_last_net_io_time = None

# Initialize CPU monitoring when available (psutil often restricted on shared cPanel)
try:
    psutil.cpu_percent(interval=0.1)
except Exception:
    pass

@app.route("/api/system-stats", methods=['GET'])
def get_system_stats():
    """System stats with graceful fallback when psutil is blocked on shared hosting."""
    global _initial_net_io, _last_net_io_time

    fallback = {
        "cpu_percent": 0,
        "ram_used_gb": 0,
        "ram_total_gb": 0,
        "ram_percent": 0,
        "bandwidth_sent_mb": 0,
        "bandwidth_recv_mb": 0,
        "bandwidth_sent_rate_mbps": 0,
        "bandwidth_recv_rate_mbps": 0,
        "available": False,
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        cpu_percent = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        ram_used_gb = ram.used / (1024 ** 3)
        ram_total_gb = ram.total / (1024 ** 3)
        ram_percent = ram.percent

        net_io = psutil.net_io_counters()
        current_time = time.time()

        if _initial_net_io is None:
            _initial_net_io = net_io
            _last_net_io_time = current_time

        time_delta = current_time - _last_net_io_time if _last_net_io_time else 1
        if time_delta == 0:
            time_delta = 0.001

        bytes_sent_delta = net_io.bytes_sent - _initial_net_io.bytes_sent
        bytes_recv_delta = net_io.bytes_recv - _initial_net_io.bytes_recv

        _initial_net_io = net_io
        _last_net_io_time = current_time

        bandwidth_sent_mb = net_io.bytes_sent / (1024 ** 2)
        bandwidth_recv_mb = net_io.bytes_recv / (1024 ** 2)
        bandwidth_sent_rate_mbps = (bytes_sent_delta / time_delta) * 8 / (1024 ** 2)
        bandwidth_recv_rate_mbps = (bytes_recv_delta / time_delta) * 8 / (1024 ** 2)

        return {
            "cpu_percent": round(cpu_percent, 1),
            "ram_used_gb": round(ram_used_gb, 2),
            "ram_total_gb": round(ram_total_gb, 2),
            "ram_percent": round(ram_percent, 1),
            "bandwidth_sent_mb": round(bandwidth_sent_mb, 2),
            "bandwidth_recv_mb": round(bandwidth_recv_mb, 2),
            "bandwidth_sent_rate_mbps": round(bandwidth_sent_rate_mbps, 2),
            "bandwidth_recv_rate_mbps": round(bandwidth_recv_rate_mbps, 2),
            "available": True,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"System stats unavailable (common on cPanel): {e}")
        return jsonify(fallback)

# Sample data initialization removed. Use API to manage data.

# Staff endpoints for Manager and Analyst
@app.route("/api/staff/check-invitation", methods=['POST'])
def staff_check_invitation():
    data = request.get_json()
    email = data.get('email')
    if not email:
        return jsonify({"has_invitation": False, "message": "Email is required"}), 400
    
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            return jsonify({"has_invitation": False, "message": "No account found with this email"}), 404
        
        # Determine team owner name (from parent_user_id)
        team_owner_name = "Unknown"
        if user.parent_user_id:
            parent = db.query(models.User).filter(models.User.user_id == user.parent_user_id).first()
            if parent:
                team_owner_name = parent.username

        # If they are pending
        if user.invitation_status == 'pending':
            return jsonify({
                "has_invitation": True,
                "status": "pending",
                "role": user.user_type.value if hasattr(user.user_type, 'value') else user.user_type,
                "team_owner_name": team_owner_name
            })
        
        # If they are already accepted/active
        return jsonify({
            "has_invitation": True,
            "status": "registered",
            "role": user.user_type.value if hasattr(user.user_type, 'value') else user.user_type,
            "team_owner_name": team_owner_name
        })
    finally:
        db.close()

@app.route("/api/staff/complete-registration", methods=['POST'])
def staff_complete_registration():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    # username might be provided, or we can default to email prefix
    username = data.get('username')
    
    if not email or not password:
        return jsonify({"success": False, "message": "Email and password are required"}), 400
        
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user or user.invitation_status != 'pending':
            return jsonify({"success": False, "message": "Invalid invitation"}), 400
            
        if username:
            # Check if username exists
            existing = db.query(models.User).filter(models.User.username == username, models.User.user_id != user.user_id).first()
            if existing:
                return jsonify({"success": False, "message": "Username already taken"}), 400
            user.username = username
        elif not user.username:
            user.username = email.split('@')[0]
            
        user.set_password(password)
        user.is_active = True
        user.invitation_status = 'accepted'
        db.commit()
        
        # Create session token
        session_token = create_session(str(user.user_id), db)
        
        # Return same payload as login
        return jsonify({
            "success": True,
            "message": "Registration completed successfully",
            "session_token": session_token,
            "redirect_to": "/templates/team-owner-dashboard.html",
            "user": {
                "id": user.user_id,
                "username": user.username,
                "email": user.email,
                "user_type": user.user_type.value if hasattr(user.user_type, 'value') else user.user_type,
                "role": user.user_type.value if hasattr(user.user_type, 'value') else user.user_type
            }
        })
    finally:
        db.close()

# Generic Login Endpoint with Role Selection
@app.route("/api/login", methods=['POST'])
def login():
    """
    Login endpoint with role selection for users/admins/staff.
    Accepts role parameter to route to appropriate dashboard.
    """
    login_data = request.get_json()
    db = SessionLocal()
    
    logger.info(f"Login attempt for username: {login_data.get('username')}, role: {login_data.get('role')}")
    
    try:
        # Find user by username or email
        user = db.query(models.User).filter(
            or_(
                models.User.username == login_data.get('username'),
                models.User.email == login_data.get('username')
            )
        ).first()
        
        if not user or not user.verify_password(login_data.get('password')):
            logger.warning(f"Failed login attempt for user: {login_data.get('username')}")
            abort(401, description="Invalid username/email or password")
        
        # Check if user is active - auto-activate inactive accounts
        if not user.is_active:
            logger.warning(f"Inactive user attempting login: {login_data.get('username')}")
            # Auto-activate the account
            user.is_active = True
            db.commit()
            logger.info(f"Auto-activated account: {login_data.get('username')}")
        
        # Validate role selection matches user type
        requested_role = login_data.get('role', 'user')
        user_type_str = user.user_type.value if hasattr(user.user_type, 'value') else str(user.user_type)
        
        logger.info(f"User type: {user_type_str}, Requested role: {requested_role}")
        
        # Role validation mapping
        role_mapping = {
            'admin': 'admin',
            'team_manager': 'team_owner',  # team_manager maps to team_owner in DB
            'team_analyst': 'team_owner',  # team_analyst maps to team_owner in DB
            'team_owner': 'team_owner',
            'player': 'player',
            'user': 'player'
        }
        
        # For staff roles (team_manager, team_analyst), check if user has the correct role
        if requested_role in ['team_manager', 'team_analyst']:
            if user_type_str != requested_role and user_type_str != 'team_owner':
                logger.warning(f"Access denied: {requested_role} role requires {requested_role} account, but user type is {user_type_str}")
                abort(403, description=f"Access denied. {requested_role} role requires {requested_role} account.")
        elif requested_role == 'team_owner':
            if user_type_str != 'team_owner':
                logger.warning(f"Access denied: Team Owner role required, but user type is {user_type_str}")
                abort(403, description="Access denied. Team Owner role required.")
        elif requested_role == 'admin':
            # More flexible admin check - handle different possible admin type values
            if user_type_str.lower() != 'admin':
                logger.warning(f"Access denied: Admin role required, but user type is {user_type_str}")
                abort(403, description="Access denied. Admin role required.")
        elif requested_role in ['player', 'user']:
            if user_type_str != 'player':
                logger.warning(f"Access denied: Player role required, but user type is {user_type_str}")
                abort(403, description="Access denied. Player role required.")
        
        # Create session
        session_token = create_session(str(user.user_id), db)
        
        # Log activity (non-critical, don't fail login if this fails)
        try:
            log_activity(
                db=db,
                user_id=user.user_id,
                action_type="USER_LOGIN",
                action_description=f"User logged in as {requested_role}",
                entity_type="user",
                entity_id=user.user_id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get("user-agent")
            )
        except Exception as log_err:
            logger.error(f"Failed to log login activity: {log_err}")
            # Don't fail the login if logging fails
            
        # Set cookie and return response with role information
        response_data = {
            "success": True,
            "message": "Login successful",
            "user": {
                "id": user.user_id,
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "user_type": user_type_str,
                "role": requested_role,  # Return the requested role for routing
                "is_active": user.is_active
            },
            "redirect_to": get_redirect_path(requested_role),
            "session_token": session_token
        }
        
        is_production = app.config['SESSION_COOKIE_SECURE']
        
        response = make_response(jsonify(response_data))
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_token,
            httponly=True,
            secure=is_production,
            max_age=settings.session_expire_minutes * 60,
            samesite="Lax"
        )
        return response

    except HTTPException:

        raise

    except Exception as e:
        import traceback
        logger.error(f"Login error: {e}")
        logger.error(f"Login error traceback: {traceback.format_exc()}")
        abort(500, description=f"An error occurred during login: {str(e)}")
    finally:
        db.close()

def get_redirect_path(role: str) -> str:
    """Get the redirect path based on user role."""
    redirect_map = {
        'admin': '/templates/admin-dashboard.html',
        'team_manager': '/dashboard/manager',
        'team_analyst': '/dashboard/analyst',
        'team_owner': '/dashboard',
        'player': '/templates/player-dashboard.html',
        'user': '/templates/player-dashboard.html'
    }
    return redirect_map.get(role, '/templates/player-dashboard.html')

# Team Owner specific login endpoint
@app.route("/api/team-owner/login", methods=['POST'])
def team_owner_login():
    """
    Team owner specific login endpoint.
    Only allows team owners to log in.
    """
    login_data = request.get_json()
    db = SessionLocal()
    
    username = login_data.get('username')
    password = login_data.get('password')
    
    # Bcrypt has a 72-byte limit, truncate if necessary
    if isinstance(password, str):
        password = password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    
    try:
        client_ip = request.remote_addr
        if not username or not password:
            abort(400, description="Email/username and password are required")
        
        # Find user by email or username
        user = db.query(models.User).filter(
            (models.User.email == username) | (models.User.username == username)
        ).first()
        
        if not user or not user.verify_password(password):
            print(f"Failed team owner login attempt for user: {username} from IP: {client_ip}")
            abort(401, description="Incorrect email/username or password")
        
        # Check if user is a team owner
        if user.user_type != models.UserType.team_owner:
            abort(403, description="Access denied. Only team owners can use this login endpoint.")
        
        # Check if user is active - but allow inactive team owners to login with a warning
        if not user.is_active:
            logger.warning(f"Inactive team owner attempting login: {username}")
            # Auto-activate the account for team owners
            user.is_active = True
            db.commit()
            logger.info(f"Auto-activated team owner account: {username}")
        
        session_token = create_session(str(user.user_id), db)
        
        # Get team owner details
        team_owner = db.query(models.TeamOwner).filter(
            models.TeamOwner.user_id == user.user_id
        ).first()
        
        # Get team details
        team = None
        if team_owner:
            team = db.query(models.Team).filter(
                models.Team.owner_id == team_owner.team_owner_id
            ).first()
        
        try:
            log_activity(
                db=db,
                user_id=user.user_id,
                action_type="TEAM_OWNER_LOGIN",
                action_description=f"Team owner logged in: {user.email}",
                entity_type="user",
                entity_id=user.user_id,
                ip_address=client_ip,
                user_agent=request.headers.get("user-agent"),
            )
        except Exception as log_err:
            print(f"Failed to log team owner login activity: {log_err}")

        response_data = {
            "status": "success", 
            "message": "Team owner login successful",
            "user": {
                "id": user.user_id,
                "email": user.email,
                "username": user.username,
                "user_type": user.user_type.value if hasattr(user.user_type, 'value') else str(user.user_type)
            },
            "team_owner": {
                "team_owner_id": team_owner.team_owner_id if team_owner else None,
                "owner_name": team_owner.owner_name if team_owner else None,
                "wallet_balance": float(team_owner.wallet_balance) if team_owner and team_owner.wallet_balance else 0.0
            },
            "team": {
                "team_id": team.team_id if team else None,
                "team_name": team.team_name if team else None,
                "status": team.status if team else None,
                "max_players": team.max_players if team else 0,
                "current_players": team.current_players if team else 0
            }
        }
        
        response = make_response(jsonify(response_data))
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_token,
            httponly=True,
            secure=app.config['SESSION_COOKIE_SECURE'],
            max_age=settings.session_expire_minutes * 60,
            samesite="Lax"
        )
        return response
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_msg = error_msg.replace('[SUCCESS]', '[SUCCESS]').replace('[ERROR]', '[ERROR]')
        
        # Log full traceback to file
        with open('team_owner_login_error.log', 'a') as f:
            f.write(f"\n\n=== Team Owner Login Error at {datetime.utcnow()} ===\n")
            f.write(f"Error: {error_msg}\n")
            f.write(f"Type: {type(e).__name__}\n")
            f.write(traceback.format_exc())
        
        print(f"Team owner login error: {error_msg}")
        print(f"Team owner login error type: {type(e).__name__}")
        
        abort(500, description=error_msg)
    finally:
        db.close()

@app.route("/api/users", methods=['GET'])
def read_users():
    """
    Get all users with pagination. Only accessible by admins.
    Returns: {users: List[User], total: int}
    """
    current_user = get_current_user()
    db = SessionLocal()
    
    skip = request.args.get('skip', 0, type=int)
    limit = request.args.get('limit', 100, type=int)
    user_type = request.args.get('user_type')
    event_id = request.args.get('event_id', type=int)
    
    if current_user.user_type != models.UserType.admin and str(current_user.user_type) != "admin":
        return jsonify({"success": False, "message": "Not authorized to view users"}), 403
    
    try:
        # Build query
        query = db.query(models.User)
    
        # Eager load relationships
        from sqlalchemy.orm import joinedload, selectinload
        query = query.options(
            joinedload(models.User.player).selectinload(models.Player.events),
            joinedload(models.User.player).selectinload(models.Player.skill_ratings).joinedload(models.PlayerSkillRating.skill).joinedload(models.PlayerSkill.sport),
            joinedload(models.User.team_owner).selectinload(models.TeamOwner.teams)
        )
    
        # Filter by user_type if provided
        if user_type:
            # Convert string to UserType enum for comparison
            try:
                user_type_enum = models.UserType(user_type)
                query = query.filter(models.User.user_type == user_type_enum)
            except ValueError:
                # Invalid user_type provided, return empty result
                return jsonify({"users": [], "total": 0})

        # Filter by event_id if provided
        if event_id:
            if user_type == "player":
                query = query.join(models.Player).join(models.Player.events).filter(models.Event.event_id == event_id)
            elif user_type == "team_owner":
                query = query.join(models.TeamOwner).join(models.Team).filter(models.Team.event_id == event_id)
        
        # Get total count
        total = query.count()
        
        # Get paginated users
        users = query.offset(skip).limit(limit).all()
        
        # Convert to dict for JSON serialization
        users_data = []
        for user in users:
            user_dict = {
                "user_id": user.user_id,
                "username": user.username,
                "email": user.email,
                "phone": user.phone,
                "user_type": user.user_type.value if hasattr(user.user_type, 'value') else user.user_type,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "event_id": None  # Default to None
            }
            
            # Get event_id and profile info for players
            if user.user_type == models.UserType.player and user.player:
                # Get the first event the player is registered for
                if user.player.events:
                    user_dict["event_id"] = user.player.events[0].event_id
                
                # Add player profile details
                user_dict.update({
                    "first_name": user.player.first_name,
                    "last_name": user.player.last_name,
                    "date_of_birth": user.player.date_of_birth.isoformat() if user.player.date_of_birth else None,
                    "gender": user.player.gender,
                    "profile_image_url": user.player.profile_image_url,
                    "bio": user.player.bio,
                    "address": user.player.address,
                    "city": user.player.city,
                    "state": user.player.state,
                    "country": user.player.country,
                    "pincode": user.player.pincode,
                    "height_cm": user.player.height_cm,
                    "weight_kg": user.player.weight_kg,
                })
                
                # Helper to get rating from skill_ratings relationship
                def get_rating(sport_name):
                    # Look through skill_ratings explicitly
                    for rating in user.player.skill_ratings:
                        # Access skill details if relationship is loaded, otherwise this might fail if not eager loaded
                        # But we added joinedload earlier. Need to ensure skill is loaded too.
                        # Actually, the implementation plan said "backward compatibility".
                        # Let's try to get it from the relationship if possible, else fall back to property/column.
                        if rating.skill.sport.name.lower() == sport_name.lower():
                            return rating.rating
                    
                    # Fallback to column if exists
                    return getattr(user.player, f"{sport_name.lower()}_rating", None)

                user_dict.update({
                    "basketball_rating": get_rating("Basketball"),
                    "football_rating": get_rating("Football"),
                    "cricket_rating": get_rating("Cricket")
                })
            
            # Get team_name, owner_name, and event_id for team owners
            if user.user_type == models.UserType.team_owner and user.team_owner:
                user_dict["owner_name"] = user.team_owner.owner_name
                # Get team information
                if user.team_owner.teams:
                    team = user.team_owner.teams[0]  # Get first team
                    user_dict["team_name"] = team.team_name
                    user_dict["event_id"] = team.event_id
                else:
                    user_dict["team_name"] = None
            
            users_data.append(user_dict)
        
        return jsonify({"users": users_data, "total": total})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching users: {e}")
        abort(500, description="Internal server error")
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/sports", methods=['GET'])
def get_event_sports(event_id: int):
    """Get all sports for a specific event"""
    db = SessionLocal()
    try:
        event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
        if not event:
            abort(404, description="Event not found")
        
        # Get sports associated with this event
        sports_list = []
        for sport in event.sports:
            sports_list.append({
                "sport_id": sport.sport_id,
                "name": sport.name,
                "description": sport.description,
                "icon_class": sport.icon_class
            })
        
        return jsonify(sports_list)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching sports for event {event_id}: {e}")
        abort(500, description="Internal server error")
    finally:
        db.close()


# Activity logging helper function
def log_activity(
    db: Session,
    user_id: int,
    action_type: str,
    action_description: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
):
    """Helper function to log admin activities"""
    try:
        # Remove any emojis from the description
        import re
        emoji_pattern = re.compile("["
            u"\U0001F600-\U0001F64F"  # emoticons
            u"\U0001F300-\U0001F5FF"  # symbols & pictographs
            u"\U0001F680-\U0001F6FF"  # transport & map symbols
            u"\U0001F1E0-\U0001F1FF"  # flags (iOS)
            u"\U00002702-\U000027B0"  # dingbats
            u"\U000024C2-\U0001F251" 
            "]+", flags=re.UNICODE)
        
        clean_description = emoji_pattern.sub(r'', action_description)
        
        # Create new activity log with cleaned description
        activity_log = models.ActivityLog(
            user_id=user_id,
            action_type=action_type,
            action_description=clean_description,
            entity_type=entity_type,
            entity_id=entity_id,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.add(activity_log)
        db.commit() # Commit activity log immediately
        return activity_log
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        error_msg = str(e)
        print(f"Error logging activity: {error_msg}")
        return None

@app.route("/api/activity-logs", methods=['GET'])
def get_activity_logs():
    """
    Get activity logs with pagination, sorting, and filtering. Only accessible by admins.
    Returns: {logs: List[ActivityLog], total: int}
    """
    current_user = get_current_user()
    db = SessionLocal()
    
    skip = request.args.get('skip', 0, type=int)
    limit = request.args.get('limit', 50, type=int)
    sort_by = request.args.get('sort_by', 'newest')
    filter_by = request.args.get('filter_by', 'all')
    
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Not authorized to view activity logs")
    
    try:
        # Base query
        query = db.query(models.ActivityLog)
    
        # Apply filtering
        if filter_by != "all":
            if filter_by == "admin":
                # Join with User table to filter by user_type
                query = query.join(models.User, models.ActivityLog.user_id == models.User.user_id).filter(
                    models.User.user_type == models.UserType.admin
                )
            elif filter_by == "team_owner":
                query = query.join(models.User, models.ActivityLog.user_id == models.User.user_id).filter(
                    models.User.user_type == models.UserType.team_owner
                )
            elif filter_by == "player":
                # For players, we might need to check entity_type or user_type if players are users
                # Assuming players are users with user_type 'player'
                query = query.join(models.User, models.ActivityLog.user_id == models.User.user_id).filter(
                    models.User.user_type == models.UserType.player
                )
        
        # Get total count after filtering
        total = query.count()
        
        # Apply sorting
        if sort_by == "oldest":
            query = query.order_by(models.ActivityLog.created_at.asc())
        else:  # Default to newest
            query = query.order_by(models.ActivityLog.created_at.desc())
        
        # Apply pagination
        logs = query.offset(skip).limit(limit).all()
        
        # Convert to dict for JSON serialization
        logs_data = []
        for log in logs:
            # Fetch user details if user_id exists
            user_info = None
            if log.user_id:
                user = db.query(models.User).filter(models.User.user_id == log.user_id).first()
                if user:
                    user_info = {
                        "username": user.username,
                        "email": user.email,
                        "user_type": user.user_type.value if hasattr(user.user_type, 'value') else str(user.user_type)
                    }
            
            logs_data.append({
                "log_id": log.log_id,
                "user_id": log.user_id,
                "user_info": user_info,
                "action_type": log.action_type,
                "action_description": log.action_description,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "created_at": log.created_at.isoformat() if log.created_at else None
            })
        
        return jsonify({"logs": logs_data, "total": total})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching activity logs: {e}")
        abort(500, description="Internal server error")
    finally:
        db.close()

# Create a new activity log entry (unauthenticated - for frontend logging)
@app.route("/api/activity-logs/public", methods=['POST'])
def create_public_activity_log_endpoint():
    """Create a new activity log entry without authentication requirement."""
    log_data = request.get_json()
    db = SessionLocal()
    
    try:
        # Clean any potential emojis from the action description
        action_description = log_data.get('action_description', '')
        if action_description:
            # Replace checkmark emoji with text
            action_description = action_description.replace('[SUCCESS]', '[SUCCESS]')
            # Remove any other non-ASCII characters that might cause encoding issues
            action_description = action_description.encode('ascii', errors='ignore').decode('ascii')
        
        activity_log = models.ActivityLog(
            user_id=None,  # No user for public logs
            action_type=log_data.get('action_type'),
            action_description=action_description,
            entity_type=log_data.get('entity_type'),
            entity_id=log_data.get('entity_id'),
            ip_address=log_data.get('ip_address'),
            user_agent=log_data.get('user_agent')
        )
        db.add(activity_log)
        db.commit()
        db.refresh(activity_log)
        
        return jsonify({"log_id": activity_log.log_id, "status": "created"})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        # Log error but don't expose sensitive info
        print(f"Error creating activity log: {str(e)}")
        abort(500, description="Failed to create activity log")
    finally:
        db.close()

# Create a new activity log entry
@app.route("/api/activity-logs", methods=['POST'])
def create_activity_log_endpoint():
    """Create a new activity log entry for the authenticated user."""
    current_user = get_current_user()
    log_data = request.get_json()
    db = SessionLocal()
    
    try:
        # Clean any potential emojis from the action description
        action_description = log_data.get('action_description', '')
        if action_description:
            # Replace checkmark emoji with text
            action_description = action_description.replace('[SUCCESS]', '[SUCCESS]')
            # Remove any other non-ASCII characters that might cause encoding issues
            action_description = action_description.encode('ascii', errors='ignore').decode('ascii')
        
        activity_log = models.ActivityLog(
            user_id=current_user.user_id,
            action_type=log_data.get('action_type'),
            action_description=action_description,
            entity_type=log_data.get('entity_type'),
            entity_id=log_data.get('entity_id'),
            ip_address=log_data.get('ip_address'),
            user_agent=log_data.get('user_agent')
        )
        db.add(activity_log)
        db.commit()
        db.refresh(activity_log)
        
        return jsonify({"log_id": activity_log.log_id, "status": "created"})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        # Log error but don't expose sensitive info
        print(f"Error creating activity log: {str(e)}")
        abort(500, description="Failed to create activity log")
    finally:
        db.close()

@app.route("/api/me", methods=['GET'])
def get_current_user_info():
    current_user = get_current_user()
    return jsonify({
        "user_id": current_user.user_id,
        "username": current_user.username,
        "email": current_user.email,
        "user_type": current_user.user_type.value if hasattr(current_user.user_type, "value") else current_user.user_type,
    })

# Logout endpoint
@app.route("/api/logout", methods=['POST'])
def logout():
    """Log out the current user by deleting the session cookie."""
    response = make_response(jsonify({"status": "success", "message": "Successfully logged out"}))
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


# Root endpoint handled by serve_frontend below

# Player registration endpoint
@app.route("/register/player", methods=['POST'])
def register_player_endpoint():
    raw_data = request.get_json()
    db = SessionLocal()
    try:
        # Validate raw dict into Pydantic model
        try:
            player_data = schemas.PlayerRegistration(**raw_data)
        except Exception as validation_err:
            abort(400, description=str(validation_err))
        result = register_player(player_data, db)
        return jsonify(result), 201
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        abort(500, description=str(e))
    finally:
        db.close()

def register_player(
    player_data: schemas.PlayerRegistration,
    db: Session
):
    logger.info(f"Starting registration for email: {player_data.email}")
    
    email_normalized = player_data.email.lower()
    event_id = player_data.event_id
    
    # 1. Validation and existence checks (Read-only)
    try:
        # Check if email already exists in User table
        existing_user_email = db.query(models.User).filter(models.User.email == email_normalized).first()
        if existing_user_email:
            abort(400, description="Email already registered in user account")

        # Check if email already exists in Player table
        existing_player_email = db.query(models.Player).filter(models.Player.email == email_normalized).first()
        if existing_player_email:
            abort(400, description="Email already registered in player profile")

        # Check if phone already exists in User table
        if player_data.phone:
            existing_user_phone = db.query(models.User).filter(models.User.phone == player_data.phone).first()
            if existing_user_phone:
                abort(400, description="Phone number already registered in user account")
            
            # Also check Player table for phone
            existing_player_phone = db.query(models.Player).filter(models.Player.phone == player_data.phone).first()
            if existing_player_phone:
                abort(400, description="Phone number already registered in player profile")

        # Check event existence
        if not event_id:
            abort(400, description="Event ID required")
            
        # We query the event once to check existence and max_participants
        event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
        if not event:
            abort(400, description="Event not found")
            
        # Check both max_participants and max_players
        limit = event.max_players if event.max_players is not None else event.max_participants
        if limit and event.current_participants >= limit:
             abort(400, description="Event registration is full")
        
        # Check if username exists (base username)
        base_username = email_normalized.split('@')[0]
        final_username = base_username
        if db.query(models.User).filter(models.User.username == base_username).first():
            import random, string
            suffix = ''.join(random.choices(string.digits, k=4))
            final_username = f"{base_username}{suffix}"
            
        # Rollback to clear any shared locks taken during the queries before we do slow bcrypt
        db.rollback()




    except HTTPException:




        raise




    except Exception as e:
        logger.error(f"Error during registration validation: {str(e)}")
        abort(500, description="Registration validation failed")

    # 2. Preparation (No DB activities here to keep locks minimal later)
    try:
        # Hash password (CPU heavy)
        password_bytes = player_data.password.encode('utf-8')
        hashed_password = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')
        
        # Parse date of birth
        dob_value = player_data.date_of_birth
        if isinstance(dob_value, str):
            date_of_birth = datetime.strptime(dob_value, "%Y-%m-%d").date()
        else:
            date_of_birth = dob_value
            
    except ValueError:
        abort(400, description="Invalid date format. Use YYYY-MM-DD")

    except HTTPException:

        raise

    except Exception as e:
        logger.error(f"Error during registration prep: {str(e)}")
        abort(500, description="Internal processing error")

    # 3. Main write transaction (Keep it short!)
    try:
        # Create user
        user = models.User(
            username=final_username,
            email=email_normalized,
            password_hash=hashed_password,
            phone=player_data.phone,
            user_type=models.UserType.player, # Using Enum instead of string
            is_active=True,
            is_verified=False
        )
        logger.info(f"Creating user record for {email_normalized}")
        db.add(user)
        db.flush()
        logger.info(f"User created with ID: {user.user_id}")
        
        # Create player profile
        player_profile = models.Player(
            user_id=user.user_id,
            email=player_data.email,
            password_hash=hashed_password,
            phone=player_data.phone,
            first_name=player_data.first_name,
            last_name=player_data.last_name,
            date_of_birth=date_of_birth,
            gender=player_data.gender,
            address=player_data.address,
            city=player_data.city,
            state=player_data.state,
            country=player_data.country,
            pincode=player_data.pincode,
            bio=player_data.bio,
            height_cm=player_data.height_cm,
            weight_kg=player_data.weight_kg,
            sport_profiles=player_data.sport_profiles,
            is_active=True,
            is_verified=False
        )
        logger.info("Creating player profile")
        db.add(player_profile)
        db.flush()
        logger.info(f"Player profile created with ID: {player_profile.player_id}")
        
        # Re-fetch the event with a lock to enforce capacity securely
        event = db.query(models.Event).with_for_update().filter(models.Event.event_id == event_id).first()
        if not event:
            db.rollback()
            abort(400, description="Event no longer exists")
            
        # Enforce capacity dynamically from relationships
        limit = event.max_players if event.max_players is not None else event.max_participants
        if limit:
            active_players_count = db.query(models.Player).join(
                models.player_events, 
                models.Player.player_id == models.player_events.c.player_id
            ).filter(
                models.player_events.c.event_id == event_id,
                models.Player.is_active == True
            ).count()
            
            if active_players_count >= limit:
                db.rollback()
                abort(400, description="Event registration is full")
            
        # Link to event
        player_profile.events.append(event)
        logger.info(f"Linked player to event ID: {event_id}")

        # Save sport ratings
        if player_data.sport_ratings:
            for sport_rating in player_data.sport_ratings:
                sport_id = sport_rating.get('sport_id')
                rating = sport_rating.get('rating', 0)
                if rating > 0:
                    skill = db.query(models.PlayerSkill).filter(
                        models.PlayerSkill.sport_id == sport_id,
                        models.PlayerSkill.skill_name == "Overall"
                    ).first()
                    
                    if not skill:
                        skill = models.PlayerSkill(
                            sport_id=sport_id,
                            skill_name="Overall",
                            description="Overall rating for registration",
                            min_rating=1,
                            max_rating=10
                        )
                        db.add(skill)
                        db.flush()
                    
                    skill_rating = models.PlayerSkillRating(
                        player_id=player_profile.player_id,
                        skill_id=skill.skill_id,
                        rating=rating,
                        rated_by=user.user_id,
                        notes="Self-assessment during registration"
                    )
                    db.add(skill_rating)
        
        db.commit()
        
        # 4. Post-commit tasks (Log activity)
        try:
            log_activity(
                db=db,
                user_id=user.user_id,
                action_type="PLAYER_REGISTERED",
                action_description=f"Player registered: {player_data.email}"
            )
        except Exception as log_err:
            logger.error(f"Non-critical error logging activity: {log_err}")

        return {
            "success": True,
            "message": "Registration successful",
            "user_id": user.user_id,
            "id": user.user_id,
            "player_id": player_profile.player_id
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"SQLAlchemy error during registration: {str(e)}", exc_info=True)
        # Check for Lock Wait Timeout specifically
        if "1205" in str(e):
             abort(408, description="Database is busy, please try again in a few seconds")
        abort(500, description="Database error during registration. Please try again later.")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error in register_player transaction: {str(e)}", exc_info=True)
        abort(500, description=f"Registration failed: {str(e)}")

# User registration endpoint (kept for backward compatibility)
@app.route("/api/register", methods=['POST'])
def register_user():
    """Legacy registration endpoint that forwards to the player registration endpoint."""
    raw_data = request.get_json()
    db = SessionLocal()
    
    try:
        # Validate raw dict into Pydantic model
        try:
            user_data = schemas.PlayerRegistration(**raw_data)
        except Exception as validation_err:
            abort(400, description=str(validation_err))
        # Call the player registration endpoint (now sync)
        result = register_player(user_data, db)
        
        # Create session for the new user
        session_token = create_session(str(result["user_id"]), db)
        
        # Get the user from the database
        user = db.query(models.User).filter(
            models.User.user_id == result["user_id"]
        ).first()
        
        if not user:
            abort(500, description="User registration succeeded but user not found")
            
        return jsonify({
            "success": True,
            "message": "User registered successfully",
            "user": {
                "id": user.user_id,
                "email": user.email,
                "username": user.username,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "created_at": user.created_at.isoformat() if user.created_at else None
            },
            "session_token": session_token
        })
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error in register_user: {str(e)}", exc_info=True)
        abort(500, description="An unexpected error occurred during registration")
    finally:
        db.close()



# Admin Approval Endpoint
@app.route("/api/admin/users/<int:user_id>/approve", methods=['POST'])
def approve_user(user_id: int):
    """
    Approve a user registration (specifically Team Owner), set their password, and activate them.
    Only accessible by admins.
    """
    approval_data = request.get_json()
    current_user = get_current_user()
    db = SessionLocal()
    
    try:
        # Check admin privileges
        if current_user.user_type != "admin": # Check string value since Enum comparison might be tricky depending on how it's stored
            # Double check if it's an enum object
            if hasattr(current_user.user_type, 'value'):
                 if current_user.user_type.value != "admin":
                     return jsonify({"success": False, "message": "Only admins can approve users"}), 403
            else:
                 return jsonify({"success": False, "message": "Only admins can approve users"}), 403
        
        # Get user to approve
        user_to_approve = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user_to_approve:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        # Update user
        if approval_data and approval_data.get('password'):
            user_to_approve.password_hash = get_password_hash(approval_data.get('password'))
        user_to_approve.is_active = True
        user_to_approve.is_verified = True
        
        # Also activate their associated team(s) if they are a team owner
        team_owner = db.query(models.TeamOwner).filter(models.TeamOwner.user_id == user_id).first()
        if team_owner:
            for team in team_owner.teams:
                if team.status == 'inactive':
                    team.status = 'active'
        
        # Log activity
        try:
            log_activity(
                db=db, 
                user_id=current_user.user_id, 
                action_type="USER_APPROVED", 
                action_description=f"Approved user {user_to_approve.username} (ID: {user_id})", 
                entity_type="user", 
                entity_id=user_id
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to log approval activity: {e}")
        
        db.commit()
        db.refresh(user_to_approve)
        
        return jsonify({
            "user_id": user_to_approve.user_id,
            "username": user_to_approve.username,
            "email": user_to_approve.email,
            "user_type": user_to_approve.user_type.value if hasattr(user_to_approve.user_type, 'value') else user_to_approve.user_type,
            "is_active": user_to_approve.is_active,
            "is_verified": user_to_approve.is_verified
        })
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error approving user: {e}")
        return jsonify({"success": False, "message": "Error approving user"}), 500
    finally:
        db.close()

@app.route("/api/admin/users/<int:user_id>/delete", methods=['DELETE'])
def delete_user(user_id: int):
    """
    Delete a user (typically team owner) and cascade delete related data.
    Only accessible by admins.
    """
    current_user = get_current_user()
    db = SessionLocal()
    
    try:
        # Check admin privileges
        role_str = current_user.user_type.value if hasattr(current_user.user_type, 'value') else str(current_user.user_type)
        if role_str not in ["admin", "superadmin"]:
            return jsonify({"success": False, "message": "Only admins can delete users"}), 403
        
        # Get user to delete
        user_to_delete = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user_to_delete:
            return jsonify({"success": False, "message": "User not found"}), 404
            
        user_role = user_to_delete.user_type.value if hasattr(user_to_delete.user_type, 'value') else str(user_to_delete.user_type)
        
        # Identify staff members (for team_owner)
        staff_members = db.query(models.User).filter(models.User.parent_user_id == user_id).all()
        deleted_staff_count = len(staff_members)
        
        # Check for historical dependencies (bids) if team_owner
        has_bids = False
        teams = []
        if user_role == 'team_owner':
            team_owner = db.query(models.TeamOwner).filter(models.TeamOwner.user_id == user_id).first()
            if team_owner:
                teams = db.query(models.Team).filter(models.Team.owner_id == team_owner.team_owner_id).all()
                for team in teams:
                    if db.query(models.Bid).filter(models.Bid.team_id == team.team_id).first() is not None:
                        has_bids = True
                        break
        
        if has_bids:
            # SOFT DELETE: Preserve historical bids, deactivate user and staff, suspend teams
            user_to_delete.is_active = False
            for staff in staff_members:
                staff.is_active = False
            for team in teams:
                team.status = 'suspended'
                
            db.commit()
            
            # Log activity outside the main transaction to avoid expiring objects before commit
            try:
                log_db = SessionLocal()
                log_activity(
                    db=log_db, 
                    user_id=current_user.user_id, 
                    action_type="USER_SUSPENDED", 
                    action_description=f"Suspended team owner {user_to_delete.username} (ID: {user_id}) to preserve historical bids", 
                    entity_type="user", 
                    entity_id=user_id
                )
                log_db.close()
            except Exception as e:
                logger.error(f"Failed to log suspension activity: {e}")
                
            return jsonify({
                "success": True,
                "message": "User has historical records (bids). User and their teams were marked as inactive instead of hard-deleted.",
                "deleted_staff_count": deleted_staff_count
            })
            
        else:
            # HARD DELETE: Safely remove dependent records that lack SQLAlchemy cascades or DB cascades
            all_user_ids = [user_id] + [s.user_id for s in staff_members]
            
            for uid in all_user_ids:
                db.query(models.Transaction).filter(
                    (models.Transaction.from_user_id == uid) | 
                    (models.Transaction.to_user_id == uid)
                ).delete(synchronize_session=False)
                db.query(models.Message).filter(models.Message.sender_id == uid).delete(synchronize_session=False)
                db.query(models.PlayerSkillRating).filter(models.PlayerSkillRating.rated_by == uid).delete(synchronize_session=False)
                db.query(models.Session).filter(models.Session.user_id == uid).delete(synchronize_session=False)

            # Delete staff members first
            for staff in staff_members:
                db.delete(staff)
                
            # Delete the main user (SQLAlchemy cascade will handle TeamOwner, Team, TeamPlayer)
            db.delete(user_to_delete)
            
            db.commit()
            
            # Log activity outside the main transaction
            try:
                log_db = SessionLocal()
                log_activity(
                    db=log_db, 
                    user_id=current_user.user_id, 
                    action_type="USER_DELETED", 
                    action_description=f"Hard deleted user {user_to_delete.username} (ID: {user_id}) and related entities", 
                    entity_type="user", 
                    entity_id=user_id
                )
                log_db.close()
            except Exception as e:
                logger.error(f"Failed to log deletion activity: {e}")

            return jsonify({
                "success": True,
                "message": "User deleted successfully",
                "deleted_staff_count": deleted_staff_count
            })
            
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        import traceback
        tb = traceback.format_exc()
        logger.error(f"Error deleting user: {tb}")
        # Identify constraint failures for a better error message
        error_str = str(e).lower()
        if "foreign key constraint" in error_str or "integrityerror" in error_str:
            return jsonify({"success": False, "message": "Cannot delete user due to existing dependent records.", "detail": str(e)}), 409
        return jsonify({"success": False, "message": f"Error deleting user: {str(e)}", "detail": tb}), 500
    finally:
        db.close()

@app.route("/api/admin/players/<int:player_id>", methods=['DELETE'])
def admin_delete_player(player_id: int):
    current_user = get_current_user()
    db = SessionLocal()
    try:
        if current_user.user_type != models.UserType.admin and str(current_user.user_type) != "admin":
            return jsonify({"success": False, "message": "Only admins can delete players"}), 403
            
        player = db.query(models.Player).filter(models.Player.player_id == player_id).first()
        if not player:
            return jsonify({"success": False, "message": "Player not found"}), 404
            
        # Optional: Delete associated user account
        user = db.query(models.User).filter(models.User.user_id == player.user_id).first()
        
        # Log activity
        log_activity(db, current_user.user_id, "PLAYER_DELETED", f"Deleted player {player.full_name}", "player", player_id)
        
        if user:
            uid = user.user_id
            db.query(models.Transaction).filter((models.Transaction.from_user_id == uid) | (models.Transaction.to_user_id == uid)).delete(synchronize_session=False)
            db.query(models.Message).filter(models.Message.sender_id == uid).delete(synchronize_session=False)
            db.query(models.PlayerSkillRating).filter(models.PlayerSkillRating.rated_by == uid).delete(synchronize_session=False)
            db.query(models.Session).filter(models.Session.user_id == uid).delete(synchronize_session=False)
            
        db.query(models.PlayerSkillRating).filter(models.PlayerSkillRating.player_id == player_id).delete(synchronize_session=False)
        db.query(models.Bid).filter(models.Bid.player_id == player_id).delete(synchronize_session=False)
        db.query(models.TeamPlayer).filter(models.TeamPlayer.player_id == player_id).delete(synchronize_session=False)

        db.delete(player)
        if user:
            db.delete(user)
        db.commit()
        return jsonify({"success": True, "message": "Player deleted successfully"})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting player: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@app.route("/api/admin/teams/<int:team_id>", methods=['DELETE'])
def admin_delete_team(team_id: int):
    current_user = get_current_user()
    db = SessionLocal()
    try:
        if current_user.user_type != models.UserType.admin and str(current_user.user_type) != "admin":
            return jsonify({"success": False, "message": "Only admins can delete teams"}), 403
            
        team = db.query(models.Team).filter(models.Team.team_id == team_id).first()
        if not team:
            return jsonify({"success": False, "message": "Team not found"}), 404
            
        # Log activity
        log_activity(db, current_user.user_id, "TEAM_DELETED", f"Deleted team {team.team_name}", "team", team_id)
        
        db.query(models.Bid).filter(models.Bid.team_id == team_id).delete(synchronize_session=False)
        db.query(models.TeamPlayer).filter(models.TeamPlayer.team_id == team_id).delete(synchronize_session=False)
        
        db.delete(team)
        db.commit()
        return jsonify({"success": True, "message": "Team deleted successfully"})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting team: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@app.route("/register/team-owner", methods=['POST'])
def register_team_owner():
    registration_data = request.get_json()
    db = SessionLocal()
    
    try:
        logger.info("Starting team owner registration...")
        
        # Extract user data and team owner data from the combined request
        try:
            user_data = registration_data.get('user_data')
            team_owner_data = registration_data.get('team_owner_data')
            logger.info(f"Received registration data - User: {user_data}, Team Owner: {team_owner_data}")
            
            # Log the incoming request data for debugging
            logger.debug(f"Incoming request data: {registration_data}")
            
        except HTTPException:
            
            raise
            
        except Exception as e:
            error_msg = f"Error parsing registration data: {str(e)}"
            logger.error(error_msg, exc_info=True)
            abort(400, description="Invalid registration data")
        
        # Validate required fields
        required_user_fields = ['username', 'email', 'phone']
        missing_user_fields = [field for field in required_user_fields if not user_data.get(field)]
        if missing_user_fields:
            error_msg = f"Missing required fields: {', '.join(missing_user_fields)}"
            logger.warning(f"Validation failed: {error_msg}")
            return jsonify({"success": False, "message": error_msg}), 400
            
        if not team_owner_data.get('team_name') or not team_owner_data.get('owner_name'):
            return jsonify({"success": False, "message": "Team name and owner name are required fields"}), 400
        
        # Check if email already exists (we'll use email as the primary identifier)
        try:
            logger.info(f"Checking if user already exists with email: {user_data['email']}")
            
            # First check if email exists
            existing_email = db.query(models.User).filter(
                models.User.email == user_data['email']
            ).first()
            
            if existing_email:
                logger.warning(f"Email already registered: {user_data['email']}")
                return jsonify({"success": False, "message": "This email is already registered. Please use a different email or try logging in."}), 400
            
            # Generate a username from email if not provided or if it's the same as email
            if not user_data.get('username') or user_data.get('username') == user_data['email']:
                # Use the part before @ as username, or generate a random one if not valid
                username = user_data['email'].split('@')[0]
                # Remove any non-alphanumeric characters and limit length
                username = ''.join(c for c in username if c.isalnum() or c in ('_', '-'))[:30]
                if not username:  # If no valid characters, generate a random username
                    import random
                    import string
                    username = 'user_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
                user_data['username'] = username
                logger.info(f"Generated username: {username} for email: {user_data['email']}")
            
            # Check if the generated username already exists
            existing_username = db.query(models.User).filter(
                models.User.username == user_data['username']
            ).first()
            
            if existing_username:
                # If username exists, append a random string to make it unique
                import random
                import string
                user_data['username'] = f"{user_data['username']}_{''.join(random.choices(string.digits, k=4))}"
                logger.info(f"Adjusted username to be unique: {user_data['username']}")
                
        except HTTPException:
                
            raise
                
        except Exception as e:
            logger.error(f"Error checking for existing user: {str(e)}", exc_info=True)
            return jsonify({"success": False, "message": "Registration failed - error processing request"}), 500
        
        # Start transaction
        try:
            # Check if username already exists
            existing_username = db.query(models.User).filter(
                func.lower(models.User.username) == user_data['username'].lower()
            ).first()
            
            if existing_username:
                error_msg = f"Username '{user_data['username']}' is already taken"
                logger.warning(error_msg)
                return jsonify({"success": False, "message": error_msg}), 400
            
            # Create user with password
            try:
                # Hash the password if provided
                password_hash = None
                if user_data.get('password'):
                    password_hash = bcrypt.hashpw(user_data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                
                # Normalize phone
                owner_phone = user_data.get('phone', '')
                if not owner_phone or not str(owner_phone).strip():
                    owner_phone = None
                else:
                    owner_phone = str(owner_phone).strip()

                # Create the user
                db_user = models.User(
                    username=user_data['username'],
                    email=user_data['email'],
                    phone=owner_phone,
                    user_type=models.UserType.team_owner,
                    is_active=False,  # Inactive until admin approves
                    password_hash=password_hash
                )
                
                db.add(db_user)
                db.flush()  # Flush to get the user_id
                
                logger.info(f"Created team owner for user_id: {db_user.user_id}")
                
                # Create team owner
                db_team_owner = models.TeamOwner(
                    user_id=db_user.user_id,
                    owner_name=team_owner_data['owner_name'],
                    company_name=team_owner_data.get('company_name', ''), # Use team name as company name
                    address=team_owner_data['address'],
                    wallet_balance=0.0
                )
                
                db.add(db_team_owner)
                db.flush()
                
                # Create team request
                event_id = team_owner_data.get('event_id')
                if event_id:
                     event = db.query(models.Event).with_for_update().filter(models.Event.event_id == event_id).first()
                     if event:
                         # Check if event is full (Teams)
                         active_teams_count = db.query(models.Team).filter(
                             models.Team.event_id == event.event_id, 
                             models.Team.status.in_(['active', 'pending', 'inactive']) # count all registered teams to be safe
                         ).count()
                         
                         if event.max_teams and active_teams_count >= event.max_teams:
                             logger.warning(f"Registration failed - Event is full (Max Teams): {event.title}")
                             db.rollback()
                             return jsonify({"success": False, "message": f"Registration closed for {event.title}. Max teams limit reached. Please contact admin."}), 400
                        
                         # We don't increment current_participants for team owners anymore, that's for players.

                new_team = models.Team(
                    team_name=team_owner_data['team_name'],
                    owner_id=db_team_owner.team_owner_id,
                    event_id=event_id if event_id else None,
                    status='inactive' # Team is inactive until approved
                )
                
                db.add(new_team)
                db.flush()

                # Process staff invitations (Team Manager and Team Analyst)
                staff_invitations = []
                
                # Team Manager invitation
                team_manager_name = team_owner_data.get('teamManagerName')
                team_manager_email = team_owner_data.get('teamManagerEmail')
                
                if team_manager_name and team_manager_email:
                    try:
                        # Check if email already exists
                        existing_manager = db.query(models.User).filter(
                            models.User.email == team_manager_email
                        ).first()
                        
                        if not existing_manager:
                            # Generate verification token
                            verification_token = secrets.token_urlsafe(32)
                            
                            # Normalize phone
                            manager_phone = team_owner_data.get('teamManagerPhone', '')
                            if not manager_phone or not str(manager_phone).strip():
                                manager_phone = None
                            else:
                                manager_phone = str(manager_phone).strip()

                            # Create staff user (Team Manager)
                            manager_user = models.User(
                                username=team_manager_email.split('@')[0][:30],  # Temporary username
                                email=team_manager_email,
                                phone=manager_phone,
                                user_type=models.UserType.team_manager,
                                parent_user_id=db_user.user_id,  # Link to team owner
                                is_invited=True,
                                invitation_status='pending',
                                is_active=False,  # Cannot login until password is set
                                is_verified=False,
                                verification_token=verification_token,
                                password_hash=None
                            )
                            
                            db.add(manager_user)
                            db.flush()
                            
                            staff_invitations.append({
                                'role': 'team_manager',
                                'name': team_manager_name,
                                'email': team_manager_email,
                                'token': verification_token,
                                'user_id': manager_user.user_id
                            })
                            
                            logger.info(f"Created Team Manager invitation for {team_manager_email}")
                    except HTTPException:
                        raise
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Error creating Team Manager invitation: {str(e)}")
                        raise e
                
                # Team Analyst invitation
                team_analyst_name = team_owner_data.get('teamAnalystName')
                team_analyst_email = team_owner_data.get('teamAnalystEmail')
                
                if team_analyst_name and team_analyst_email:
                    try:
                        # Check if email already exists
                        existing_analyst = db.query(models.User).filter(
                            models.User.email == team_analyst_email
                        ).first()
                        
                        if not existing_analyst:
                            # Generate verification token
                            verification_token = secrets.token_urlsafe(32)
                            
                            # Normalize phone
                            analyst_phone = team_owner_data.get('teamAnalystPhone', '')
                            if not analyst_phone or not str(analyst_phone).strip():
                                analyst_phone = None
                            else:
                                analyst_phone = str(analyst_phone).strip()

                            # Create staff user (Team Analyst)
                            analyst_user = models.User(
                                username=team_analyst_email.split('@')[0][:30],  # Temporary username
                                email=team_analyst_email,
                                phone=analyst_phone,
                                user_type=models.UserType.team_analyst,
                                parent_user_id=db_user.user_id,  # Link to team owner
                                is_invited=True,
                                invitation_status='pending',
                                is_active=False,  # Cannot login until password is set
                                is_verified=False,
                                verification_token=verification_token,
                                password_hash=None
                            )
                            
                            db.add(analyst_user)
                            db.flush()
                            
                            staff_invitations.append({
                                'role': 'team_analyst',
                                'name': team_analyst_name,
                                'email': team_analyst_email,
                                'token': verification_token,
                                'user_id': analyst_user.user_id
                            })
                            
                            logger.info(f"Created Team Analyst invitation for {team_analyst_email}")
                    except HTTPException:
                        raise
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Error creating Team Analyst invitation: {str(e)}")
                        raise e

                db.commit()
                
                # Refresh to get the generated IDs
                db.refresh(db_user)
                db.refresh(db_team_owner)
                db.refresh(new_team)
                
                # Log successful registration to activity logs
                try:
                    log_activity(
                        db=db,
                        user_id=db_user.user_id,
                        action_type="TEAM_OWNER_REGISTERED",
                        action_description=f"New team owner registered: {db_user.email}",
                        entity_type="user",
                        entity_id=db_user.user_id,
                    )
                except Exception as log_err:
                    logger.error(f"Failed to log team owner registration activity: {log_err}")

                # Log successful registration in app logs
                logger.info(f"Team owner registered successfully: {db_user.user_id}")
                
                # Prepare staff invitation links
                invitation_links = []
                for invitation in staff_invitations:
                    verification_url = f"{request.host_url}email-verification?token={invitation['token']}"
                    invitation_links.append({
                        'role': invitation['role'],
                        'name': invitation['name'],
                        'email': invitation['email'],
                        'verification_link': verification_url
                    })
                
                return {
                    "message": "Team owner registration successful. Waiting for admin approval.",
                    "success": True,
                    "user_id": db_user.user_id,
                    "team_owner_id": db_team_owner.team_owner_id,
                    "team_id": new_team.team_id,
                    "staff_invitations": invitation_links
                }
                
            except SQLAlchemyError as e:
                db.rollback()
                error_msg = f"Database error during registration: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return jsonify({
                    "status": "error",
                    "message": "Registration failed due to a database error",
                    "errors": [error_msg]
                }), 500
                
        except HTTPException:
                
            raise
                
        except Exception as e:
            db.rollback()
            error_msg = f"Unexpected error during registration: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return jsonify({
                "status": "error",
                "message": "An unexpected error occurred during registration",
                "errors": [error_msg]
            }), 500
            
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Database error during team owner registration: {str(e)}", exc_info=True)
            return jsonify({"success": False, "message": "Database error during registration"}), 500
            
    except HTTPException:
            
        raise
            
    except Exception as e:
        error_msg = f"Unexpected error in team owner registration: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({"success": False, "message": f"An unexpected error occurred: {str(e)}"}), 500
    finally:
        db.close()

# -------------------------
# Consolidated Event Management Endpoints
# -------------------------




# GET all events
@app.route("/events/", methods=['GET'])
@app.route("/api/events", methods=['GET'])
@app.route("/api/events/", methods=['GET'])
def get_events():
    """
    Get all events with optional filtering by live status.
    """
    db = SessionLocal()
    try:
        from sqlalchemy.orm import joinedload
        query = db.query(models.Event).options(joinedload(models.Event.sports))
        
        skip = request.args.get('skip', 0, type=int)
        limit = request.args.get('limit', 100, type=int)
        is_live = request.args.get('is_live', type=bool)
        
        # Filter by live status if provided
        if is_live is not None:
            query = query.filter(models.Event.is_live == is_live)
        
        # Order by start date descending (newest first)
        query = query.order_by(desc(models.Event.start_date))
        
        # Apply pagination
        events = query.offset(skip).limit(limit).all()
        
        result = []
        for event in events:
            # Dynamically compute counts using SQL
            teams_count = db.query(models.Team).filter(
                models.Team.event_id == event.event_id,
                models.Team.status.in_(['active', 'pending', 'inactive'])
            ).count()
            
            players_count = db.query(models.Player).join(
                models.player_events, 
                models.Player.player_id == models.player_events.c.player_id
            ).filter(
                models.player_events.c.event_id == event.event_id,
                models.Player.is_active == True
            ).count()
            
            result.append({
                "event_id": event.event_id,
                "title": event.title,
                "description": event.description,
                "start_date": event.start_date.isoformat() if event.start_date else None,
                "end_date": event.end_date.isoformat() if event.end_date else None,
                "location": event.location,
                "status": event.status,
                "is_live": event.is_live,
                "budget": float(event.budget) if event.budget else None,
                "base_prices": event.base_prices,
                "registration_fee": float(event.registration_fee) if event.registration_fee else 0.0,
                "registered_players_count": players_count,
                "registered_teams_count": teams_count,
                "max_players": event.max_players,
                "max_teams": event.max_teams,
                "sports": [{"sport_id": s.sport_id, "name": s.name} for s in event.sports] if event.sports else []
            })
            
        return jsonify(result)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error fetching events: {str(e)}\n{traceback.format_exc()}")
        abort(500, description=f"Error fetching events: {str(e)}")
    finally:
        db.close()


# GET live events
@app.route("/events/live", methods=['GET'])
@app.route("/api/events/live", methods=['GET'])
def get_live_events():
    """
    Get all live events.
    """
    db = SessionLocal()
    try:
        from sqlalchemy.orm import joinedload
        events = db.query(models.Event).options(joinedload(models.Event.sports)).filter(models.Event.is_live == True).all()
        result = []
        for event in events:
            teams_count = db.query(models.Team).filter(
                models.Team.event_id == event.event_id,
                models.Team.status.in_(['active', 'pending', 'inactive'])
            ).count()
            
            players_count = db.query(models.Player).join(
                models.player_events, 
                models.Player.player_id == models.player_events.c.player_id
            ).filter(
                models.player_events.c.event_id == event.event_id,
                models.Player.is_active == True
            ).count()
            
            result.append({
                "event_id": event.event_id,
                "title": event.title,
                "description": event.description,
                "start_date": event.start_date.isoformat() if event.start_date else None,
                "end_date": event.end_date.isoformat() if event.end_date else None,
                "location": event.location,
                "status": event.status,
                "is_live": event.is_live,
                "budget": float(event.budget) if event.budget else None,
                "base_prices": event.base_prices,
                "registration_fee": float(event.registration_fee) if event.registration_fee else 0.0,
                "registered_players_count": players_count,
                "registered_teams_count": teams_count,
                "max_players": event.max_players,
                "max_teams": event.max_teams,
                "sports": [{"sport_id": s.sport_id, "name": s.name} for s in event.sports] if event.sports else []
            })
            
        return jsonify(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching live events: {str(e)}")
        abort(500, description=f"Error fetching live events: {str(e)}")
    finally:
        db.close()


# GET single event
@app.route("/events/<int:event_id>", methods=['GET'])
@app.route("/api/events/<int:event_id>", methods=['GET'])
def get_event(event_id: int):
    """
    Get a single event by ID.
    """
    db = SessionLocal()
    try:
        from sqlalchemy.orm import joinedload
        event = db.query(models.Event).options(joinedload(models.Event.sports)).filter(models.Event.event_id == event_id).first()
        if not event:
            abort(404, description="Event not found")
        
        teams_count = db.query(models.Team).filter(
            models.Team.event_id == event.event_id,
            models.Team.status.in_(['active', 'pending', 'inactive'])
        ).count()
        
        players_count = db.query(models.Player).join(
            models.player_events, 
            models.Player.player_id == models.player_events.c.player_id
        ).filter(
            models.player_events.c.event_id == event.event_id,
            models.Player.is_active == True
        ).count()

        return jsonify({
            "event_id": event.event_id,
            "title": event.title,
            "description": event.description,
            "start_date": event.start_date.isoformat() if event.start_date else None,
            "end_date": event.end_date.isoformat() if event.end_date else None,
            "location": event.location,
            "status": event.status,
            "is_live": event.is_live,
            "budget": float(event.budget) if event.budget else None,
            "base_prices": event.base_prices,
            "registration_fee": float(event.registration_fee) if event.registration_fee else 0.0,
            "registered_players_count": players_count,
            "registered_teams_count": teams_count,
            "max_players": event.max_players,
            "max_teams": event.max_teams,
            "sports": [{"sport_id": s.sport_id, "name": s.name} for s in event.sports] if event.sports else []
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching event: {str(e)}")
        abort(500, description=f"Error fetching event: {str(e)}")
    finally:
        db.close()


# POST create event
@app.route("/events/", methods=['POST'])
@app.route("/api/events/", methods=['POST'])
def create_event():
    """
    Create a new event. Only admins can create events.
    """
    current_user = get_current_user()
    event_data = request.get_json()
    db = SessionLocal()
    
    # Check if user is admin
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can create events")
    
    try:
        # Parse datetime strings to handle ISO format with 'Z' suffix
        def parse_datetime(date_str):
            if not date_str:
                return None
            # Handle ISO format with 'Z' suffix (UTC)
            if date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            try:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except ValueError:
                # Fallback to parsing with dateutil if available
                try:
                    from dateutil import parser
                    return parser.parse(date_str)
                except ImportError:
                    # Final fallback - manual parsing
                    return datetime.strptime(date_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')

        # --- Cricket Implementation: Server-side validation and copy of master defaults ---
        sport_id = event_data.get('sport_id')
        event_config = event_data.get('event_config')
        
        if sport_id:
            sport = db.query(models.Sport).filter(models.Sport.sport_id == sport_id).first()
            if sport and sport.name.lower() == 'cricket':
                # Load defaults from Sport Master
                master_rules = sport.default_auction_rules or {}
                
                # Use submitted values if provided, otherwise fallback to Sport Master defaults
                budget = event_data.get('budget') if event_data.get('budget') is not None else master_rules.get('default_budget', 0)
                bid_time_limit = event_data.get('bid_time_limit') if event_data.get('bid_time_limit') is not None else master_rules.get('default_timer', 20)
                
                # For base prices, ensure we use the master categories config if the user didn't submit a full base_prices dict
                base_prices = event_data.get('base_prices')
                if not base_prices and sport.categories_config:
                    base_prices = {cat.get('name'): cat.get('base_price', 1000000) for cat in sport.categories_config if isinstance(cat, dict)}
                
                # Build finalized event configuration without duplicating source-of-truth fields
                final_event_config = event_config or {}
                # Add any additional flexible config here, e.g., roles or specific cricket mechanics
                if 'roles_config' not in final_event_config and sport.roles_config:
                    final_event_config['roles_config'] = sport.roles_config

                # Create new event mapped to authoritative fields
                new_event = models.Event(
                    title=event_data.get('title'),
                    description=event_data.get('description'),
                    start_date=parse_datetime(event_data.get('start_date')),
                    end_date=parse_datetime(event_data.get('end_date')),
                    registration_deadline=parse_datetime(event_data.get('registration_deadline')),
                    location=event_data.get('location'),
                    status=event_data.get('status'),
                    budget=budget,
                    base_prices=base_prices,
                    bid_time_limit=bid_time_limit,
                    registration_fee=event_data.get('registration_fee'),
                    max_players=event_data.get('max_players'),
                    max_teams=event_data.get('max_teams'),
                    extra_info=event_data.get('extra_info'),
                    is_live=event_data.get('is_live'),
                    creator_id=current_user.user_id,
                    sport_id=sport_id,
                    event_config=final_event_config
                )
            else:
                # Basic creation for non-cricket or missing sport
                new_event = models.Event(
                    title=event_data.get('title'),
                    description=event_data.get('description'),
                    start_date=parse_datetime(event_data.get('start_date')),
                    end_date=parse_datetime(event_data.get('end_date')),
                    registration_deadline=parse_datetime(event_data.get('registration_deadline')),
                    location=event_data.get('location'),
                    status=event_data.get('status'),
                    budget=event_data.get('budget'),
                    base_prices=event_data.get('base_prices'),
                    bid_time_limit=event_data.get('bid_time_limit'),
                    registration_fee=event_data.get('registration_fee'),
                    max_players=event_data.get('max_players'),
                    max_teams=event_data.get('max_teams'),
                    extra_info=event_data.get('extra_info'),
                    is_live=event_data.get('is_live'),
                    creator_id=current_user.user_id,
                    sport_id=sport_id,
                    event_config=event_config
                )
        else:
            # Legacy fallback
            new_event = models.Event(
                title=event_data.get('title'),
                description=event_data.get('description'),
                start_date=parse_datetime(event_data.get('start_date')),
                end_date=parse_datetime(event_data.get('end_date')),
                registration_deadline=parse_datetime(event_data.get('registration_deadline')),
                location=event_data.get('location'),
                status=event_data.get('status'),
                budget=event_data.get('budget'),
                base_prices=event_data.get('base_prices'),
                bid_time_limit=event_data.get('bid_time_limit'),
                registration_fee=event_data.get('registration_fee'),
                max_players=event_data.get('max_players'),
                max_teams=event_data.get('max_teams'),
                extra_info=event_data.get('extra_info'),
                is_live=event_data.get('is_live'),
                creator_id=current_user.user_id,
                event_config=event_config
            )
        
        db.add(new_event)
        db.flush() # Get the event_id

        # Handle sports legacy event_sports link
        sport_names = event_data.get('sport_names', [])
        if sport_names:
            for sport_name in sport_names:
                sport = db.query(models.Sport).filter(
                    func.lower(models.Sport.name) == sport_name.lower()
                ).first()
                
                if not sport:
                    sport = models.Sport(name=sport_name, is_active=True)
                    db.add(sport)
                    db.flush()
                
                if sport not in new_event.sports:
                    new_event.sports.append(sport)
        elif sport_id:
             # Ensure the new authoritative sport is also added to event_sports for backward compatibility
             sport = db.query(models.Sport).filter(models.Sport.sport_id == sport_id).first()
             if sport and sport not in new_event.sports:
                  new_event.sports.append(sport)
        
        # Log activity
        log_activity(db, current_user.user_id, "EVENT_CREATED", f"Created event {new_event.title}", "event", new_event.event_id)
        
        db.commit()
        db.refresh(new_event)
        return jsonify({
            "event_id": new_event.event_id,
            "title": new_event.title,
            "description": new_event.description,
            "start_date": new_event.start_date.isoformat() if new_event.start_date else None,
            "end_date": new_event.end_date.isoformat() if new_event.end_date else None,
            "status": new_event.status,
            "is_live": new_event.is_live,
            "budget": float(new_event.budget) if new_event.budget else None,
            "max_players": new_event.max_players,
            "max_teams": new_event.max_teams
        })
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating event: {str(e)}")
        abort(500, description=f"Error creating event: {str(e)}")
    finally:
        db.close()


# PUT update event
@app.route("/events/<int:event_id>", methods=['PUT'])
@app.route("/api/events/<int:event_id>", methods=['PUT'])
def update_event(event_id: int):
    """
    Update an existing event. Only admins can update events.
    """
    current_user = get_current_user()
    event_data = request.get_json()
    db = SessionLocal()
    
    # Check if user is admin
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can update events")
    
    event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
    if not event:
        abort(404, description="Event not found")
    
    try:
        # Parse datetime strings to handle ISO format with 'Z' suffix
        def parse_datetime(date_str):
            if not date_str:
                return None
            # Handle ISO format with 'Z' suffix (UTC)
            if date_str.endswith('Z'):
                date_str = date_str[:-1] + '+00:00'
            try:
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except ValueError:
                # Fallback to parsing with dateutil if available
                try:
                    from dateutil import parser
                    return parser.parse(date_str)
                except ImportError:
                    # Final fallback - manual parsing
                    return datetime.strptime(date_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')

        # Update fields dynamically from request data
        sport_names = event_data.pop('sport_names', None)
        
        for key, value in event_data.items():
            if hasattr(event, key):
                if key in ['start_date', 'end_date', 'registration_deadline']:
                    if value is not None:
                        setattr(event, key, parse_datetime(value))
                elif key == "status" and value is not None:
                    setattr(event, key, value.value if hasattr(value, 'value') else value)
                else:
                    setattr(event, key, value)
            
        if sport_names is not None:
            # Clear existing sports
            event.sports = []
            
            for sport_name in sport_names:
                sport = db.query(models.Sport).filter(
                    func.lower(models.Sport.name) == sport_name.lower()
                ).first()
                
                if not sport:
                    sport = models.Sport(name=sport_name, is_active=True)
                    db.add(sport)
                    db.flush()
                
                if sport not in event.sports:
                    event.sports.append(sport)
        
        # Log activity
        log_activity(db, current_user.user_id, "EVENT_UPDATED", f"Updated event {event.title}", "event", event.event_id)
        
        db.commit()
        db.refresh(event)
        return jsonify({
            "event_id": event.event_id,
            "title": event.title,
            "description": event.description,
            "start_date": event.start_date.isoformat() if event.start_date else None,
            "end_date": event.end_date.isoformat() if event.end_date else None,
            "location": event.location,
            "status": event.status,
            "is_live": event.is_live,
            "budget": float(event.budget) if event.budget else None,
            "base_prices": event.base_prices,
            "registration_fee": float(event.registration_fee) if event.registration_fee else 0.0,
            "registered_players_count": event.current_participants,
            "max_players": event.max_players,
            "max_teams": event.max_teams,
            "sports": [{"sport_id": s.sport_id, "name": s.name} for s in event.sports] if event.sports else []
        })
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating event: {str(e)}")
        abort(500, description=f"Error updating event: {str(e)}")
    finally:
        db.close()


@app.route("/debug_db", methods=['GET'])
def debug_db():
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("SHOW CREATE TABLE events")).fetchone()
            event_schema = result[1] if result else "Not found"
            result_team = conn.execute(text("SHOW CREATE TABLE teams")).fetchone()
            team_schema = result_team[1] if result_team else "Not found"
            
        return jsonify({"success": True, "event_schema": event_schema, "team_schema": team_schema})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# DELETE event
@app.route("/events/<int:event_id>", methods=['DELETE'])
@app.route("/api/events/<int:event_id>", methods=['DELETE'])
def delete_event(event_id: int):
    logger.info("DELETE EVENT: received event_id=%s", event_id)
    db = SessionLocal()
    try:
        current_user = get_current_user()
        
        user_type_val = current_user.user_type.name if hasattr(current_user.user_type, 'name') else str(current_user.user_type)
        if user_type_val != 'admin' and user_type_val != 'UserType.admin':
            return jsonify({"success": False, "message": "Only admins can delete events"}), 403
            
        logger.info("DELETE EVENT: looking up event")
        event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
        
        logger.info("DELETE EVENT: event found=%s", event is not None)
        if not event:
            return jsonify({"success": False, "message": "Event not found"}), 404
            
        logger.info("DELETE EVENT: Dependent-record lookup started")
        # 1. Identify users to delete before deleting the event
        users_to_delete = []
        
        # Process players linked to this event
        players = list(event.players)
        for player in players:
            if len(player.events) <= 1:
                users_to_delete.append(player.user_id)
                
        # Process Team Owners via Teams in this event
        teams_in_event = db.query(models.Team).filter(models.Team.event_id == event_id).all()
        owner_ids = set([team.owner_id for team in teams_in_event])
        for owner_id in owner_ids:
            other_teams = db.query(models.Team).filter(
                models.Team.owner_id == owner_id, 
                models.Team.event_id != event_id
            ).first()
            if not other_teams:
                owner = db.query(models.TeamOwner).filter(models.TeamOwner.team_owner_id == owner_id).first()
                if owner:
                    users_to_delete.append(owner.user_id)
                    
        # Include staff members of the deleted Team Owners
        if users_to_delete:
            staff_members = db.query(models.User).filter(models.User.parent_user_id.in_(users_to_delete)).all()
            for staff in staff_members:
                users_to_delete.append(staff.user_id)
        
        logger.info("DELETE EVENT: Dependent-record cleanup started for %s users", len(users_to_delete))
        # Log activity BEFORE deletion
        try:
            log_activity(db, current_user.user_id, "EVENT_DELETED", f"Deleted event {event.title} and {len(users_to_delete)} associated users", "event", event_id)
        except Exception as e:
            logger.warning("DELETE EVENT: log_activity failed: %s", str(e))
            
        # 2. Cleanup un-cascaded dependencies for users to delete
        users_to_delete = list(set(users_to_delete))
        if users_to_delete:
            for u_id in users_to_delete:
                db.query(models.Transaction).filter((models.Transaction.from_user_id == u_id) | (models.Transaction.to_user_id == u_id)).delete(synchronize_session=False)
                db.query(models.Message).filter(models.Message.sender_id == u_id).delete(synchronize_session=False)
                db.query(models.PlayerSkillRating).filter(models.PlayerSkillRating.rated_by == u_id).delete(synchronize_session=False)
                db.query(models.Session).filter(models.Session.user_id == u_id).delete(synchronize_session=False)
                
                team_owner = db.query(models.TeamOwner).filter(models.TeamOwner.user_id == u_id).first()
                if team_owner:
                    teams = db.query(models.Team).filter(models.Team.owner_id == team_owner.team_owner_id).all()
                    for team in teams:
                        db.query(models.Bid).filter(models.Bid.team_id == team.team_id).delete(synchronize_session=False)
                        db.query(models.TeamPlayer).filter(models.TeamPlayer.team_id == team.team_id).delete(synchronize_session=False)
                        db.delete(team)
                    db.delete(team_owner)
                    
                player = db.query(models.Player).filter(models.Player.user_id == u_id).first()
                if player:
                    db.query(models.PlayerSkillRating).filter(models.PlayerSkillRating.player_id == player.player_id).delete(synchronize_session=False)
                    db.query(models.Bid).filter(models.Bid.player_id == player.player_id).delete(synchronize_session=False)
                    db.query(models.TeamPlayer).filter(models.TeamPlayer.player_id == player.player_id).delete(synchronize_session=False)
                    db.delete(player)

        logger.info("DELETE EVENT: deleting event_id=%s", event_id)
        # 3. Delete event (SQLAlchemy will cascade to Teams, Auctions, Bids, TeamPlayers, etc.)
        db.delete(event)
        
        logger.info("DELETE EVENT: deleting associated users")
        # 4. Delete the users (SQLAlchemy will cascade to Player, TeamOwner, etc.)
        if users_to_delete:
            for u_id in users_to_delete:
                u_to_delete = db.query(models.User).filter(models.User.user_id == u_id).first()
                if u_to_delete:
                    db.delete(u_to_delete)

        logger.info("DELETE EVENT: committing transaction")
        db.commit()
        logger.info("DELETE EVENT: commit successful")
        return jsonify({"success": True, "message": "Event deleted successfully"}), 200
    except Exception as e:
        logger.exception("DELETE EVENT FAILED for event_id=%s", event_id)
        db.rollback()
        return jsonify({"success": False, "message": "Failed to delete event", "error": str(e)}), 500
    finally:
        db.close()


# POST add players to event (first-come-first-serve)
@app.route("/events/<int:event_id>/add-players", methods=['POST'])
def add_players_to_event(event_id: int):
    """
    Automatically add registered players to event (first-come-first-serve).
    Only admins can perform this action.
    """
    current_user = get_current_user()
    db = SessionLocal()
    
    # Check if user is admin
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can add players to events")
    
    event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
    if not event:
        abort(404, description="Event not found")
    
    try:
        abort(501, description="Bulk addition of players is not implemented. Players register individually via the registration form.")
    except HTTPException:
        raise
    except Exception as e:
        abort(500, description=f"Error adding players: {str(e)}")
    finally:
        db.close()


# POST add team owners to event
@app.route("/events/<int:event_id>/add-team-owners", methods=['POST'])
def add_team_owners_to_event(event_id: int):
    """
    Automatically add registered team owners to event (first-come-first-serve).
    Only admins can perform this action.
    """
    current_user = get_current_user()
    db = SessionLocal()
    
    # Check if user is admin
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can add team owners to events")
    
    event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
    if not event:
        abort(404, description="Event not found")
    
    try:
        abort(501, description="Bulk addition of team owners is not implemented. Owners register individually via the registration form.")
    except HTTPException:
        raise
    except Exception as e:
        abort(500, description=f"Error adding team owners: {str(e)}")
    finally:
        db.close()


# POST create team owner manually (Admin only)
@app.route("/events/<int:event_id>/create-team-owner", methods=['POST'])
def create_team_owner_admin(event_id: int):
    """
    Manually create a team owner and assign to event.
    Only admins can perform this action.
    """
    owner_data = request.get_json()
    current_user = get_current_user()
    db = SessionLocal()
    
    # Check if user is admin
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can create team owners")
    
    try:
        # 1. Create User
        # Check if email exists
        if db.query(models.User).filter(models.User.email == owner_data.get('email')).first():
            abort(400, description="Email already registered")
            
        # Check if username exists
        if db.query(models.User).filter(models.User.username == owner_data.get('username')).first():
            abort(400, description="Username already taken")
            
        # Hash password
        hashed_password = bcrypt.hashpw(owner_data.get('password').encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        new_user = models.User(
            username=owner_data.get('username'),
            email=owner_data.get('email'),
            password_hash=hashed_password,
            phone=owner_data.get('phone'),
            user_type=models.UserType.team_owner,
            is_active=True,
            is_verified=True # Admin created, so verified
        )
        db.add(new_user)
        db.flush() # Get user_id
        
        # 2. Create Team Owner Profile
        new_team_owner = models.TeamOwner(
            user_id=new_user.user_id,
            owner_name=owner_data.get('owner_name'),
            contact_number=owner_data.get('phone'),
            email=owner_data.get('email'),
            address=owner_data.get('address')
        )
        db.add(new_team_owner)
        db.flush() # Get team_owner_id
        
        # 3. Create Team linked to Event
        # Lock event to check capacity safely
        event = db.query(models.Event).with_for_update().filter(models.Event.event_id == event_id).first()
        if not event:
            db.rollback()
            abort(404, description="Event not found")
            
        active_teams_count = db.query(models.Team).filter(
            models.Team.event_id == event_id,
            models.Team.status.in_(['active', 'pending', 'inactive'])
        ).count()
        
        if event.max_teams and active_teams_count >= event.max_teams:
            db.rollback()
            abort(400, description=f"Event is full. Max {event.max_teams} teams allowed.")
            
        new_team = models.Team(
            team_name=owner_data.get('team_name'),
            owner_id=new_team_owner.team_owner_id,
            event_id=event_id,
            status='active'
        )
        db.add(new_team)
        db.commit()
        
        return jsonify({"message": "Team Owner created successfully", "team_owner_id": new_team_owner.team_owner_id})
        
    except HTTPException:
        
        raise
        
    except Exception as e:
        db.rollback()
        abort(500, description=f"Error creating team owner: {str(e)}")
    finally:
        db.close()


# POST make event live
@app.route("/events/<int:event_id>/make-live", methods=['POST'])
def make_event_live(event_id: int):
    """
    Make an event live (visible on home page) and initialize the auction.
    Only admins can perform this action.
    """
    current_user = get_current_user()
    db = SessionLocal()
    
    # Check if user is admin
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can make events live")
    
    event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
    if not event:
        abort(404, description="Event not found")
    
    try:
        event.is_live = True
        
        # Check if auction exists
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        
        if not auction:
            # Create new auction
            auction = models.Auction(
                event_id=event_id,
                creator_id=current_user.user_id,
                title=f"Auction for {event.title}",
                start_time=datetime.utcnow(),
                end_time=datetime.utcnow() + timedelta(hours=4), # Default duration
                status='in_progress',
                min_bid_increment=1000.0
            )
            db.add(auction)
        else:
            # Update existing auction
            auction.status = 'in_progress'
            if auction.start_time > datetime.utcnow():
                auction.start_time = datetime.utcnow()
        
        db.commit()
        db.refresh(event)
        
        return jsonify({
            "message": "Event is now live and auction started",
            "event_id": event.event_id,
            "title": event.title,
            "is_live": event.is_live,
            "auction_url": f"/auction-dashboard.html?id={event.event_id}"
        })
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        abort(500, description=f"Error making event live: {str(e)}")
    finally:
        db.close()


# GET live auction for event
@app.route("/events/<int:event_id>/live-auction", methods=['GET'])
def get_live_auction(event_id: int):
    """
    Get live auction details for an event.
    """
    db = SessionLocal()
    try:
        event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
        if not event:
            abort(404, description="Event not found")
    
        # Get auction for this event
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        
        if not auction:
            return jsonify({
                "message": "No auction found for this event",
                "event_id": event_id,
                "has_auction": False
            })
        
        return jsonify({
            "has_auction": True,
            "auction_url": f"/templates/live-auction.html?id={auction.event_id}",
            "auction_id": auction.auction_id,
            "event_id": auction.event_id,
            "title": auction.title,
            "status": auction.status,
            "start_time": auction.start_time.isoformat() if auction.start_time else None,
            "end_time": auction.end_time.isoformat() if auction.end_time else None
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching live auction: {str(e)}")
        abort(500, description=f"Error fetching live auction: {str(e)}")
    finally:
        db.close()


# Favicon endpoint to prevent 404 errors
@app.route('/favicon.ico', methods=['GET'])
def favicon():
    return '', 200, {'Content-Type': 'image/x-icon', 'Cache-Control': 'public, max-age=86400'}

# Serve frontend homepage (index lives in frontend/, not templates/)
@app.route("/", methods=['GET'])
def serve_frontend():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if not os.path.exists(index_path):
        abort(404, description="Frontend not found")
    return send_file(index_path)

@app.route("/player-dashboard.html", methods=['GET'])
@app.route("/player/dashboard", methods=['GET'])
def player_dashboard_page():
    dashboard_path = os.path.join(TEMPLATES_DIR, "player-dashboard.html")
    if not os.path.exists(dashboard_path):
        abort(404, description="Player dashboard not found")
    return send_file(dashboard_path)


# Team Owner Dashboard
@app.route("/team-organization/dashboard", methods=['GET'])
def team_owner_dashboard():
    dashboard_path = os.path.join(TEMPLATES_DIR, "team-owner-dashboard.html")
    if not os.path.exists(dashboard_path):
        abort(404, description="Team owner dashboard not found")
    return send_file(dashboard_path, max_age=0)

# Admin Dashboard
@app.route("/admin/dashboard", methods=['GET'])
def admin_dashboard():
    dashboard_path = os.path.join(TEMPLATES_DIR, "admin-dashboard.html")
    if not os.path.exists(dashboard_path):
        abort(404, description="Admin dashboard not found")
    return send_file(dashboard_path, max_age=0)

# Email Verification Page
@app.route("/email-verification", methods=['GET'])
def email_verification_page():
    verification_path = os.path.join(TEMPLATES_DIR, "email-verification.html")
    if not os.path.exists(verification_path):
        abort(404, description="Email verification page not found")
    return send_file(verification_path)

# Set Password Page
@app.route("/set-password", methods=['GET'])
def set_password_page():
    password_path = os.path.join(TEMPLATES_DIR, "set-password.html")
    if not os.path.exists(password_path):
        abort(404, description="Set password page not found")
    return send_file(password_path)

# Check Invitation API
@app.route("/api/check-invitation", methods=['GET'])
def check_invitation():
    token = request.args.get('token')
    if not token:
        return jsonify({"success": False, "message": "No token provided"}), 400
    
    db = SessionLocal()
    try:
        # Find user by verification token
        user = db.query(models.User).filter(
            models.User.verification_token == token,
            models.User.is_invited == True,
            models.User.invitation_status == 'pending'
        ).first()
        
        if not user:
            return jsonify({"success": False, "message": "Invalid or expired invitation"}), 404
        
        # Get team owner details
        team_owner = None
        if user.parent_user_id:
            parent_user = db.query(models.User).filter(models.User.user_id == user.parent_user_id).first()
            if parent_user:
                team_owner = db.query(models.TeamOwner).filter(models.TeamOwner.user_id == parent_user.user_id).first()
        
        # Get team name
        team_name = "N/A"
        if team_owner:
            team = db.query(models.Team).filter(models.Team.owner_id == team_owner.team_owner_id).first()
            if team:
                team_name = team.team_name
        
        return jsonify({
            "success": True,
            "role": user.user_type.value,
            "team_name": team_name,
            "owner_name": team_owner.owner_name if team_owner else "N/A"
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking invitation: {str(e)}")
        return jsonify({"success": False, "message": "Error checking invitation"}), 500
    finally:
        db.close()

# Verify Email API
@app.route("/api/verify-email", methods=['POST'])
def verify_email():
    data = request.get_json()
    token = data.get('token')
    
    if not token:
        return jsonify({"success": False, "message": "No token provided"}), 400
    
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(
            models.User.verification_token == token,
            models.User.is_invited == True,
            models.User.invitation_status == 'pending'
        ).first()
        
        if not user:
            return jsonify({"success": False, "message": "Invalid or expired invitation"}), 404
        
        # Update user as verified
        user.is_verified = True
        db.commit()
        
        return jsonify({"success": True, "message": "Email verified successfully"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying email: {str(e)}")
        db.rollback()
        return jsonify({"success": False, "message": "Error verifying email"}), 500
    finally:
        db.close()

# Set Password API
@app.route("/api/set-password", methods=['POST'])
def set_password():
    data = request.get_json()
    token = data.get('token')
    username = data.get('username')
    password = data.get('password')
    
    if not token or not username or not password:
        return jsonify({"success": False, "message": "Missing required fields"}), 400
    
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(
            models.User.verification_token == token,
            models.User.is_invited == True,
            models.User.is_verified == True
        ).first()
        
        if not user:
            return jsonify({"success": False, "message": "Invalid or expired invitation"}), 404
        
        # Check if username already exists
        existing_user = db.query(models.User).filter(
            func.lower(models.User.username) == username.lower(),
            models.User.user_id != user.user_id
        ).first()
        
        if existing_user:
            return jsonify({"success": False, "message": "Username already taken"}), 400
        
        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Update user
        user.username = username
        user.password_hash = password_hash
        user.is_active = True
        user.invitation_status = 'accepted'
        user.verification_token = None  # Clear token after use
        
        db.commit()
        
        return jsonify({"success": True, "message": "Password set successfully"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting password: {str(e)}")
        db.rollback()
        return jsonify({"success": False, "message": "Error setting password"}), 500
    finally:
        db.close()

# Bidding Page
@app.route("/bidding", methods=['GET'])
def bidding_page():
    bidding_path = os.path.join(TEMPLATES_DIR, "bidding-page.html")
    if not os.path.exists(bidding_path):
        abort(404, description="Bidding page not found")
    return send_file(bidding_path)

# Admin Index Redirect (for compatibility)
@app.route("/admin/index.html", methods=['GET'])
def admin_index():
    return redirect('/admin/dashboard')

# Catch-all: serve frontend/template files (must stay after specific routes)
@app.route("/<path:full_path>", methods=['GET'])
def catch_all(full_path: str):
    # Skip API / static / reserved prefixes (those have dedicated handlers or 404)
    if full_path.startswith(('api/', 'static/', 'css/', 'js/')):
        abort(404, description="Not found")

    if full_path.startswith(('admin/', 'team-organization/')):
        abort(404, description="Route not found")

    for candidate in (
        os.path.join(FRONTEND_DIR, full_path),
        os.path.join(TEMPLATES_DIR, full_path),
        os.path.join(STATIC_DIR, full_path),
    ):
        if os.path.isfile(candidate):
            return send_file(candidate)

    # SPA fallback → homepage
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.isfile(index_path):
        return send_file(index_path)

    abort(404, description="File not found")

# Health check endpoint
@app.route("/health", methods=['GET'])
def health_check():
    from sqlalchemy import text
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return jsonify({
            "status": "ok",
            "database": "connected"
        })
    except HTTPException:
        raise
    except Exception as e:
        return jsonify({
            "status": "error",
            "database": "disconnected",
            "error": str(e)
        })
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/teams", methods=['GET'])
def get_event_teams(event_id: int):
    """Get all teams registered for a specific event."""
    current_user = get_current_user()
    db = SessionLocal()
    
    # Allow all authenticated users to see teams (needed for live auction UI)
    # Admin, Team Owner, and Player need this data.
        
    try:
        event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
        if not event:
            abort(404, description="Event not found")
            
        # Query active teams with valid owners directly instead of using event.teams
        teams = db.query(models.Team).join(
            models.TeamOwner, models.Team.owner_id == models.TeamOwner.team_owner_id
        ).join(
            models.User, models.TeamOwner.user_id == models.User.user_id
        ).filter(
            models.Team.event_id == event_id,
            models.Team.status.in_(['active', 'pending'])
        ).all()

        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()

        teams_data = []
        for team in teams:
            owner_name = team.owner.owner_name or team.owner.company_name or "Unknown Owner"
            purse = event.budget if event else 0.00
            
            if auction:
                ts = db.query(models.AuctionTeamStatus).filter(
                    models.AuctionTeamStatus.auction_id == auction.auction_id,
                    models.AuctionTeamStatus.team_id == team.team_id
                ).first()
                if ts:
                    purse = ts.current_purse
                    
            teams_data.append({
                "team_id": team.team_id,
                "team_name": team.team_name,
                "owner_name": owner_name,
                "players_count": team.current_players or 0,
                "max_players": team.max_players or 15,
                "status": team.status,
                "budget": float(purse) if purse is not None else 0.00
            })
            
        return jsonify({
            "success": True,
            "teams": teams_data
        })
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/players", methods=['GET'])
def get_event_players(event_id: int):
    """Get all players registered for a specific event."""
    current_user = get_current_user()
    db = SessionLocal()
    
    if current_user.user_type != models.UserType.admin and str(current_user.user_type) != "admin":
        abort(403, description="Only admins can view event registrations")
        
    try:
        event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
        if not event:
            abort(404, description="Event not found")
            
        players_data = []
        for player in event.players:
            # Determine category (mocking for now if missing)
            category = "standard"
            if player.highest_winning_bid and player.highest_winning_bid > 500000:
                category = "diamond"
            elif player.highest_winning_bid and player.highest_winning_bid > 200000:
                category = "platinum"
            elif player.highest_winning_bid and player.highest_winning_bid > 100000:
                category = "gold"
                
            players_data.append({
                "id": player.player_id,
                "name": player.full_name,
                "category": category,
                "rating": player.cricket_rating or 7.0,
                "wins": player.tournaments_won or 0,
                "losses": 0, # Not tracked directly
                "basePrice": float(player.average_bid_amount or 10000),
                "image": player.profile_image_url or f"https://placehold.co/300x200/1e293b/ffffff?text={player.first_name}"
            })
            
        return jsonify(players_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching event players: {str(e)}")
        abort(500, description="Error fetching players")
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/auction", methods=['GET'])
def get_auction_by_event(event_id: int):
    """Get the auction details for a specific event."""
    current_user = get_current_user()
    db = SessionLocal()
    
    try:
        from sqlalchemy.orm import joinedload
        # Get event and auction with joinedload for players
        event = db.query(models.Event).options(joinedload(models.Event.players)).filter(models.Event.event_id == event_id).first()
        if not event:
            abort(404, description="Event not found")
            
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        if not auction:
            abort(404, description="Auction not found")

        # 1. Teams logic - joinedload owner
        teams = db.query(models.Team).options(joinedload(models.Team.owner)).filter(
            models.Team.event_id == event_id,
            models.Team.status.in_(['active', 'pending', 'inactive'])
        ).all()

        # Sort case-insensitively for deterministic bidding order
        teams.sort(key=lambda t: (t.team_name or "").lower())

        # Pre-fetch AuctionTeamStatuses
        team_ids = [t.team_id for t in teams]
        team_statuses = {}
        if team_ids:
            statuses = db.query(models.AuctionTeamStatus).filter(
                models.AuctionTeamStatus.auction_id == auction.auction_id,
                models.AuctionTeamStatus.team_id.in_(team_ids)
            ).all()
            team_statuses = {s.team_id: s for s in statuses}

        teams_data = []
        for index, team in enumerate(teams):
            owner_name = "Unknown Owner"
            if team.owner:
                owner_name = team.owner.owner_name or team.owner.company_name or "Unknown Owner"
            purse = event.budget if event.budget else 0.00
            
            ts = team_statuses.get(team.team_id)
            if ts:
                purse = ts.current_purse
                    
            teams_data.append({
                "team_id": team.team_id,
                "team_name": team.team_name,
                "owner_name": owner_name,
                "players_count": team.current_players or 0,
                "max_players": team.max_players or 15,
                "status": team.status,
                "budget": float(purse) if purse is not None else 0.00,
                "order": index + 1
            })
            
        first_bidder_team_id = teams_data[0]["team_id"] if teams_data else None

        # 2. Players logic
        winning_bids = db.query(models.Bid).filter(
            models.Bid.auction_id == auction.auction_id,
            models.Bid.status == 'won'
        ).all()
        sold_player_bids = {b.player_id: b for b in winning_bids}
        team_id_to_name = {t.team_id: t.team_name for t in teams}
        
        players_data = []
        for player in event.players:
            p_status = "UPCOMING"
            highest_bid_amount = 0
            sold_to_team = None
            
            if player.player_id in sold_player_bids:
                p_status = "SOLD"
                bid = sold_player_bids[player.player_id]
                highest_bid_amount = float(bid.amount)
                sold_to_team = team_id_to_name.get(bid.team_id, "Unknown Team")
            
            category = "Standard"
            if player.highest_winning_bid and player.highest_winning_bid > 500000:
                category = "Diamond"
            elif player.highest_winning_bid and player.highest_winning_bid > 200000:
                category = "Platinum"
            elif player.highest_winning_bid and player.highest_winning_bid > 100000:
                category = "Gold"
                
            players_data.append({
                "id": player.player_id,
                "name": player.full_name,
                "role": "Player",
                "category": category,
                "basePrice": float(player.average_bid_amount or 10000),
                "photo": player.profile_image_url or f"https://placehold.co/300x200/1e293b/ffffff?text={player.first_name}",
                "status": p_status,
                "sold_amount": highest_bid_amount,
                "sold_to": sold_to_team
            })

        # 3. Current player
        current_player_data = None
        highest_bidder_name = "-"
        if auction.current_player:
            current_player_data = {
                "id": auction.current_player.player_id,
                "name": auction.current_player.full_name,
                "role": "Player",
                "category": "Standard",
                "basePrice": float(auction.current_bid_amount),
                "age": auction.current_player.age if hasattr(auction.current_player, 'age') else "--",
                "photo": auction.current_player.profile_image_url or f"https://placehold.co/300x200/1e293b/ffffff?text={auction.current_player.first_name}"
            }
            
            winning_bid = db.query(models.Bid).filter(
                models.Bid.auction_id == auction.auction_id,
                models.Bid.player_id == auction.current_player_id
            ).order_by(desc(models.Bid.amount)).first()
            
            if winning_bid:
                highest_bidder_name = team_id_to_name.get(winning_bid.team_id, "Unknown Team")

        # Timer calculation
        bid_deadline_iso = None
        paused_time_left = None
        
        now = datetime.utcnow()
        if auction.status == 'paused':
            try:
                import json
                extra = json.loads(auction.description)
                paused_time_left = extra.get('paused_time_left')
            except:
                paused_time_left = 0
        elif auction.status in ['in_progress', 'RUNNING'] and auction.bid_deadline:
            bid_deadline_iso = auction.bid_deadline.isoformat()

        return jsonify({
            "success": True,
            "auction_id": auction.auction_id,
            "status": auction.status,
            "start_time": auction.start_time.isoformat() if auction.start_time else None,
            "current_bid": float(auction.current_bid_amount),
            "highest_bidder": highest_bidder_name,
            "title": auction.title,
            "event": {
                "id": event.event_id,
                "name": event.title,
                "status": event.status
            },
            "teams": teams_data,
            "players": players_data,
            "current_player": current_player_data,
            "first_bidder_team_id": first_bidder_team_id,
            "bid_deadline": bid_deadline_iso,
            "paused_time_left": paused_time_left
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching auction: {str(e)}")
        abort(500, description=f"Error fetching auction: {str(e)}")
    finally:
        db.close()

@app.route("/auction/<int:auction_id>/next-player", methods=['POST'])
def auction_next_player(auction_id: int):
    """Select the next player for the auction."""
    current_user = get_current_user()
    db = SessionLocal()
    
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can control auction")
    
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if not auction:
            abort(404, description="Auction not found")
        
        # Get all players in event
        event = auction.event
        if not event:
            abort(404, description="Event not found for auction")
        
        # Find available players (those not sold and not the current player)
        # We need to filter out players who have won bids in this auction
        # Get IDs of sold players
        sold_player_ids = db.query(models.Bid.player_id).filter(
            models.Bid.auction_id == auction_id,
            models.Bid.status == 'won'
        ).all()
        sold_ids = [id[0] for id in sold_player_ids]
        
        available_players = [p for p in event.players if p.player_id != auction.current_player_id and p.player_id not in sold_ids]
        
        if not available_players:
            return jsonify({"message": "No more players available"})
            
        next_player = available_players[0] # Simplest "next"
        
        auction.current_player_id = next_player.player_id
        auction.current_bid_amount = float(event.base_prices.get(next_player.category.lower() if next_player.category else 'silver', 10000)) if event.base_prices else 10000
        auction.status = 'IN_PROGRESS' # Ensure running
        
        db.commit()
        
        return jsonify({
            "message": "Next player selected",
            "player": {
                "id": next_player.player_id,
                "name": next_player.full_name,
                "base_price": auction.current_bid_amount
            }
        })
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error selecting next player: {str(e)}")
        abort(500, description=f"Error selecting next player: {str(e)}")
    finally:
        db.close()

@app.route("/auction/<int:auction_id>/sold", methods=['POST'])
def auction_sold(auction_id: int):
    """Mark current player as sold to highest bidder."""
    current_user = get_current_user()
    db = SessionLocal()
    
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can control auction")
    
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if not auction or not auction.current_player_id:
            abort(400, description="No active player in auction")
        
        # Logic to finalize bid: find highest bid for this player/auction
        winning_bid = db.query(models.Bid).filter(
            models.Bid.auction_id == auction_id,
            models.Bid.player_id == auction.current_player_id
        ).order_by(desc(models.Bid.amount)).first()
        
        if winning_bid:
            winning_bid.status = 'won'
            
            # Add to team roster
            team_player = models.TeamPlayer(
                team_id=winning_bid.team_id,
                player_id=auction.current_player_id,
                joined_date=datetime.utcnow()
            )
            db.add(team_player)
            
            # Verify wallet balance deduction should have happened at bid time or here
            # For now assuming it persists
        
        # Do NOT clear current player yet - let the frontend assume "Sold" state until "Next Player" is clicked
        # OR clear it. Usually dashboard shows "SOLD" overlay.
        # We will keep the current player set but maybe update status?
        # Auction model doesn't have "player_status".
        # Frontend logic: if player is in "sold" list, show sold.
        # But for "current state", let's clear it so dashboard updates to "Waiting".
        
        # Actually, it's better to keep it and return "Sold" status so UI can show "Sold to X".
        # But sticking to the simple logic: Next Player button clears it.
        
        # Let's clear it for now to signal "done".
        # auction.current_player_id = None
        # auction.current_bid_amount = 0
        
        db.commit()
        
        return jsonify({"message": "Player sold"})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error marking player as sold: {str(e)}")
        abort(500, description=f"Error marking player as sold: {str(e)}")
    finally:
        db.close()

@app.route("/auction/<int:auction_id>/unsold", methods=['POST'])
def auction_unsold(auction_id: int):
    """Mark current player as unsold."""
    current_user = get_current_user()
    db = SessionLocal()
    
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can control auction")
    
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if not auction:
            abort(404, description="Auction not found")
        
        # Here we might mark the player as 'unsold' in a tracking table if we had one
        # For now just clear current player
        auction.current_player_id = None
        auction.current_bid_amount = 0
        db.commit()
        
        return jsonify({"message": "Player marked unsold"})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error marking player as unsold: {str(e)}")
        abort(500, description=f"Error marking player as unsold: {str(e)}")
    finally:
        db.close()

@app.route("/auction/<int:auction_id>/pause", methods=['POST'])
def auction_pause(auction_id: int):
    current_user = get_current_user()
    db = SessionLocal()
    
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can control auction")
    
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if auction:
            auction.status = 'PAUSED'
            db.commit()
        return jsonify({"message": "Auction paused"})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error pausing auction: {str(e)}")
        abort(500, description=f"Error pausing auction: {str(e)}")
    finally:
        db.close()

@app.route("/auction/<int:auction_id>/resume", methods=['POST'])
def auction_resume(auction_id: int):
    current_user = get_current_user()
    db = SessionLocal()
    
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can control auction")
    
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if auction:
            auction.status = 'IN_PROGRESS'
            db.commit()
        return jsonify({"message": "Auction resumed"})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error resuming auction: {str(e)}")
        abort(500, description=f"Error resuming auction: {str(e)}")
    finally:
        db.close()

@app.route("/api/dashboard/admin/stats", methods=['GET'])
def get_admin_dashboard_stats():
    # current_user = get_current_user()
    # if current_user.user_type != models.UserType.admin:
    #     abort(403, description="Admin access required")
        
    db = SessionLocal()
    try:
        total_sports = db.query(func.count(models.Sport.sport_id)).scalar() or 0
        total_teams = db.query(func.count(models.Team.team_id)).scalar() or 0
        total_players = db.query(func.count(models.Player.player_id)).scalar() or 0
        total_owners = db.query(func.count(models.User.user_id)).filter(models.User.user_type == 'team_owner').scalar() or 0
        total_managers = db.query(func.count(models.User.user_id)).filter(models.User.user_type == 'team_manager').scalar() or 0
        total_analysts = db.query(func.count(models.User.user_id)).filter(models.User.user_type == 'team_analyst').scalar() or 0
        total_events = db.query(func.count(models.Event.event_id)).scalar() or 0
        
        active_auctions = db.query(func.count(models.Auction.auction_id)).filter(models.Auction.status.in_(['IN_PROGRESS', 'PAUSED'])).scalar() or 0
        completed_auctions = db.query(func.count(models.Auction.auction_id)).filter(models.Auction.status == 'COMPLETED').scalar() or 0
        
        purchased_players = db.query(func.count(models.TeamPlayer.team_player_id)).scalar() or 0
        available_players = total_players - purchased_players
        
        # Calculate auction revenue (sum of all winning bids)
        auction_revenue = db.query(func.sum(models.Bid.amount)).filter(models.Bid.status == 'won').scalar() or 0
        
        # Pending approvals (users where is_active is False)
        pending_approvals = db.query(func.count(models.User.user_id)).filter(models.User.is_active == False).scalar() or 0
        
        return jsonify({
            "total_sports": total_sports,
            "total_teams": total_teams,
            "total_players": total_players,
            "total_owners": total_owners,
            "total_managers": total_managers,
            "total_analysts": total_analysts,
            "total_events": total_events,
            "active_auctions": active_auctions,
            "completed_auctions": completed_auctions,
            "purchased_players": purchased_players,
            "available_players": available_players,
            "auction_revenue": float(auction_revenue),
            "pending_approvals": pending_approvals
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching admin stats: {str(e)}")
        abort(500, description="Error fetching stats")
    finally:
        db.close()

@app.route("/api/dashboard/team-owner/stats", methods=['GET'])
def get_team_owner_dashboard_stats():
    current_user = get_current_user()
    if current_user.user_type != models.UserType.team_owner:
        abort(403, description="Team Owner access required")
        
    db = SessionLocal()
    try:
        owner = db.query(models.TeamOwner).filter(models.TeamOwner.user_id == current_user.user_id).first()
        total_budget = 0
        squad_size = 0
        total_events = 0
        
        if owner:
            teams = db.query(models.Team).filter(models.Team.owner_id == owner.owner_id).all()
            total_budget = sum([t.budget for t in teams if t.budget]) if teams else 0
            
            for t in teams:
                squad_size += db.query(func.count(models.TeamPlayer.id)).filter(models.TeamPlayer.team_id == t.team_id).scalar() or 0
                
            total_events = db.query(func.count(models.Event.event_id)).filter(models.Event.status == 'ACTIVE').scalar() or 0
            
        return jsonify({
            "budget": total_budget,
            "squad_size": squad_size,
            "total_events": total_events
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching team owner stats: {str(e)}")
        abort(500, description="Error fetching stats")
    finally:
        db.close()

# -------------------------
# Admin Dashboard Completion APIs
# -------------------------

# Manage Sports
@app.route("/api/admin/sports", methods=['GET'])
def admin_get_sports():
    db = SessionLocal()
    try:
        sports = db.query(models.Sport).all()
        return jsonify([
            {
                "sport_id": s.sport_id,
                "name": s.name,
                "description": s.description,
                "icon_class": s.icon_class
            } for s in sports
        ])
    finally:
        db.close()

# --- CRICKET SPORT MASTER API ENDPOINTS ---

@app.route("/api/sports", methods=['GET'])
def get_sports():
    db = SessionLocal()
    try:
        sports = db.query(models.Sport).all()
        sports_data = [{
            "sport_id": s.sport_id,
            "name": s.name,
            "description": s.description,
            "icon_class": s.icon_class,
            "roles_config": s.roles_config,
            "categories_config": s.categories_config,
            "attributes_schema": s.attributes_schema,
            "default_auction_rules": s.default_auction_rules
        } for s in sports]
        return jsonify({"success": True, "sports": sports_data})
    except Exception as e:
        logger.error(f"Error fetching sports: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()

@app.route("/api/sports/<int:sport_id>", methods=['GET'])
def get_sport(sport_id: int):
    db = SessionLocal()
    try:
        sport = db.query(models.Sport).filter(models.Sport.sport_id == sport_id).first()
        if not sport:
            abort(404, description="Sport not found")
        return jsonify({
            "success": True, 
            "sport": {
                "sport_id": sport.sport_id,
                "name": sport.name,
                "description": sport.description,
                "roles_config": sport.roles_config,
                "categories_config": sport.categories_config,
                "attributes_schema": sport.attributes_schema,
                "default_auction_rules": sport.default_auction_rules
            }
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching sport {sport_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()

@app.route("/api/sports/<int:sport_id>/config", methods=['PUT'])
def update_sport_config(sport_id: int):
    current_user = get_current_user()
    if current_user.user_type != models.UserType.admin:
        abort(403, description="Only admins can update sport configuration")
        
    db = SessionLocal()
    config_data = request.get_json()
    try:
        sport = db.query(models.Sport).filter(models.Sport.sport_id == sport_id).first()
        if not sport:
            abort(404, description="Sport not found")
            
        if 'roles_config' in config_data:
            sport.roles_config = config_data['roles_config']
        if 'categories_config' in config_data:
            sport.categories_config = config_data['categories_config']
        if 'attributes_schema' in config_data:
            sport.attributes_schema = config_data['attributes_schema']
        if 'default_auction_rules' in config_data:
            sport.default_auction_rules = config_data['default_auction_rules']
            
        db.commit()
        return jsonify({"success": True, "message": "Sport configuration updated"})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating sport {sport_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db.close()

@app.route('/api/admin/db-setup', methods=['POST'])
def admin_create_sport():
    db = SessionLocal()
    try:
        data = request.json
        new_sport = models.Sport(
            name=data.get('name'),
            description=data.get('description'),
            icon_class=data.get('icon_class', 'fas fa-trophy')
        )
        db.add(new_sport)
        db.commit()
        db.refresh(new_sport)
        return jsonify({"success": True, "sport_id": new_sport.sport_id})
    finally:
        db.close()

@app.route("/api/admin/sports/<int:sport_id>", methods=['DELETE'])
def admin_delete_sport(sport_id):
    db = SessionLocal()
    try:
        sport = db.query(models.Sport).filter(models.Sport.sport_id == sport_id).first()
        if sport:
            db.delete(sport)
            db.commit()
            return jsonify({"success": True})
        abort(404, description="Sport not found")
    finally:
        db.close()

# Manage Teams (with Owners/Managers/Analysts)
@app.route("/api/admin/teams", methods=['GET'])
def admin_get_teams():
    db = SessionLocal()
    try:
        teams = db.query(models.Team).all()
        result = []
        for t in teams:
            owner = db.query(models.TeamOwner).filter(models.TeamOwner.team_owner_id == t.owner_id).first()
            owner_user = db.query(models.User).filter(models.User.user_id == owner.user_id).first() if owner else None
            
            # Fetch staff
            managers = db.query(models.User).filter(
                models.User.parent_user_id == (owner_user.user_id if owner_user else None),
                models.User.user_type == 'team_manager'
            ).all()
            analysts = db.query(models.User).filter(
                models.User.parent_user_id == (owner_user.user_id if owner_user else None),
                models.User.user_type == 'team_analyst'
            ).all()

            result.append({
                "team_id": t.team_id,
                "team_name": t.team_name,
                "budget": float(owner.wallet_balance) if owner and owner.wallet_balance else 0,
                "owner_name": owner_user.username if owner_user else "N/A",
                "manager_count": len(managers),
                "analyst_count": len(analysts)
            })
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error fetching admin teams: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()



import os
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/api/player/dashboard", methods=['GET'])
def get_player_dashboard():
    current_user = get_current_user()
    if getattr(current_user.user_type, "value", current_user.user_type) != 'player':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    db = SessionLocal()
    try:
        player = db.query(models.Player).filter(models.Player.user_id == current_user.user_id).first()
        if not player:
            return jsonify({"success": False, "message": "Player profile not found"}), 404
            
        # Overall rating calculation (basic average of sports)
        ratings = [player.cricket_rating or 0, player.football_rating or 0, player.basketball_rating or 0]
        avg_rating = sum(ratings) / 3 if any(ratings) else 0
        
        return jsonify({
            "name": f"{player.first_name} {player.last_name}",
            "avatar": player.profile_image_url,
            "avgRating": round(avg_rating, 1),
            "eventsCount": player.total_events_participated or 0,
            "successRate": player.auction_success_rate or 0,
            "avgBid": float(player.average_bid_amount) if player.average_bid_amount else 0,
            "profileViews": player.profile_views or 0,
            "teamsInterested": player.teams_interested or 0,
            "currentValue": float(player.highest_winning_bid) if player.highest_winning_bid else 0,
            
            # Achievements
            "tournamentsWon": player.tournaments_won or 0,
            "mvpAwards": player.mvp_awards or 0,
            "bestPlayerAwards": player.best_player_awards or 0,
            "proContracts": player.professional_contracts or 0,
            "stateChampion": "Yes" if player.state_level_champion else "No",
            "internationalExp": "Yes" if player.international_experience else "No"
        })
    finally:
        db.close()

@app.route("/api/player/events/upcoming", methods=['GET'])
def get_player_upcoming_events():
    current_user = get_current_user()
    if getattr(current_user.user_type, "value", current_user.user_type) != 'player':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    db = SessionLocal()
    try:
        player = db.query(models.Player).filter(models.Player.user_id == current_user.user_id).first()
        if not player:
            return jsonify({"success": False, "message": "Player profile not found"}), 404
            
        from datetime import datetime
        now = datetime.utcnow()
        upcoming_events = db.query(models.Event).join(models.player_events).filter(
            models.player_events.c.player_id == player.player_id,
            models.Event.status.in_(['upcoming', 'registration_open', 'in_progress']),
            models.Event.end_date >= now
        ).order_by(models.Event.start_date.asc()).all()
        
        events_data = [{
            "event_id": event.event_id,
            "title": event.title,
            "description": event.description,
            "start_date": event.start_date.isoformat() if event.start_date else None,
            "end_date": event.end_date.isoformat() if event.end_date else None,
            "location": event.location,
            "status": event.status,
            "registration_status": "registered"
        } for event in upcoming_events]
        
        return jsonify(events_data)
    finally:
        db.close()

@app.route("/api/player/upload-image", methods=['POST'])
def player_upload_image():
    current_user = get_current_user()
    if current_user.user_type.value != 'player':
        abort(403, description="Player access required")
        
    if 'image' not in request.files:
        return jsonify({"success": False, "message": "No image part"}), 400
        
    file = request.files['image']
    if file.filename == '':
        return jsonify({"success": False, "message": "No selected file"}), 400
        
    if file and allowed_file(file.filename):
        # Validate size (max 5MB)
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        if size > 5 * 1024 * 1024:
            return jsonify({"success": False, "message": "File exceeds 5MB limit"}), 400
            
        # Uploads go under frontend/static (Passenger-writable app tree)
        upload_folder = os.path.join(STATIC_DIR, 'uploads', 'profile_images')
        os.makedirs(upload_folder, exist_ok=True)
        
        # Create unique filename
        import uuid
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{current_user.user_id}_{uuid.uuid4().hex[:8]}.{ext}"
        filepath = os.path.join(upload_folder, filename)
        
        file.save(filepath)
        
        image_url = f"/static/uploads/profile_images/{filename}"
        
        db = SessionLocal()
        try:
            player = db.query(models.Player).filter(models.Player.user_id == current_user.user_id).first()
            if not player:
                return jsonify({"success": False, "message": "Player profile not found"}), 404
                
            # Optional: delete old image if it exists
            if player.profile_image_url and 'uploads/profile_images' in player.profile_image_url:
                old_filename = player.profile_image_url.split('/')[-1]
                old_filepath = os.path.join(upload_folder, old_filename)
                if os.path.exists(old_filepath):
                    try:
                        os.remove(old_filepath)
                    except:
                        pass
                        
            player.profile_image_url = image_url
            db.commit()
            
            # Trigger notification
            create_notification(
                user_id=current_user.user_id,
                n_type="profile",
                title="Profile Photo Updated",
                message="Your profile photo has been updated successfully."
            )
            
            return jsonify({"success": True, "message": "Image uploaded successfully", "image_url": image_url})
        finally:
            db.close()
            
    return jsonify({"success": False, "message": "Invalid file type. Only JPG, PNG, WEBP allowed."}), 400

@app.route("/api/player/remove-image", methods=['DELETE'])
def player_remove_image():
    current_user = get_current_user()
    if current_user.user_type.value != 'player':
        abort(403, description="Player access required")
        
    db = SessionLocal()
    try:
        player = db.query(models.Player).filter(models.Player.user_id == current_user.user_id).first()
        if not player:
            return jsonify({"success": False, "message": "Player profile not found"}), 404
            
        if player.profile_image_url and 'uploads/profile_images' in player.profile_image_url:
            old_filename = player.profile_image_url.split('/')[-1]
            upload_folder = os.path.join(STATIC_DIR, 'uploads', 'profile_images')
            old_filepath = os.path.join(upload_folder, old_filename)
            if os.path.exists(old_filepath):
                try:
                    os.remove(old_filepath)
                except:
                    pass
                    
        player.profile_image_url = None
        db.commit()
        return jsonify({"success": True, "message": "Image removed successfully"})
    finally:
        db.close()

# -------------------------------------------------------------------
# NOTIFICATIONS API
# -------------------------------------------------------------------
def create_notification(user_id, n_type, title, message, db_session=None):
    """Utility function to create a notification"""
    close_db = False
    if db_session is None:
        db_session = SessionLocal()
        close_db = True
        
    try:
        new_notification = models.Notification(
            user_id=user_id,
            type=n_type,
            title=title,
            message=message
        )
        db_session.add(new_notification)
        db_session.commit()
        return True
    except Exception as e:
        print(f"Error creating notification: {e}")
        return False
    finally:
        if close_db:
            db_session.close()

@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    current_user = get_current_user()
    db = SessionLocal()
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        offset = (page - 1) * limit
        
        notifications_query = db.query(models.Notification).filter(models.Notification.user_id == current_user.user_id).order_by(desc(models.Notification.created_at))
        total = notifications_query.count()
        notifications = notifications_query.offset(offset).limit(limit).all()
        
        return jsonify({
            "notifications": [
                {
                    "id": n.notification_id,
                    "type": n.type,
                    "title": n.title,
                    "message": n.message,
                    "is_read": n.is_read,
                    "created_at": n.created_at.isoformat()
                } for n in notifications
            ],
            "total": total,
            "page": page,
            "limit": limit
        })
    finally:
        db.close()

@app.route("/api/notifications/unread-count", methods=["GET"])
def get_unread_notification_count():
    current_user = get_current_user()
    db = SessionLocal()
    try:
        count = db.query(models.Notification).filter(
            models.Notification.user_id == current_user.user_id,
            models.Notification.is_read == False
        ).count()
        return jsonify({"unread_count": count})
    finally:
        db.close()

@app.route("/api/notifications/<int:notification_id>/read", methods=["PUT"])
def mark_notification_read(notification_id):
    current_user = get_current_user()
    db = SessionLocal()
    try:
        notification = db.query(models.Notification).filter(
            models.Notification.notification_id == notification_id,
            models.Notification.user_id == current_user.user_id
        ).first()
        
        if not notification:
            return jsonify({"error": "Notification not found"}), 404
            
        notification.is_read = True
        db.commit()
        return jsonify({"success": True})
    finally:
        db.close()

@app.route("/api/notifications/read-all", methods=["PUT"])
def mark_all_notifications_read():
    current_user = get_current_user()
    db = SessionLocal()
    try:
        db.query(models.Notification).filter(
            models.Notification.user_id == current_user.user_id,
            models.Notification.is_read == False
        ).update({"is_read": True})
        db.commit()
        return jsonify({"success": True})
    finally:
        db.close()

@app.route("/api/notifications/<int:notification_id>", methods=["DELETE"])
def delete_notification(notification_id):
    current_user = get_current_user()
    db = SessionLocal()
    try:
        notification = db.query(models.Notification).filter(
            models.Notification.notification_id == notification_id,
            models.Notification.user_id == current_user.user_id
        ).first()
        
        if not notification:
            return jsonify({"error": "Notification not found"}), 404
            
        db.delete(notification)
        db.commit()
        return jsonify({"success": True})
    finally:
        db.close()

# -----------------------------
# Forgot Password Flow
# -----------------------------

def send_otp_email(to_email, otp):
    """Utility to send the 6-digit OTP via email."""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_email = os.getenv("SMTP_EMAIL", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    
    if not smtp_email or not smtp_password:
        print("SMTP config is missing. Could not send email to:", to_email)
        return False
        
    try:
        msg = MIMEText(f"Your JamRig password reset verification code is: {otp}\nThis code will expire in 10 minutes.")
        msg['Subject'] = 'JamRig - Password Reset Code'
        msg['From'] = smtp_email
        msg['To'] = to_email

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print("Error sending OTP email:", e)
        return False

@app.route("/api/auth/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json()
    email = data.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            return jsonify({"error": "User with this email not found"}), 404
            
        # Generate 6-digit OTP
        otp = "".join([str(random.randint(0, 9)) for _ in range(6)])
        
        # We can store the OTP in reset_password_token and an expiry time in reset_password_expires
        user.reset_password_token = otp
        user.reset_password_expires = datetime.utcnow() + timedelta(minutes=10)
        db.commit()
        
        # Send Email
        if send_otp_email(user.email, otp):
            return jsonify({"success": True, "message": "OTP sent to your email"})
        else:
            return jsonify({"error": "Failed to send OTP email"}), 500
    finally:
        db.close()

@app.route("/api/auth/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json()
    email = data.get("email")
    otp = data.get("otp")
    
    if not email or not otp:
        return jsonify({"error": "Email and OTP are required"}), 400
        
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user or user.reset_password_token != otp:
            return jsonify({"error": "Invalid OTP"}), 400
            
        if user.reset_password_expires and datetime.utcnow() > user.reset_password_expires:
            return jsonify({"error": "OTP has expired"}), 400
            
        return jsonify({"success": True, "message": "OTP verified"})
    finally:
        db.close()

@app.route("/api/auth/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json()
    email = data.get("email")
    otp = data.get("otp")
    new_password = data.get("new_password")
    
    if not all([email, otp, new_password]):
        return jsonify({"error": "Missing required fields"}), 400
        
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user or user.reset_password_token != otp:
            return jsonify({"error": "Invalid or expired OTP"}), 400
            
        if user.reset_password_expires and datetime.utcnow() > user.reset_password_expires:
            return jsonify({"error": "OTP has expired"}), 400
            
        user.set_password(new_password)
        user.reset_password_token = None
        user.reset_password_expires = None
        db.commit()
        
        return jsonify({"success": True, "message": "Password reset successfully"})
    finally:
        db.close()

def initialize_database():
    logger.info("Initializing database...")
    try:
        with engine.connect() as conn:
            logger.info("Successfully connected to database")
            try:
                conn.execute("ALTER TABLE auctions ADD COLUMN bid_deadline DATETIME NULL")
                logger.info("Added bid_deadline to auctions table")
            except Exception:
                pass # Column already exists
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        return False


# -------------------------------------------------------------------------
# Passenger / cPanel auction engine bootstrap
# Background threads are unreliable under Passenger (idle process kill).
# We always register a request-scoped lazy tick; optional daemon thread for
# long-lived workers when ENABLE_AUCTION_ENGINE_THREAD=true.
# -------------------------------------------------------------------------
_auction_engine_started = False

def _bootstrap_auction_engine():
    global _auction_engine_started
    if _auction_engine_started:
        return
    _auction_engine_started = True
    try:
        from auction_engine import ensure_auction_engine
        ensure_auction_engine()
    except Exception as e:
        logger.warning(f"Auction engine bootstrap skipped: {e}")

@app.before_request
def _auction_tick_before_request():
    """Advance auctions on traffic — works even when Passenger kills idle workers."""
    try:
        _bootstrap_auction_engine()
        path = request.path or ""
        if path.startswith(('/api/', '/auction/', '/bidding', '/health')):
            from auction_engine import tick_auctions_if_due
            tick_auctions_if_due()
    except Exception as e:
        logger.debug(f"Auction tick skipped: {e}")


# --- WEBSOCKET REAL-TIME EVENTS (PHASE 3+) ---

@socketio.on('join_auction')
def handle_join_auction(data):
    """Clients emit this to subscribe to their specific auction room."""
    auction_id = data.get('auction_id')
    if auction_id:
        room = f"auction_{auction_id}"
        join_room(room)
        emit('lobby_update', {'message': 'A new user joined the lobby'}, to=room)

@socketio.on('leave_auction')
def handle_leave_auction(data):
    """Clients emit this when they leave the auction page."""
    auction_id = data.get('auction_id')
    if auction_id:
        room = f"auction_{auction_id}"
        leave_room(room)

@socketio.on('join_lobby')
def handle_join_lobby(data):
    """Team connects and emits this. Server broadcasts team_status_update"""
    auction_id = data.get('auction_id')
    team_id = data.get('team_id')
    if auction_id and team_id:
        room = f"auction_{auction_id}"
        join_room(room)
        
        db = SessionLocal()
        try:
            ts = db.query(models.AuctionTeamStatus).filter(
                models.AuctionTeamStatus.auction_id == auction_id,
                models.AuctionTeamStatus.team_id == team_id
            ).first()
            if ts:
                ts.status = 'JOINED'
                db.commit()
            emit('team_status_update', {'team_id': team_id, 'status': 'JOINED'}, to=room)
            
            # Emit current auction state so UI doesn't hang on CONNECTING
            auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
            if auction:
                player_data = None
                player = auction.current_player
                
                # If no current player is set yet, peek at the first pending player
                if not player:
                    first_ap = db.query(models.AuctionPlayer).filter(
                        models.AuctionPlayer.auction_id == auction_id,
                        models.AuctionPlayer.status == 'PENDING'
                    ).order_by(models.AuctionPlayer.auction_order).first()
                    if first_ap:
                        player = first_ap.player

                if player:
                    player_data = {
                        'id': player.player_id,
                        'name': player.full_name,
                        'role': getattr(player, 'bio', 'Player'),
                        'category': 'Standard',
                        'base_price': auction.current_bid_amount or 0,
                        'photo': getattr(player, 'profile_image_url', None) or getattr(player, 'photo', None)
                    }
                
                status_to_emit = auction.status.upper() if auction.status else 'LOBBY'
                if status_to_emit == 'IN_PROGRESS':
                    status_to_emit = 'RUNNING'

                import json
                time_left = None
                if status_to_emit == 'PAUSED':
                    try:
                        extra = json.loads(auction.description) if auction.description else {}
                        time_left = extra.get('paused_time_left')
                    except:
                        pass
                
                emit('auction_update', {
                    'status': status_to_emit,
                    'current_bid': auction.current_bid_amount,
                    'current_player': player_data,
                    'bid_deadline': auction.bid_deadline.isoformat() + "Z" if auction.bid_deadline else None,
                    'paused_time_left': time_left
                }, to=request.sid)

        except Exception as e:
            logger.error(f"Error in join_lobby: {e}")
        finally:
            db.close()

@socketio.on('team_ready')
def handle_team_ready(data):
    auction_id = data.get('auction_id')
    team_id = data.get('team_id')
    if auction_id and team_id:
        room = f"auction_{auction_id}"
        db = SessionLocal()
        try:
            ts = db.query(models.AuctionTeamStatus).filter(
                models.AuctionTeamStatus.auction_id == auction_id,
                models.AuctionTeamStatus.team_id == team_id
            ).first()
            if ts:
                ts.status = 'READY'
                db.commit()
            emit('team_status_update', {'team_id': team_id, 'status': 'READY'}, to=room)
        except Exception as e:
            logger.error(f"Error in team_ready: {e}")
        finally:
            db.close()


@socketio.on('admin_start_auction')
def handle_admin_start_auction(data):
    auction_id = data.get('auction_id')
    if not auction_id:
        return {'error': 'Missing auction_id'}
    
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if not auction:
            return {'error': 'Auction not found'}
        
        auction.status = 'in_progress'
        
        if not auction.current_player_id:
            first_ap = db.query(models.AuctionPlayer).filter(
                models.AuctionPlayer.auction_id == auction_id,
                models.AuctionPlayer.status == 'PENDING'
            ).order_by(models.AuctionPlayer.auction_order).first()
            
            if not first_ap:
                return {'error': 'No eligible players available for this auction.'}
                
            auction.current_player_id = first_ap.player_id
            first_ap.started_at = datetime.utcnow()
            auction.current_bid_amount = first_ap.base_price
        
        now = datetime.utcnow()
        auction.current_player_bid_start = now
        auction.bid_deadline = now + timedelta(seconds=20)
        db.commit()
        
        player_data = None
        if auction.current_player:
            player_data = {
                'id': auction.current_player.player_id,
                'name': auction.current_player.full_name,
                'role': getattr(auction.current_player, 'bio', 'Player'),
                'category': 'Standard',
                'base_price': auction.current_bid_amount,
                'photo': getattr(auction.current_player, 'profile_image_url', None)
            }
        
        room = f"auction_{auction_id}"
        emit('auction_update', {
            'status': 'RUNNING',
            'current_player': player_data,
            'current_bid': auction.current_bid_amount,
            'bid_deadline': auction.bid_deadline.isoformat() + "Z"
        }, to=room, namespace="/")
        
        return {'success': True}
    except Exception as e:
        logger.error(f"Error starting auction: {e}")
        return {'error': str(e)}
    finally:
        db.close()

@socketio.on('admin_pause_auction')
def handle_admin_pause_auction(data):
    auction_id = data.get('auction_id')
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if auction and auction.status == 'in_progress':
            auction.status = 'paused'
            now = datetime.utcnow()
            time_left = 0
            if auction.bid_deadline and auction.bid_deadline > now:
                time_left = (auction.bid_deadline - now).total_seconds()
            
            import json
            extra = {}
            if auction.description:
                try: extra = json.loads(auction.description)
                except: pass
            extra['paused_time_left'] = time_left
            auction.description = json.dumps(extra)
            
            auction.bid_deadline = None
            db.commit()
            
            room = f"auction_{auction_id}"
            emit('auction_update', {
                'status': 'PAUSED',
                'paused_time_left': time_left
            }, to=room, namespace="/")
        return {'success': True}
    finally:
        db.close()

@socketio.on('admin_resume_auction')
def handle_admin_resume_auction(data):
    auction_id = data.get('auction_id')
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if auction and auction.status == 'paused':
            auction.status = 'in_progress'
            
            import json
            time_left = 20
            if auction.description:
                try: 
                    extra = json.loads(auction.description)
                    time_left = extra.get('paused_time_left', 20)
                except: pass
                
            now = datetime.utcnow()
            auction.bid_deadline = now + timedelta(seconds=time_left)
            
            # Shift current_player_bid_start so auction engine doesn't prematurely timeout
            if auction.event and auction.event.bid_time_limit:
                bid_time_limit = auction.event.bid_time_limit
            else:
                bid_time_limit = 20
                
            auction.current_player_bid_start = now - timedelta(seconds=(bid_time_limit - time_left))
            db.commit()
            
            room = f"auction_{auction_id}"
            emit('auction_update', {
                'status': 'RUNNING',
                'bid_deadline': auction.bid_deadline.isoformat() + "Z"
            }, to=room, namespace="/")
        return {'success': True}
    finally:
        db.close()

@socketio.on('admin_stop_auction')
def handle_admin_stop_auction(data):
    auction_id = data.get('auction_id')
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if auction:
            auction.status = 'stopped'
            auction.bid_deadline = None
            db.commit()
            
            room = f"auction_{auction_id}"
            emit('auction_update', {
                'status': 'STOPPED',
                'bid_deadline': None
            }, to=room, namespace="/")
        return {'success': True}
    finally:
        db.close()

@socketio.on('admin_next_player')
def handle_admin_next_player(data):
    auction_id = data.get('auction_id')
    if not auction_id:
        return {'error': 'Missing auction_id'}
    
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if not auction:
            return {'error': 'Auction not found'}
            
        event_id = auction.event_id
        
        # Get auctioned player IDs
        auctioned_player_ids_q = db.query(models.AuctionPlayer.player_id).filter(
            models.AuctionPlayer.auction_id == auction_id,
            models.AuctionPlayer.status.in_(['SOLD', 'UNSOLD'])
        ).distinct()
        auctioned_player_ids = [r[0] for r in auctioned_player_ids_q.all()]

        # Find first PENDING player from auction_players
        next_ap = db.query(models.AuctionPlayer).filter(
            models.AuctionPlayer.auction_id == auction_id,
            models.AuctionPlayer.status == 'PENDING',
            ~models.AuctionPlayer.player_id.in_(auctioned_player_ids)
        ).order_by(models.AuctionPlayer.auction_order).first()

        room = f"auction_{auction_id}"
        if next_ap:
            next_player = next_ap.player
            auction.current_player_id = next_player.player_id
            now = datetime.utcnow()
            auction.current_player_bid_start = now
            auction.bid_deadline = now + timedelta(seconds=20)
            auction.current_bid_amount = next_ap.base_price
            
            next_ap.started_at = now
            db.commit()
            
            emit('auction_update', {
                'status': 'RUNNING' if auction.status == 'in_progress' else auction.status.upper(),
                'current_player': {
                    'id': next_player.player_id,
                    'name': next_player.full_name,
                    'role': getattr(next_player, 'bio', 'Player'),
                    'category': 'Standard',
                    'base_price': next_ap.base_price,
                    'photo': getattr(next_player, 'profile_image_url', None)
                },
                'current_bid': auction.current_bid_amount,
                'bid_deadline': auction.bid_deadline.isoformat() + "Z" if auction.bid_deadline else None
            }, to=room, namespace="/")
        else:
            auction.status = 'completed'
            db.commit()
            emit('auction_update', {'status': 'COMPLETED'}, to=room)
            
        return {'success': True}
    except Exception as e:
        logger.error(f"Error next player: {e}")
        return {'error': str(e)}
    finally:
        db.close()


@socketio.on('place_bid')
def handle_place_bid(data):
    auction_id = data.get('auction_id')
    team_id = data.get('team_id')
    try:
        amount = float(data.get('amount'))
    except (TypeError, ValueError):
        return {'error': 'Invalid bid amount'}
    
    if not all([auction_id, team_id, amount]):
        return {'error': 'Missing parameters'}
        
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).with_for_update().first()
        if not auction or auction.status != 'in_progress':
            return {'error': 'Auction not active'}
            
        # Concurrency protection: atomicity
        if amount <= auction.current_bid_amount:
            return {'error': 'Bid must be higher than current bid'}
            
        min_increment = float(auction.min_bid_increment) if auction.min_bid_increment else 0
        if amount < float(auction.current_bid_amount) + min_increment:
            return {'error': f'Minimum increment is {min_increment}'}
            
        # Get the active AuctionPlayer
        current_ap = db.query(models.AuctionPlayer).filter(
            models.AuctionPlayer.auction_id == auction_id,
            models.AuctionPlayer.player_id == auction.current_player_id
        ).order_by(models.AuctionPlayer.auction_player_id.desc()).first()
        
        ap_id = current_ap.auction_player_id if current_ap else None

        if not ap_id:
            return {'error': 'No active player in auction'}

        # Enforce first bidder rule (alphabetical)
        existing_bid_count = db.query(models.AuctionBid).filter(
            models.AuctionBid.auction_player_id == ap_id
        ).count()
        
        if existing_bid_count == 0:
            teams = db.query(models.Team).filter(
                models.Team.event_id == auction.event_id,
                models.Team.status.in_(['active', 'pending', 'inactive'])
            ).all()
            teams.sort(key=lambda t: (t.team_name or "").lower())
            first_bidder_team = teams[0] if teams else None
            
            if first_bidder_team and str(first_bidder_team.team_id) != str(team_id):
                return {'error': f'The first bid must be placed by {first_bidder_team.team_name}'}

        # Ensure team has sufficient purse
        team = db.query(models.Team).filter(models.Team.team_id == team_id).first()
        if not team or not team.owner:
            return {'error': 'Team or owner not found'}
            
        team_status = db.query(models.AuctionTeamStatus).filter(
            models.AuctionTeamStatus.auction_id == auction_id,
            models.AuctionTeamStatus.team_id == team_id
        ).first()
        
        spent = float(team_status.spent_budget or 0) if team_status else 0
        wallet_balance = float(team.owner.wallet_balance or 0)
        
        if (wallet_balance - spent) < amount:
            return {'error': 'Insufficient purse remaining'}

        # Record the bid
        bid = models.AuctionBid(
            auction_id=auction_id,
            auction_player_id=ap_id,
            team_id=team_id,
            bid_amount=amount
        )
        db.add(bid)
        
        # Extend timer by exactly 20 seconds from now
        now = datetime.utcnow()
        deadline = now + timedelta(seconds=20)
        auction.current_player_bid_start = now
        auction.bid_deadline = deadline
        auction.current_bid_amount = amount
        db.commit()
        
        room = f"auction_{auction_id}"
        emit('bid_placed', {
            'team_id': team_id,
            'amount': amount,
            'bid_deadline': deadline.isoformat() + "Z"
        }, to=room, namespace="/")
        
        return {'success': True}
    except Exception as e:
        db.rollback()
        logger.error(f"Error placing bid: {e}")
        return {'error': 'Internal server error'}
    finally:
        db.close()

@socketio.on('admin_mark_sold')
def handle_admin_mark_sold(data):
    auction_id = data.get('auction_id')
    if not auction_id:
        return {'error': 'Missing auction_id'}

    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if not auction or not auction.current_player_id:
            return {'error': 'No active player in auction'}

        current_ap = db.query(models.AuctionPlayer).filter(
            models.AuctionPlayer.auction_id == auction_id,
            models.AuctionPlayer.player_id == auction.current_player_id
        ).order_by(models.AuctionPlayer.auction_player_id.desc()).first()

        if not current_ap:
            return {'error': 'Active player record not found'}

        # Get highest bid
        highest_bid = db.query(models.AuctionBid).filter(
            models.AuctionBid.auction_player_id == current_ap.auction_player_id
        ).order_by(models.AuctionBid.bid_amount.desc()).first()

        if highest_bid:
            current_ap.status = 'SOLD'
            current_ap.sold_to_team_id = highest_bid.team_id
            current_ap.final_price = highest_bid.bid_amount
            current_ap.ended_at = datetime.utcnow()
            
            # Deduct from team budget
            team_status = db.query(models.AuctionTeamStatus).filter(
                models.AuctionTeamStatus.auction_id == auction_id,
                models.AuctionTeamStatus.team_id == highest_bid.team_id
            ).first()
            if team_status:
                team_status.spent_budget = float(team_status.spent_budget or 0) + float(highest_bid.bid_amount)
                
            # Physically deduct from owner's wallet to enforce persistence
            team = db.query(models.Team).filter(models.Team.team_id == highest_bid.team_id).first()
            if team and team.owner:
                team.owner.wallet_balance = float(team.owner.wallet_balance or 0) - float(highest_bid.bid_amount)
                
            db.commit()
            room = f"auction_{auction_id}"
            emit('player_sold', {
                'player_id': current_ap.player_id,
                'team_id': highest_bid.team_id,
                'amount': highest_bid.bid_amount
            }, to=room)
        else:
            return {'error': 'No bids placed'}
        
        return {'success': True}
    except Exception as e:
        logger.error(f"Error marking sold: {e}")
        return {'error': str(e)}
    finally:
        db.close()

@socketio.on('admin_mark_unsold')
def handle_admin_mark_unsold(data):
    auction_id = data.get('auction_id')
    if not auction_id:
        return {'error': 'Missing auction_id'}

    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if not auction or not auction.current_player_id:
            return {'error': 'No active player in auction'}

        current_ap = db.query(models.AuctionPlayer).filter(
            models.AuctionPlayer.auction_id == auction_id,
            models.AuctionPlayer.player_id == auction.current_player_id
        ).order_by(models.AuctionPlayer.auction_player_id.desc()).first()

        if current_ap:
            current_ap.status = 'UNSOLD'
            current_ap.ended_at = datetime.utcnow()
            db.commit()
            
            room = f"auction_{auction_id}"
            emit('player_unsold', {
                'player_id': current_ap.player_id
            }, to=room)
            
        return {'success': True}
    except Exception as e:
        logger.error(f"Error marking unsold: {e}")
        return {'error': str(e)}
    finally:
        db.close()

@socketio.on('timer_expired')
def handle_timer_expired(data):
    auction_id = data.get('auction_id')
    if not auction_id:
        return {'error': 'Missing auction_id'}

    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.auction_id == auction_id).first()
        if not auction or auction.status != 'in_progress':
            return {'error': 'Auction not active'}
            
        if not auction.bid_deadline:
            return {'error': 'No active deadline'}
            
        # Verify that time actually expired
        now = datetime.utcnow()
        if now < auction.bid_deadline:
            return {'error': 'Timer has not expired yet on server'}

        current_ap = db.query(models.AuctionPlayer).filter(
            models.AuctionPlayer.auction_id == auction_id,
            models.AuctionPlayer.player_id == auction.current_player_id
        ).order_by(models.AuctionPlayer.auction_player_id.desc()).first()

        if not current_ap:
            return {'error': 'Active player record not found'}

        # Get highest bid
        highest_bid = db.query(models.AuctionBid).filter(
            models.AuctionBid.auction_player_id == current_ap.auction_player_id
        ).order_by(models.AuctionBid.bid_amount.desc()).first()

        room = f"auction_{auction_id}"

        if highest_bid:
            current_ap.status = 'SOLD'
            current_ap.sold_to_team_id = highest_bid.team_id
            current_ap.final_price = highest_bid.bid_amount
            current_ap.ended_at = now
            
            team_status = db.query(models.AuctionTeamStatus).filter(
                models.AuctionTeamStatus.auction_id == auction_id,
                models.AuctionTeamStatus.team_id == highest_bid.team_id
            ).first()
            if team_status:
                team_status.spent_budget = float(team_status.spent_budget or 0) + float(highest_bid.bid_amount)
                
            team = db.query(models.Team).filter(models.Team.team_id == highest_bid.team_id).first()
            if team and team.owner:
                team.owner.wallet_balance = float(team.owner.wallet_balance or 0) - float(highest_bid.bid_amount)
                
            db.commit()
            emit('player_sold', {
                'player_id': current_ap.player_id,
                'team_id': highest_bid.team_id,
                'amount': highest_bid.bid_amount
            }, to=room)
        else:
            current_ap.status = 'UNSOLD'
            current_ap.ended_at = now
            db.commit()
            emit('player_unsold', {
                'player_id': current_ap.player_id
            }, to=room)
            
        # Automatically advance to next player
        handle_admin_next_player({'auction_id': auction_id})
        
        return {'success': True}
    except Exception as e:
        logger.error(f"Error handling timer expired: {e}")
        return {'error': str(e)}
    finally:
        db.close()


@app.route("/api/player/skills", methods=['PUT'])
def api_update_player_skills():
    current_user = get_current_user()
    if getattr(current_user.user_type, "value", current_user.user_type) != 'player':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
            
    payload = request.get_json()
    if not payload:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400
        
    db = SessionLocal()
    try:
        player = db.query(models.Player).filter(models.Player.user_id == current_user.user_id).first()
        if not player:
            return jsonify({"success": False, "message": "Player not found"}), 404
            
        if 'cricket_rating' in payload: player.cricket_rating = min(10, max(1, payload.get('cricket_rating', 1)))
        if 'football_rating' in payload: player.football_rating = min(10, max(1, payload.get('football_rating', 1)))
        if 'basketball_rating' in payload: player.basketball_rating = min(10, max(1, payload.get('basketball_rating', 1)))
        
        db.commit()
        return jsonify({"success": True, "message": "Skills updated successfully"})
    finally:
        db.close()

@app.route("/api/player/achievements", methods=['PUT'])
def api_update_player_achievements():
    current_user = get_current_user()
    if getattr(current_user.user_type, "value", current_user.user_type) != 'player':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
            
    payload = request.get_json()
    if not payload:
        return jsonify({"success": False, "message": "Invalid JSON"}), 400
        
    db = SessionLocal()
    try:
        player = db.query(models.Player).filter(models.Player.user_id == current_user.user_id).first()
        if not player:
            return jsonify({"success": False, "message": "Player not found"}), 404
            
        if 'tournaments_won' in payload: player.tournaments_won = payload['tournaments_won']
        if 'mvp_awards' in payload: player.mvp_awards = payload['mvp_awards']
        if 'best_player_awards' in payload: player.best_player_awards = payload['best_player_awards']
        if 'professional_contracts' in payload: player.professional_contracts = payload['professional_contracts']
        if 'state_level_champion' in payload: player.state_level_champion = payload['state_level_champion']
        if 'international_experience' in payload: player.international_experience = payload['international_experience']
        
        db.commit()
        return jsonify({"success": True, "message": "Achievements updated successfully"})
    finally:
        db.close()

# ==============================================================================
# NEW LIVE AUCTION API ROUTES
# ==============================================================================

@app.route("/api/events/<int:event_id>/auction", methods=['GET'])
def api_get_auction_full(event_id):
    db = SessionLocal()
    try:
        event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
        if not event:
            return jsonify({"success": False, "message": "Event not found"}), 404
            
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        
        teams = db.query(models.Team).filter(models.Team.event_id == event_id).all()
        teams_data = []
        for t in sorted(teams, key=lambda x: x.team_name.lower()):
            teams_data.append({
                "id": t.team_id,
                "name": t.team_name,
                "purse": float(t.owner.wallet_balance) if t.owner and t.owner.wallet_balance else 0.0,
                "players_count": t.current_players if t.current_players else 0,
                "order": len(teams_data) + 1,
                "team_name": t.team_name
            })
            
        timer = 0
        if auction and auction.status == 'RUNNING' and auction.bid_deadline:
            timer = max(0, (auction.bid_deadline - datetime.utcnow()).total_seconds())
        elif auction and auction.status == 'PAUSED' and auction.paused_time_left:
            timer = float(auction.paused_time_left)

        auction_data = {
            "status": auction.status if auction else "NOT_STARTED",
            "current_player_id": auction.current_player_id if auction else None,
            "current_bid": float(auction.current_bid_amount) if auction else 0.0,
            "current_team_id": auction.current_team_id if auction else None,
            "timer": timer,
            "timer_duration": 30
        }

        return jsonify({
            "success": True,
            "event": {"id": event.event_id, "name": event.title, "status": event.status},
            "auction": auction_data,
            "teams": teams_data
        })
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/auction/state", methods=['GET'])
def api_get_auction_state(event_id):
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        if not auction:
            return jsonify({"success": False, "message": "Auction not found"}), 404
            
        timer = 0
        if auction.status == 'RUNNING' and auction.bid_deadline:
            timer = max(0, (auction.bid_deadline - datetime.utcnow()).total_seconds())
        elif auction.status == 'PAUSED' and auction.paused_time_left:
            timer = float(auction.paused_time_left)

        return jsonify({
            "success": True,
            "status": auction.status,
            "current_player_id": auction.current_player_id,
            "current_bid": float(auction.current_bid_amount),
            "current_team_id": auction.current_team_id,
            "timer": timer,
            "bid_deadline": auction.bid_deadline.isoformat() + "Z" if auction.bid_deadline else None
        })
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/auction/start", methods=['POST'])
def api_auction_start(event_id):
    current_user = get_current_user()
    if not current_user or getattr(current_user.user_type, 'value', current_user.user_type) != 'admin':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        if not auction:
            return jsonify({"success": False, "message": "Auction not found"}), 404
            
        auction.status = 'RUNNING'
        if auction.paused_time_left is not None:
             auction.bid_deadline = datetime.utcnow() + timedelta(seconds=float(auction.paused_time_left))
             auction.paused_time_left = None
        db.commit()
        
        emit('auction_started', {'status': 'RUNNING', 'event_id': event_id}, to=f"auction_{event_id}", namespace='/')
        return jsonify({"success": True, "message": "Auction started"})
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/auction/pause", methods=['POST'])
def api_auction_pause(event_id):
    current_user = get_current_user()
    if not current_user or getattr(current_user.user_type, 'value', current_user.user_type) != 'admin':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        if not auction or auction.status != 'RUNNING':
            return jsonify({"success": False, "message": "Cannot pause"}), 400
            
        auction.status = 'PAUSED'
        if auction.bid_deadline:
            time_left = (auction.bid_deadline - datetime.utcnow()).total_seconds()
            auction.paused_time_left = max(0.0, time_left)
            
        db.commit()
        
        emit('auction_paused', {'status': 'PAUSED', 'time_left': float(auction.paused_time_left or 0)}, to=f"auction_{event_id}", namespace='/')
        return jsonify({"success": True})
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/auction/resume", methods=['POST'])
def api_auction_resume(event_id):
    current_user = get_current_user()
    if not current_user or getattr(current_user.user_type, 'value', current_user.user_type) != 'admin':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        if not auction or auction.status != 'PAUSED':
            return jsonify({"success": False, "message": "Cannot resume"}), 400
            
        auction.status = 'RUNNING'
        if auction.paused_time_left is not None:
            auction.bid_deadline = datetime.utcnow() + timedelta(seconds=float(auction.paused_time_left))
            auction.paused_time_left = None
            
        db.commit()
        
        emit('auction_resumed', {
            'status': 'RUNNING',
            'bid_deadline': auction.bid_deadline.isoformat() + "Z" if auction.bid_deadline else None
        }, to=f"auction_{event_id}", namespace='/')
        return jsonify({"success": True})
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/auction/stop", methods=['POST'])
def api_auction_stop(event_id):
    current_user = get_current_user()
    if not current_user or getattr(current_user.user_type, 'value', current_user.user_type) != 'admin':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        if not auction:
            return jsonify({"success": False}), 404
            
        auction.status = 'STOPPED'
        auction.bid_deadline = None
        db.commit()
        
        emit('auction_stopped', {'status': 'STOPPED'}, to=f"auction_{event_id}", namespace='/')
        return jsonify({"success": True})
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/auction/player/start", methods=['POST'])
def api_auction_player_start(event_id):
    current_user = get_current_user()
    if not current_user or getattr(current_user.user_type, 'value', current_user.user_type) != 'admin':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    payload = request.get_json() or {}
    player_id = payload.get('player_id')
    
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        player = db.query(models.Player).filter(models.Player.player_id == player_id).first()
        
        if not auction or not player:
            return jsonify({"success": False}), 404
            
        teams = db.query(models.Team).filter(models.Team.event_id == event_id).all()
        sorted_teams = sorted(teams, key=lambda x: x.team_name.lower())
        first_bidder = sorted_teams[0] if sorted_teams else None
            
        auction.current_player_id = player.player_id
        auction.current_bid_amount = player.base_price or 0.0
        auction.current_team_id = first_bidder.team_id if first_bidder else None
        auction.bid_deadline = datetime.utcnow() + timedelta(seconds=30)
        auction.status = 'RUNNING'
        
        db.commit()
        
        emit('player_started', {
            'player_id': player.player_id,
            'base_price': float(auction.current_bid_amount),
            'bid_deadline': auction.bid_deadline.isoformat() + "Z"
        }, to=f"auction_{event_id}", namespace='/')
        return jsonify({"success": True})
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/auction/bid", methods=['POST'])
def api_auction_bid(event_id):
    current_user = get_current_user()
    payload = request.get_json() or {}
    team_id = payload.get('team_id')
    amount = payload.get('amount')
    
    if not team_id or not amount:
        return jsonify({"success": False, "message": "Invalid bid"}), 400
        
    db = SessionLocal()
    try:
        if engine.dialect.name == 'sqlite':
            auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        else:
            auction = db.query(models.Auction).with_for_update().filter(models.Auction.event_id == event_id).first()
            
        team = db.query(models.Team).filter(models.Team.team_id == team_id).first()
        
        if not auction or auction.status != 'RUNNING':
            return jsonify({"success": False, "message": "Auction not running"}), 400
            
        if amount <= auction.current_bid_amount:
            return jsonify({"success": False, "message": "Bid must be higher"}), 400
            
        if team.current_purse and amount > team.current_purse:
            return jsonify({"success": False, "message": "Insufficient purse"}), 400
            
        auction.current_bid_amount = amount
        auction.current_team_id = team.team_id
        auction.bid_deadline = datetime.utcnow() + timedelta(seconds=30)
        
        db.commit()
        
        emit('bid_placed', {
            'current_bid': float(amount),
            'current_team_id': team.team_id,
            'bid_deadline': auction.bid_deadline.isoformat() + "Z"
        }, to=f"auction_{event_id}", namespace='/')
        return jsonify({"success": True})
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/auction/player/sell", methods=['POST'])
def api_auction_player_sell(event_id):
    current_user = get_current_user()
    if not current_user or getattr(current_user.user_type, 'value', current_user.user_type) != 'admin':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        if not auction or not auction.current_player_id or not auction.current_team_id:
            return jsonify({"success": False}), 400
            
        team = db.query(models.Team).filter(models.Team.team_id == auction.current_team_id).first()
        if team:
            if team.owner:
                team.owner.wallet_balance = float(team.owner.wallet_balance or 0) - float(auction.current_bid_amount)
            team.current_players = (team.current_players or 0) + 1
            
        player_id = auction.current_player_id
        amount = auction.current_bid_amount
        team_id = auction.current_team_id
        
        auction.current_player_id = None
        auction.current_bid_amount = 0
        auction.current_team_id = None
        auction.status = 'PAUSED'
        
        db.commit()
        
        emit('player_sold', {
            'player_id': player_id,
            'amount': float(amount),
            'team_id': team_id,
            'purse': float(team.owner.wallet_balance) if team and team.owner else 0
        }, to=f"auction_{event_id}", namespace='/')
        return jsonify({"success": True})
    finally:
        db.close()

@app.route("/api/events/<int:event_id>/auction/player/unsold", methods=['POST'])
def api_auction_player_unsold(event_id):
    current_user = get_current_user()
    if not current_user or getattr(current_user.user_type, 'value', current_user.user_type) != 'admin':
        return jsonify({"success": False, "message": "Unauthorized"}), 403
        
    db = SessionLocal()
    try:
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        if not auction or not auction.current_player_id:
            return jsonify({"success": False}), 400
            
        player_id = auction.current_player_id
        auction.current_player_id = None
        auction.current_bid_amount = 0
        auction.current_team_id = None
        auction.status = 'PAUSED'
        
        db.commit()
        
        emit('player_unsold', {
            'player_id': player_id
        }, to=f"auction_{event_id}", namespace='/')
        return jsonify({"success": True})
    finally:
        db.close()

def background_auction_tick():
    """Background task to tick active auctions."""
    while True:
        socketio.sleep(1)
        db = SessionLocal()
        try:
            active_auctions = db.query(models.Auction).filter(
                models.Auction.status == 'RUNNING'
            ).all()
            
            now = datetime.utcnow()
            for auction in active_auctions:
                if not auction.current_player_id or not auction.bid_deadline:
                    continue
                    
                time_left = max(0, (auction.bid_deadline - now).total_seconds())
                room = f"auction_{auction.event_id}"
                
                if time_left == 0:
                    if engine.dialect.name != 'sqlite':
                        auction = db.query(models.Auction).with_for_update().filter(models.Auction.auction_id == auction.auction_id).first()
                        if auction.status != 'RUNNING':
                            continue
                            
                    # Resolve SOLD or UNSOLD
                    player_id = auction.current_player_id
                    amount = auction.current_bid_amount
                    team_id = auction.current_team_id
                    
                    teams = db.query(models.Team).filter(models.Team.event_id == auction.event_id).all()
                    sorted_teams = sorted(teams, key=lambda x: x.team_name.lower())
                    first_bidder = sorted_teams[0].team_id if sorted_teams else None
                    
                    if team_id and team_id != first_bidder and amount > 0:
                        # SOLD
                        team = db.query(models.Team).filter(models.Team.team_id == team_id).first()
                        if team:
                            if team.owner:
                                team.owner.wallet_balance = float(team.owner.wallet_balance or 0) - float(amount)
                            team.current_players = (team.current_players or 0) + 1
                        
                        socketio.emit('player_sold', {
                            'player_id': player_id,
                            'amount': float(amount),
                            'team_id': team_id,
                            'purse': float(team.owner.wallet_balance) if team and team.owner else 0
                        }, to=room, namespace='/')
                    else:
                        # UNSOLD
                        socketio.emit('player_unsold', {
                            'player_id': player_id
                        }, to=room, namespace='/')

                    # Fetch next player
                    # Simplified logic: just find any player not in auction_players or unsold. For now, pause.
                    # A robust implementation requires joining queue. Since we don't have queue models, we just PAUSE.
                    auction.current_player_id = None
                    auction.current_bid_amount = 0
                    auction.current_team_id = None
                    auction.status = 'PAUSED'
                    db.commit()
                    # We don't strictly need to emit tick every second since the client
                    # is authoritative on rendering the countdown, but we can emit sync
                    pass
        except Exception as e:
            logger.error(f"Error in background tick: {e}")
        finally:
            db.close()

# Start the background task for Passenger
socketio.start_background_task(background_auction_tick)

@app.route('/api/admin/run-migrations', methods=['GET'])
def run_migrations():
    """Temporary endpoint to safely migrate the production database scheme for missing auction columns."""
    from sqlalchemy import text
    try:
        results = []
        with engine.begin() as conn:
            # Check current_team_id
            db_name = os.getenv("DB_NAME", "")
            if not db_name:
                res = conn.execute(text("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'auctions' AND COLUMN_NAME = 'current_team_id';")).fetchall()
            else:
                res = conn.execute(text(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '{db_name}' AND TABLE_NAME = 'auctions' AND COLUMN_NAME = 'current_team_id';")).fetchall()
            if not res:
                conn.execute(text("ALTER TABLE auctions ADD COLUMN current_team_id INT NULL;"))
                try:
                    conn.execute(text("ALTER TABLE auctions ADD CONSTRAINT fk_auction_current_team FOREIGN KEY (current_team_id) REFERENCES teams(team_id) ON DELETE SET NULL;"))
                except Exception as e:
                    logger.warning(f"Failed to add constraint: {e}")
                results.append("Added current_team_id")
            
            # Check paused_time_left
            if not db_name:
                res = conn.execute(text("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'auctions' AND COLUMN_NAME = 'paused_time_left';")).fetchall()
            else:
                res = conn.execute(text(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '{db_name}' AND TABLE_NAME = 'auctions' AND COLUMN_NAME = 'paused_time_left';")).fetchall()
            if not res:
                conn.execute(text("ALTER TABLE auctions ADD COLUMN paused_time_left DECIMAL(10, 2) NULL;"))
                results.append("Added paused_time_left")
                
            # Check bid_deadline
            if not db_name:
                res = conn.execute(text("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'auctions' AND COLUMN_NAME = 'bid_deadline';")).fetchall()
            else:
                res = conn.execute(text(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '{db_name}' AND TABLE_NAME = 'auctions' AND COLUMN_NAME = 'bid_deadline';")).fetchall()
            if not res:
                conn.execute(text("ALTER TABLE auctions ADD COLUMN bid_deadline DATETIME NULL;"))
                results.append("Added bid_deadline")
                
        return jsonify({"success": True, "results": results, "message": "Migration completed"})
    except Exception as e:
        logger.error(f"Migration error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/db-inspect', methods=['GET'])
def db_inspect():
    """Endpoint to inspect the database connection and schema on the live server."""
    from sqlalchemy import text
    try:
        results = {}
        with engine.begin() as conn:
            # 1. SELECT DATABASE()
            res = conn.execute(text("SELECT DATABASE();")).scalar()
            results["database_name"] = res
            
            # 2. SELECT @@hostname
            res = conn.execute(text("SELECT @@hostname;")).scalar()
            results["hostname"] = res
            
            # 3. SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE FROM information_schema.COLUMNS
            res = conn.execute(text("""
                SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = 'auctions' 
                AND COLUMN_NAME IN ('current_team_id', 'bid_deadline', 'paused_time_left');
            """)).fetchall()
            results["columns"] = [dict(row._mapping) for row in res]
            
            # 4. SHOW CREATE TABLE auctions
            res = conn.execute(text("SHOW CREATE TABLE auctions;")).fetchone()
            results["show_create_table"] = dict(res._mapping) if res else None
            
            # 5. Direct SQLAlchemy query
            try:
                res = conn.execute(text("SELECT current_team_id, bid_deadline, paused_time_left FROM auctions LIMIT 1;")).fetchone()
                results["direct_query_success"] = True
                results["direct_query_row"] = dict(res._mapping) if res else None
            except Exception as e:
                results["direct_query_success"] = False
                results["direct_query_error"] = str(e)
                
            # 6. Check environment variables loaded
            results["env_db_host"] = os.getenv("DB_HOST")
            results["env_db_name"] = os.getenv("DB_NAME")
            results["env_db_user"] = os.getenv("DB_USER")
            
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Local development only — Passenger imports `app` and never hits this block
application=app
if __name__ == "__main__":
    print("Starting development server...")
    initialize_database()
    try:
        from auction_engine import start_auction_engine
        start_auction_engine()
        print("Auction engine started successfully")
    except Exception as e:
        print(f"Error starting auction engine: {e}")

    socketio.run(
        app,
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', 8000)),
        debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true',
        allow_unsafe_werkzeug=True
    )

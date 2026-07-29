import sys
import os
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union

from werkzeug.exceptions import HTTPException
from flask import Flask, request, jsonify, abort, send_from_directory, render_template, make_response, session, send_file, redirect
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from sqlalchemy.exc import SQLAlchemyError
from passlib.context import CryptContext
import bcrypt

from database import Base, engine, SessionLocal
import models
import schemas
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, EmailStr, validator, Field
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

load_dotenv()

# Pydantic Settings
class Settings(BaseSettings):
    # App Configuration
    app_name: str = "Sports Auction Platform API"
    
    # Security
    secret_key: str = "your-secret-key-here"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # Database
    database_url: str = "sqlite:///./app.db"
    
    # Environment
    environment: str = "development"
    debug: bool = True
    
    # CORS (will be ignored as per user request)
    cors_origins: str = ""
    
    # Session
    session_cookie_name: str = "session_token"
    session_expire_minutes: int = 60 * 24 * 7  # 7 days
    
    # Pydantic v2 config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra='ignore',  # Ignore extra fields in .env that aren't defined here
        case_sensitive=True,  # Make it case-sensitive to match the .env file exactly
        env_prefix='',  # No prefix for env vars
    )

# Create settings instance
settings = Settings()

# Initialize database tables on startup
def initialize_database():
    print("Initializing database...")
    try:
        # Test database connection first
        with engine.connect() as conn:
            print("Successfully connected to MySQL database")
        
        # Create all tables
        print("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("Database tables initialized successfully in MySQL!")
        return True
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error initializing database: {e}", file=sys.stderr)
        print("Please ensure MySQL server is running and the database 'bidzone' exists")
        print(f"You can create it with: CREATE DATABASE IF NOT EXISTS bidzone;")
        return False

# Call the initialization function when the module loads
# Database initialization moved to main startup to prevent contention during reloads
# initialize_database()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app with minimal settings
app = Flask(__name__, 
            template_folder='../frontend/templates',
            static_folder='../frontend/static')

# Custom error handler to return JSON instead of HTML
@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(500)
def handle_error(error):
    """Return JSON error responses instead of HTML"""
    response = {
        "error": error.name,
        "message": error.description if hasattr(error, 'description') else str(error),
        "status_code": error.code
    }
    return jsonify(response), error.code

@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """Handle unexpected errors and return JSON"""
    logger.error(f"Unexpected error: {str(error)}")
    response = {
        "error": "Internal Server Error",
        "message": "An unexpected error occurred. Please try again later.",
        "status_code": 500
    }
    return jsonify(response), 500

# Configure Flask app
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "dev-secret-key-1234567890")
app.config['SESSION_COOKIE_NAME'] = "session_token"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=60 * 24 * 7)  # 7 days

# Security configuration
# For development only - in production, use a proper secret key from environment variables
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-1234567890")
    
SESSION_COOKIE_NAME = "session_token"

# Password hashing configuration
pwd_context = CryptContext(
    schemes=["bcrypt"],
    default="bcrypt",
    bcrypt__rounds=12,
    deprecated="auto"
)

# Helper function to create session in database
from auction_engine import start_auction_engine

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

# Get the base directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
TEMPLATES_DIR = os.path.join(FRONTEND_DIR, 'templates')
STATIC_DIR = os.path.join(FRONTEND_DIR, 'static')
CSS_DIR = os.path.join(FRONTEND_DIR, 'css')
JS_DIR = os.path.join(FRONTEND_DIR, 'js')

# Create static directory if it doesn't exist
os.makedirs(STATIC_DIR, exist_ok=True)

# Flask static routes
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)

@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(CSS_DIR, filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(JS_DIR, filename)

# Models are imported from schemas.py
# Endpoints are consolidated below


@app.route("/api/users/<int:user_id>")
def get_user_full_details(user_id: int):
    """Get full details of a user (including player/team owner info)"""
    from sqlalchemy.orm import joinedload
    
    db = SessionLocal()
    try:
        # Eager load player relationships to avoid DetachedInstanceError
        user_obj = db.query(models.User).options(
            joinedload(models.User.player).joinedload(models.Player.skill_ratings).joinedload(models.PlayerSkillRating.skill).joinedload(models.PlayerSkill.sport)
        ).filter(models.User.user_id == user_id).first()
        
        if not user_obj:
            return jsonify({"success": False, "message": "User not found"}), 404
            
        user_data = {
            "user_id": user_obj.user_id,
            "username": user_obj.username,
            "email": user_obj.email,
            "phone": user_obj.phone,
            "user_type": user_obj.user_type,
            "created_at": user_obj.created_at,
            "is_active": user_obj.is_active,
            "is_verified": user_obj.is_verified,
            "last_login": user_obj.last_login
        }
        
        # Enrich with Team Owner details
        if user_obj.user_type == models.UserType.team_owner and user_obj.team_owner:
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
        elif user_obj.user_type == models.UserType.player and user_obj.player:
            player = user_obj.player
            user_data.update({
                "player_id": player.player_id,
                "first_name": player.first_name,
                "last_name": player.last_name,
                "date_of_birth": player.date_of_birth,
                "gender": player.gender,
                "profile_image_url": player.profile_image_url,
                "bio": player.bio,
                "address": player.address,
                "city": player.city,
                "state": player.state,
                "country": player.country,
                "pincode": player.pincode,
                "height_cm": player.height_cm,
                "weight_kg": player.weight_kg,
            })
            
            # Get all sports ratings dynamically
            sports_skills = []
            for rating in player.skill_ratings:
                sports_skills.append({
                    "sport_id": rating.skill.sport.sport_id,
                    "sport_name": rating.skill.sport.name,
                    "skill_name": rating.skill.skill_name,
                    "rating": rating.rating
                })
            
            user_data.update({
                "sports_skills": sports_skills,
                "basketball_rating": next((r.rating for r in player.skill_ratings if r.skill.sport.name.lower() == "basketball"), getattr(player, "basketball_rating", None)),
                "football_rating": next((r.rating for r in player.skill_ratings if r.skill.sport.name.lower() == "football"), getattr(player, "football_rating", None)),
                "cricket_rating": next((r.rating for r in player.skill_ratings if r.skill.sport.name.lower() == "cricket"), getattr(player, "cricket_rating", None))
            })

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
                
            return jsonify({
                "team_id": team.team_id if team else None,
                "username": current_user.username,
                "wallet_balance": float(team_owner.wallet_balance) if team_owner.wallet_balance else 0,
                "team_name": team_name,
                "squad": squad_data,
                "active_auction": active_auction_data,
                "participating_players": participating_players,
                "my_teams": my_teams
            })
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        abort(500, description=str(e))

# Auction endpoints
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

# Initialize CPU monitoring (first call returns 0, so we call it once at startup)
try:
    psutil.cpu_percent(interval=0.1)
except:
    pass

@app.route("/api/system-stats", methods=['GET'])
def get_system_stats():
    """
    Get real-time system statistics including CPU, RAM, and bandwidth usage.
    
    Returns:
        dict: System statistics including:
            - cpu_percent: CPU usage percentage
            - ram_used_gb: RAM used in GB
            - ram_total_gb: Total RAM in GB
            - ram_percent: RAM usage percentage
            - bandwidth_sent_mb: Total bandwidth sent in MB
            - bandwidth_recv_mb: Total bandwidth received in MB
            - bandwidth_sent_rate_mbps: Current send rate in Mbps
            - bandwidth_recv_rate_mbps: Current receive rate in Mbps
    """
    global _initial_net_io, _last_net_io_time
    
    try:
        # Get CPU usage (non-blocking)
        cpu_percent = psutil.cpu_percent(interval=None)
        
        # Get RAM usage
        ram = psutil.virtual_memory()
        ram_used_gb = ram.used / (1024 ** 3)  # Convert to GB
        ram_total_gb = ram.total / (1024 ** 3)  # Convert to GB
        ram_percent = ram.percent
        
        # Get network I/O statistics
        net_io = psutil.net_io_counters()
        current_time = time.time()
        
        # Initialize on first call
        if _initial_net_io is None:
            _initial_net_io = net_io
            _last_net_io_time = current_time
        
        # Calculate bandwidth rates (bytes per second)
        time_delta = current_time - _last_net_io_time if _last_net_io_time else 1
        
        # Prevent division by zero
        if time_delta == 0:
            time_delta = 0.001  # Use 1ms minimum
        
        # Calculate rates in Mbps
        bytes_sent_delta = net_io.bytes_sent - _initial_net_io.bytes_sent
        bytes_recv_delta = net_io.bytes_recv - _initial_net_io.bytes_recv
        
        # Update for next calculation
        _initial_net_io = net_io
        _last_net_io_time = current_time
        
        # Convert to MB and Mbps
        bandwidth_sent_mb = net_io.bytes_sent / (1024 ** 2)
        bandwidth_recv_mb = net_io.bytes_recv / (1024 ** 2)
        
        # Calculate current rates (Mbps)
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
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching system stats: {str(e)}")
        abort(500, description=f"Error fetching system statistics: {str(e)}")

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
            "redirect_to": "/team-owner-dashboard.html",
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
        
        is_production = os.getenv("ENVIRONMENT", "development") == "production"
        
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
        'admin': '/admin/dashboard',
        'team_manager': '/team-owner-dashboard.html',
        'team_analyst': '/team-owner-dashboard.html',
        'team_owner': '/team-owner-dashboard.html',
        'player': '/player-dashboard.html',
        'user': '/player-dashboard.html'
    }
    return redirect_map.get(role, '/dashboard')


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
        is_production = os.getenv("ENVIRONMENT", "development") == "production"
        
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
            secure=is_production,
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
        from sqlalchemy.orm import joinedload
        query = query.options(
            joinedload(models.User.player).joinedload(models.Player.events),
            joinedload(models.User.player).joinedload(models.Player.skill_ratings).joinedload(models.PlayerSkillRating.skill).joinedload(models.PlayerSkill.sport),
            joinedload(models.User.team_owner).joinedload(models.TeamOwner.teams)
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
            is_active=True,
            is_verified=False
        )
        logger.info("Creating player profile")
        db.add(player_profile)
        db.flush()
        logger.info(f"Player profile created with ID: {player_profile.player_id}")
        
        # Re-fetch the event since it was expired by rollback/commit
        event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
        if not event:
            db.rollback()
            abort(400, description="Event no longer exists")
            
        # Link to event
        player_profile.events.append(event)
        logger.info(f"Linked player to event ID: {event_id}")

        
        # Atomic update for participant count to prevent race conditions and excessive locking
        # This will fail if max_participants is reached between check and update
        stmt = (
            models.Event.__table__.update()
            .where(models.Event.event_id == event_id)
            .where(or_(models.Event.max_participants == None, models.Event.current_participants < models.Event.max_participants))
            .values(current_participants=models.Event.current_participants + 1)
        )

        result = db.execute(stmt)
        if result.rowcount == 0:
            # Check if it failed because it's full or doesn't exist
            db.rollback()
            abort(400, description="Event is full or no longer available")

        
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
        user_to_approve.password_hash = get_password_hash(approval_data.get('password'))
        user_to_approve.is_active = True
        user_to_approve.is_verified = True
        
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
        if current_user.user_type != "admin":
            if hasattr(current_user.user_type, 'value'):
                 if current_user.user_type.value != "admin":
                     return jsonify({"success": False, "message": "Only admins can delete users"}), 403
            else:
                 return jsonify({"success": False, "message": "Only admins can delete users"}), 403
        
        # Get user to delete
        user_to_delete = db.query(models.User).filter(models.User.user_id == user_id).first()
        if not user_to_delete:
            return jsonify({"success": False, "message": "User not found"}), 404
        
        # Count staff members that will be cascade deleted
        deleted_staff_count = db.query(models.User).filter(
            models.User.parent_user_id == user_id
        ).count()
        
        # Log activity before deletion
        try:
            log_activity(
                db=db, 
                user_id=current_user.user_id, 
                action_type="USER_DELETED", 
                action_description=f"Deleted user {user_to_delete.username} (ID: {user_id})", 
                entity_type="user", 
                entity_id=user_id
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to log deletion activity: {e}")
        
        # Delete user (cascade will handle related records due to foreign key constraints)
        db.delete(user_to_delete)
        db.commit()
        
        return jsonify({
            "success": True,
            "message": "User deleted successfully",
            "deleted_staff_count": deleted_staff_count
        })
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting user: {e}")
        return jsonify({"success": False, "message": f"Error deleting user: {str(e)}"}), 500
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
                
                # Create the user
                db_user = models.User(
                    username=user_data['username'],
                    email=user_data['email'],
                    phone=user_data.get('phone', ''),
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
                     event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
                     if event:
                         # Check if event is full (Teams)
                         if event.max_teams and len(event.teams) >= event.max_teams:
                             logger.warning(f"Registration failed - Event is full (Max Teams): {event.title}")
                             return jsonify({"success": False, "message": f"Registration closed for {event.title}. Max teams limit reached. Please contact admin."}), 400

                         # Check if event is full (Participants)
                         if event.max_participants and event.current_participants >= event.max_participants:
                             logger.warning(f"Registration failed - Event is full (Max Participants): {event.title}")
                             return jsonify({"success": False, "message": f"Registration closed for {event.title}. Participant limit reached. Please contact admin."}), 400
                        
                         # Increment current_participants
                         event.current_participants += 1
                         db.add(event)

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
                            
                            # Create staff user (Team Manager)
                            manager_user = models.User(
                                username=team_manager_email.split('@')[0][:30],  # Temporary username
                                email=team_manager_email,
                                phone='',
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
                        logger.error(f"Error creating Team Manager invitation: {str(e)}")
                
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
                            
                            # Create staff user (Team Analyst)
                            analyst_user = models.User(
                                username=team_analyst_email.split('@')[0][:30],  # Temporary username
                                email=team_analyst_email,
                                phone='',
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
                        logger.error(f"Error creating Team Analyst invitation: {str(e)}")

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

# Consolidated Event Management Endpoints




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
        
        return jsonify([{
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
        } for event in events])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching events: {str(e)}")
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
        return jsonify([{
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
        } for event in events])
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

        # Create new event
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
            creator_id=current_user.user_id
        )
        
        db.add(new_event)
        db.flush() # Get the event_id

        # Handle sports
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


# DELETE event
@app.route("/events/<int:event_id>", methods=['DELETE'])
def delete_event(event_id: int):
    """
    Delete an event. Only admins can delete events.
    """
    current_user = get_current_user()
    db = SessionLocal()
    
    # Check if user is admin
    if current_user.user_type != models.UserType.admin:
        return jsonify({"success": False, "message": "Only admins can delete events"}), 403
    
    event = db.query(models.Event).filter(models.Event.event_id == event_id).first()
    if not event:
        return jsonify({"success": False, "message": "Event not found"}), 404
    
    try:
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
        
        # Log activity
        log_activity(db, current_user.user_id, "EVENT_DELETED", f"Deleted event {event.title} and {len(users_to_delete)} associated users", "event", event_id)
        
        # Delete event
        db.delete(event)
        
        # Delete associated users
        if users_to_delete:
            db.query(models.User).filter(models.User.user_id.in_(users_to_delete)).delete(synchronize_session=False)
            
        db.commit()
        return jsonify({"success": True, "message": "Event and associated users deleted successfully"})
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting event: {str(e)}")
        return jsonify({"success": False, "message": f"Error deleting event: {str(e)}"}), 500
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
        # Get all players registered for this event, ordered by registration time
        from models import player_events
        registered_players = db.query(player_events).filter(
            player_events.c.event_id == event_id
        ).order_by(player_events.c.registered_at).all()
        
        # Apply max_players limit if set
        if event.max_players:
            registered_players = registered_players[:event.max_players]
        
        added_count = len(registered_players)
        
        return jsonify({
            "message": f"Successfully added {added_count} players to event",
            "added_count": added_count,
            "max_players": event.max_players
        })
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
        # Get all teams registered for this event, ordered by creation time
        teams = db.query(models.Team).filter(
            models.Team.event_id == event_id
        ).order_by(models.Team.created_at).all()
        
        # Apply max_teams limit if set
        if event.max_teams:
            teams = teams[:event.max_teams]
        
        added_count = len(teams)
        
        return jsonify({
            "message": f"Successfully added {added_count} team owners to event",
            "added_count": added_count,
            "max_teams": event.max_teams
        })
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
        new_team = models.Team(
            name=owner_data.get('team_name'),
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

# Serve frontend
@app.route("/", methods=['GET'])
def serve_frontend():
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if not os.path.exists(index_path):
        abort(404, description="Frontend not found")
    return send_file(index_path)


# Team Owner Dashboard
@app.route("/team-organization/dashboard", methods=['GET'])
def team_owner_dashboard():
    dashboard_path = os.path.join(TEMPLATES_DIR, "team-owner-dashboard.html")
    if not os.path.exists(dashboard_path):
        abort(404, description="Team owner dashboard not found")
    return send_file(dashboard_path)

# Admin Dashboard
@app.route("/admin/dashboard", methods=['GET'])
def admin_dashboard():
    dashboard_path = os.path.join(TEMPLATES_DIR, "admin-dashboard.html")
    if not os.path.exists(dashboard_path):
        abort(404, description="Admin dashboard not found")
    return send_file(dashboard_path)

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

# Catch-all route for client-side routing
@app.route("/<path:full_path>", methods=['GET'])
def catch_all(full_path: str):
    # Skip API and static file paths
    if full_path.startswith(('api/', 'static/')):
        abort(404, description="Not found")
    
    # Skip admin and team organization routes (they have their own handlers)
    if full_path.startswith(('admin/', 'team-organization/')):
        abort(404, description="Route not found")
    
    # Check if the file exists in the frontend directory
    file_path = os.path.join(FRONTEND_DIR, full_path)
    if os.path.isfile(file_path):
        return send_file(file_path)
        
    # Try to serve the requested file if it exists in templates
    file_path = os.path.join(TEMPLATES_DIR, full_path)
    if os.path.isfile(file_path):
        return send_file(file_path)
    
    # If the file is in the root of the frontend directory (like index.html)
    if full_path == "" or "/" not in full_path:
        root_file = os.path.join(FRONTEND_DIR, full_path or "index.html")
        if os.path.isfile(root_file):
            return send_file(root_file)
    
    # For any other path, serve index.html (client-side routing)
    return send_file(os.path.join(TEMPLATES_DIR, "index.html"))

# Serve all other static files (for SPA routing)
@app.route("/<path:file_path>", methods=['GET'])
def serve_other_files(file_path: str):
    # Skip API routes
    if file_path.startswith('api/'):
        abort(404, description="Not found")
    
    # Check if file exists in static directories
    possible_paths = [
        os.path.join(FRONTEND_DIR, file_path),
        os.path.join(FRONTEND_DIR, "templates", file_path),
        os.path.join(FRONTEND_DIR, "static", file_path)
    ]
    
    for path in possible_paths:
        if os.path.isfile(path):
            return send_file(path)
    
    # If no file found, serve index.html for SPA routing
    index_path = os.path.join(TEMPLATES_DIR, "index.html")
    if os.path.exists(index_path):
        return send_file(index_path)
    
    abort(404, description="File not found")

# Health check endpoint
@app.route("/health", methods=['GET'])
def health_check():
    db = SessionLocal()
    try:
        # Test the database connection by executing a simple query
        db.execute("SELECT 1")
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
    
    # Check if user is admin or team owner
    if current_user.user_type not in [models.UserType.admin, models.UserType.team_owner] and str(current_user.user_type) not in ["admin", "team_owner"]:
        abort(403, description="Not authorized to view auction")
        
    try:
        auction = db.query(models.Auction).filter(models.Auction.event_id == event_id).first()
        if not auction:
            abort(404, description="Auction not found")
        
        # Get current player details
        current_player_data = None
        if auction.current_player:
            current_player_data = {
                "id": auction.current_player.player_id,
                "name": auction.current_player.full_name,
                "sport": "Cricket", # Placeholder
                "category": "Standard", # Placeholder
                "basePrice": float(auction.current_bid_amount), # Use current bid as base for display if needed
                "rating": 8.5, # Placeholder
                "avatar": auction.current_player.profile_image_url
            }
        
        # Get highest bidder name
        highest_bidder_name = "-"
        winning_bid = db.query(models.Bid).filter(
            models.Bid.auction_id == auction.auction_id,
            models.Bid.player_id == auction.current_player_id
        ).order_by(desc(models.Bid.amount)).first()
        
        if winning_bid:
            team = db.query(models.Team).filter(models.Team.team_id == winning_bid.team_id).first()
            if team:
                highest_bidder_name = team.team_name
            
        return jsonify({
            "auction_id": auction.auction_id,
            "event_id": auction.event_id,
            "status": auction.status, # RUNNING/IN_PROGRESS
            "start_time": auction.start_time.isoformat() if auction.start_time else None,
            "current_bid": float(auction.current_bid_amount),
            "current_player": current_player_data,
            "highest_bidder": highest_bidder_name,
            "title": auction.title
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

@app.route("/api/admin/sports", methods=['POST'])
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
            owner = db.query(models.TeamOwner).filter(models.TeamOwner.owner_id == t.owner_id).first()
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
                "budget": float(t.budget) if t.budget else 0,
                "owner_name": owner_user.username if owner_user else "N/A",
                "manager_count": len(managers),
                "analyst_count": len(analysts)
            })
        return jsonify(result)
    finally:
        db.close()

# -------------------------
# Player Dashboard & Notifications APIs
# -------------------------
@app.route("/api/player/dashboard", methods=['GET'])
def get_player_dashboard():
    current_user = get_current_user()
    if current_user.user_type.value != 'player':
        abort(403, description="Player access required")
        
    db = SessionLocal()
    try:
        player = db.query(models.Player).filter(models.Player.user_id == current_user.user_id).first()
        if not player:
            return jsonify({"error": "Player profile not found"}), 404
            
        # Get bids for this player
        bids = db.query(models.Bid).filter(models.Bid.player_id == player.player_id).all()
        auctions_won = sum(1 for b in bids if b.status == 'won')
        highest_bid = max([float(b.amount) for b in bids]) if bids else 0
        avg_bid = (sum([float(b.amount) for b in bids]) / len(bids)) if bids else 0
        
        # Determine team assignments
        team_players = db.query(models.TeamPlayer).filter(models.TeamPlayer.player_id == player.player_id).all()
        teams_interested = len(set([b.team_id for b in bids]))
        
        return jsonify({
            "name": player.full_name,
            "dateOfBirth": player.date_of_birth.isoformat() if player.date_of_birth else None,
            "age": player.age,
            "gender": player.gender,
            "email": current_user.email,
            "phone": player.mobile,
            "location": f"{player.city}, {player.state}",
            "experience": player.experience_level,
            "tier": "Pro", # Could calculate from stats
            "eventsCount": len(player.events),
            "auctionsWon": auctions_won,
            "avgRating": 8.5, # Calculate from skills
            "currentValue": highest_bid or float(player.base_price),
            "activeAuctions": 0, # Calculate if current time matches event
            "totalEvents": len(player.events),
            "successRate": int((auctions_won / max(len(player.events), 1)) * 100),
            "avgBid": avg_bid,
            "highestBid": highest_bid,
            "teamsInterested": teams_interested,
            "profileViews": 0, # Could add views tracking
            "tournamentsWon": 0,
            "mvpAwards": 0,
            "bestPlayerAwards": 0,
            "proContracts": len(team_players),
            "avatar": player.profile_image_url
        })
    finally:
        db.close()

def run_server():
    """Run the Flask application with optimized settings."""
    
    # Initialize database before starting the server process
    initialize_database()
    
    # Start the background auction engine
    try:
        from auction_engine import start_auction_engine
        start_auction_engine()
        print("Auction engine started successfully")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error starting auction engine: {e}")
    
    # Flask development server
    app.run(
        host=os.getenv('HOST', '0.0.0.0'),
        port=int(os.getenv('PORT', 8000)),  # Default port is 8000
        debug=True  # Enable debug mode for development
    )

# This ensures the server only runs when the script is executed directly
if __name__ == "__main__":
    print("Starting server on http://127.0.0.1:8000")
    print("Press Ctrl+C to stop the server")
    run_server()


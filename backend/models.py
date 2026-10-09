from typing import List, Dict, Optional, Any, TYPE_CHECKING
from sqlalchemy import (
    Column, Integer, String, Text, Date, Enum as SQLEnum, DECIMAL, ForeignKey,
    Boolean, DateTime, Index, UniqueConstraint, Table, JSON, CheckConstraint, BigInteger, Time
)
from sqlalchemy.dialects.mysql import BIGINT as APP_BIGINT
from sqlalchemy.sql import func, text
from sqlalchemy.orm import relationship, validates
from database import Base
from datetime import datetime, date, timedelta
import enum
import secrets
import re

# For type hints
if TYPE_CHECKING:
    from .models import Team  # noqa: F401


# -------------------------
# Enums
# -------------------------
class UserType(enum.Enum):
    """
    User types defining the role hierarchy.
    
    Hierarchy:
    - admin: System administrator with full access
    - team_owner: Parent role - can invite staff (manager/analyst) and manage teams
    - team_manager: Child of team_owner - can manage team data and players
    - team_analyst: Child of team_owner - read-only access to team analytics
    - player: Independent role - athletes participating in auctions
    
    Parent-child relationship is established via parent_user_id in User model.
    Staff users (manager/analyst) must have a valid parent_user_id linking to a team_owner.
    """
    admin = "admin"
    team_owner = "team_owner"
    team_manager = "team_manager"
    team_analyst = "team_analyst"
    player = "player"


# -------------------------
# Association table: event_sports (many-to-many)
# -------------------------
event_sports = Table(
    "event_sports",
    Base.metadata,
    Column("event_id", Integer, ForeignKey("events.event_id", ondelete="CASCADE"), primary_key=True),
    Column("sport_id", Integer, ForeignKey("sports.sport_id", ondelete="CASCADE"), primary_key=True),
)


# -------------------------
# Association table: player_events (many-to-many)
# -------------------------
player_events = Table(
    "player_events",
    Base.metadata,
    Column("player_id", Integer, ForeignKey("players.player_id", ondelete="CASCADE"), primary_key=True),
    Column("event_id", Integer, ForeignKey("events.event_id", ondelete="CASCADE"), primary_key=True),
    Column("registered_at", DateTime, server_default=func.current_timestamp(), nullable=False),
    Column("evaluation_score", DECIMAL(5, 2), nullable=True),
    Column("category", String(50), nullable=True)
)


# -------------------------
# User
# -------------------------
class User(Base):
    """
    User model with parent-child relationship for staff management.
    
    Parent-Child Relationship Flow:
    1. Team Owner (parent) registers and optionally adds staff (manager/analyst)
    2. Staff entries are created with parent_user_id pointing to team owner's user_id
    3. Staff accounts start as inactive (is_active=False) with pending invitation status
    4. Staff completes registration by setting username/password
    5. Staff account becomes active and can login
    6. Login verifies parent team owner is still active
    
    Fields for Parent-Child:
    - parent_user_id: Foreign key to users.user_id, links staff to their team owner
    - is_invited: Boolean flag indicating if user was invited by a team owner
    - invitation_status: Tracks invitation state (pending/accepted/rejected)
    """
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # Nullable for team owners
    email = Column(String(100), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=True, index=True)
    user_type = Column(SQLEnum(UserType), nullable=False, index=True)
    
    # Parent-child relationship fields for staff management
    parent_user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True, index=True)  # Links staff (manager/analyst) to their team owner parent
    is_invited = Column(Boolean, default=False, nullable=False)  # True if user was invited by team owner (staff accounts)
    invitation_status = Column(String(20), default='pending', nullable=True)  # Invitation state: pending, accepted, rejected
    
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False)
    last_login = Column(DateTime, index=True)
    last_seen_at = Column(DateTime, index=True, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_verified = Column(Boolean, default=False, nullable=False, index=True)
    verification_token = Column(String(100), unique=True, index=True)
    reset_password_token = Column(String(100), unique=True, index=True)
    reset_password_expires = Column(DateTime, nullable=True)

    # relationships
    player = relationship("Player", back_populates="user", uselist=False, cascade="all, delete-orphan")
    team_owner = relationship("TeamOwner", back_populates="user", uselist=False, cascade="all, delete-orphan")
    created_events = relationship("Event", back_populates="creator", cascade="all, delete-orphan")
    created_auctions = relationship("Auction", back_populates="creator", cascade="all, delete-orphan")
    
    # Self-referential relationship for parent-child hierarchy
    # parent_user: Points to the team owner (parent) for staff users (manager/analyst)
    # staff_members: Backref that gives team owner access to their invited staff
    parent_user = relationship("User", remote_side=[user_id], backref="staff_members")

    __table_args__ = (
        Index("idx_user_email_verified", "email", "is_verified"),
        Index("idx_user_username_active", "username", "is_active"),
    )

    def __repr__(self):
        return f"<User(user_id={self.user_id}, username='{self.username}', email='{self.email}')>"

    def set_password(self, password: str):
        import bcrypt
        if isinstance(password, str):
            password_bytes = password.encode('utf-8')[:72]
        else:
            password_bytes = password[:72]
        self.password_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')

    def verify_password(self, password: str) -> bool:
        if not self.password_hash:  # For team owners without password
            return False
        import bcrypt
        # Bcrypt has a 72-byte limit, truncate if necessary
        if isinstance(password, str):
            password_bytes = password.encode('utf-8')[:72]
        else:
            password_bytes = password[:72]
        
        # Convert stored hash to bytes if it's a string
        if isinstance(self.password_hash, str):
            hash_bytes = self.password_hash.encode('utf-8')
        else:
            hash_bytes = self.password_hash
            
        return bcrypt.checkpw(password_bytes, hash_bytes)

    def generate_reset_token(self, expires_in: int = 3600) -> str:
        self.reset_password_token = secrets.token_urlsafe(32)
        self.reset_password_expires = datetime.utcnow() + timedelta(seconds=expires_in)
        return self.reset_password_token

# -------------------------
# Player
# -------------------------
class Player(Base):
    __tablename__ = "players"

    player_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, unique=True)
    email = Column(String(100), unique=True, nullable=False, index=True)  # Added email field
    password_hash = Column(String(255), nullable=False)  # Add password_hash field
    
    # Personal Information
    first_name = Column(String(50), nullable=False, index=True)
    last_name = Column(String(50), nullable=False, index=True)
    date_of_birth = Column(Date, nullable=True, index=True)
    gender = Column(SQLEnum('male', 'female', 'other', 'prefer-not-to-say', name='gender_enum'), nullable=True, index=True)
    
    # Sports Skills
    cricket_rating = Column(Integer, CheckConstraint('cricket_rating >= 1 AND cricket_rating <= 10'), nullable=True)
    football_rating = Column(Integer, CheckConstraint('football_rating >= 1 AND football_rating <= 10'), nullable=True)
    basketball_rating = Column(Integer, CheckConstraint('basketball_rating >= 1 AND basketball_rating <= 10'), nullable=True)
    
    # Profile Information
    profile_image_url = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    height_cm = Column(Integer, nullable=True)
    weight_kg = Column(DECIMAL(5, 2), nullable=True)
    sport_profiles = Column(JSON, nullable=True)
    
    # Contact Information
    phone = Column(String(20), unique=True, nullable=True, index=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True, index=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    pincode = Column(String(20), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_verified = Column(Boolean, default=False, nullable=False, index=True)
    verification_token = Column(String(100), unique=True, nullable=True, index=True)
    
    # Performance Metrics (manually editable by player)
    total_events_participated = Column(Integer, default=0, nullable=True)
    auction_success_rate = Column(Integer, default=0, nullable=True)  # Percentage
    average_bid_amount = Column(DECIMAL(12, 2), default=0.00, nullable=True)
    highest_winning_bid = Column(DECIMAL(12, 2), default=0.00, nullable=True)
    teams_interested = Column(Integer, default=0, nullable=True)
    profile_views = Column(Integer, default=0, nullable=True)
    
    # Achievements (manually editable by player)
    tournaments_won = Column(Integer, default=0, nullable=True)
    mvp_awards = Column(Integer, default=0, nullable=True)
    best_player_awards = Column(Integer, default=0, nullable=True)
    state_level_champion = Column(Boolean, default=False, nullable=True)
    international_experience = Column(Boolean, default=False, nullable=True)
    professional_contracts = Column(Integer, default=0, nullable=True)
    
    # Timestamps
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="player", uselist=False)
    team_players = relationship("TeamPlayer", back_populates="player", cascade="all, delete-orphan")
    bids = relationship("Bid", back_populates="player", cascade="all, delete-orphan")
    skill_ratings = relationship("PlayerSkillRating", back_populates="player", cascade="all, delete-orphan")
    events = relationship("Event", secondary=player_events, back_populates="players")
    
    __table_args__ = (
        Index('idx_player_name', 'first_name', 'last_name'),
        Index('idx_player_location', 'city', 'country'),
        {
            'comment': 'Stores player information and statistics'
        }
    )

    @property
    def full_name(self) -> str:
        """Return the full name of the player."""
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self) -> Optional[int]:
        """Calculate and return the age of the player based on date of birth."""
        if not self.date_of_birth:
            return None
            
        today = date.today()
        age = today.year - self.date_of_birth.year
        
        # Adjust age if birthday hasn't occurred yet this year
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            age -= 1
            
        return age
        
    def get_skill_rating(self, skill_name: str) -> Optional[int]:
        """Get the rating for a specific skill."""
        skill_rating = getattr(self, f"{skill_name.lower()}_rating", None)
        return skill_rating if skill_rating is not None else None
        
    def update_skill_rating(self, skill_name: str, rating: int) -> None:
        """Update a specific skill rating with validation."""
        if not (1 <= rating <= 10):
            raise ValueError("Rating must be between 1 and 10")
            
        skill_attr = f"{skill_name.lower()}_rating"
        if not hasattr(self, skill_attr):
            raise ValueError(f"Invalid skill: {skill_name}")
            
        setattr(self, skill_attr, rating)
        
    def get_teams(self) -> List['Team']:
        """Get all teams this player belongs to."""
        return [tp.team for tp in self.team_players]
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert player object to dictionary."""
        return {
            'player_id': self.player_id,
            'full_name': self.full_name,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'age': self.age,
            'gender': self.gender,
            'city': self.city,
            'country': self.country,
            'skills': {
                'cricket': self.cricket_rating,
                'football': self.football_rating,
                'basketball': self.basketball_rating
            },
            'performance_metrics': {
                'total_events_participated': self.total_events_participated or 0,
                'auction_success_rate': self.auction_success_rate or 0,
                'average_bid_amount': float(self.average_bid_amount) if self.average_bid_amount else 0,
                'highest_winning_bid': float(self.highest_winning_bid) if self.highest_winning_bid else 0,
                'teams_interested': self.teams_interested or 0,
                'profile_views': self.profile_views or 0
            },
            'achievements': {
                'tournaments_won': self.tournaments_won or 0,
                'mvp_awards': self.mvp_awards or 0,
                'best_player_awards': self.best_player_awards or 0,
                'state_level_champion': self.state_level_champion or False,
                'international_experience': self.international_experience or False,
                'professional_contracts': self.professional_contracts or 0
            },
            'is_active': self.is_active,
            'is_verified': self.is_verified
        }
        
    def __repr__(self) -> str:
        return f"<Player(id={self.player_id}, name='{self.full_name}')>"


# -------------------------
# TeamOwner
# -------------------------
class TeamOwner(Base):
    __tablename__ = "team_owners"

    team_owner_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False)
    
    company_name = Column(String(255), nullable=True)
    gst_number = Column(String(50), nullable=True)
    contact_number = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    pincode = Column(String(20), nullable=True)
    wallet_balance = Column(DECIMAL(12, 2), default=0.00)
    team_logo_url = Column(String(255), nullable=True)
    owner_name = Column(String(100), nullable=True)

    # relationships
    user = relationship("User", back_populates="team_owner")
    teams = relationship("Team", back_populates="owner", cascade="all, delete-orphan")


# -------------------------
# Team
# -------------------------
class Team(Base):
    __tablename__ = "teams"

    team_id = Column(Integer, primary_key=True, autoincrement=True)
    team_name = Column(String(100), nullable=False)
    owner_id = Column(Integer, ForeignKey("team_owners.team_owner_id", ondelete="CASCADE"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.event_id"), nullable=True)
    logo_url = Column(String(255), nullable=True)
    jersey_color = Column(String(20), nullable=True)
    status = Column(String(20), default='active', nullable=False)
    max_players = Column(Integer, default=15, nullable=False)
    current_players = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False)

    # relationships
    owner = relationship("TeamOwner", back_populates="teams")
    event = relationship("Event", back_populates="teams")
    players = relationship("TeamPlayer", back_populates="team", cascade="all, delete-orphan")
    bids = relationship("Bid", back_populates="team", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_team_name', 'team_name'),
        Index('idx_team_owner', 'owner_id'),
        UniqueConstraint('team_name', name='uq_team_name'),
        CheckConstraint("status IN ('active', 'inactive', 'suspended', 'banned', 'pending')", name='check_team_status')
    )


# -------------------------
# Sport
# -------------------------
class Sport(Base):
    __tablename__ = "sports"

    sport_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    category = Column(String(150), nullable=True)
    tier = Column(Integer, nullable=True, index=True)
    players_equipment = Column(Text, nullable=True)
    scoring_format = Column(Text, nullable=True)
    exact_rules = Column(Text, nullable=True)
    icon_class = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False)

    roles_config = Column(JSON, nullable=True)
    categories_config = Column(JSON, nullable=True)
    attributes_schema = Column(JSON, nullable=True)
    default_auction_rules = Column(JSON, nullable=True)
    evaluation_rules = Column(JSON, nullable=True)
    training_config = Column(JSON, nullable=True)

    # relationships
    skills = relationship("PlayerSkill", back_populates="sport", cascade="all, delete-orphan")
    events = relationship(
        "Event", 
        secondary=event_sports, 
        back_populates="sports",
        primaryjoin="Sport.sport_id==event_sports.c.sport_id",
        secondaryjoin="Event.event_id==event_sports.c.event_id",
        overlaps="sport"
    )


# -------------------------
# PlayerSkill & Rating
# -------------------------
class PlayerSkill(Base):
    __tablename__ = "player_skills"

    skill_id = Column(Integer, primary_key=True, autoincrement=True)
    sport_id = Column(Integer, ForeignKey("sports.sport_id"), nullable=False)
    skill_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    min_rating = Column(Integer, default=1)
    max_rating = Column(Integer, default=10)
    is_active = Column(Boolean, default=True)

    sport = relationship("Sport", back_populates="skills")
    ratings = relationship("PlayerSkillRating", back_populates="skill", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint('min_rating >= 1', name='check_min_rating'),
        CheckConstraint('max_rating <= 10', name='check_max_rating'),
        CheckConstraint('min_rating <= max_rating', name='check_rating_range')
    )


class PlayerSkillRating(Base):
    __tablename__ = "player_skill_ratings"

    rating_id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.player_id"), nullable=False)
    skill_id = Column(Integer, ForeignKey("player_skills.skill_id"), nullable=False)
    rating = Column(Integer, nullable=False)
    rated_by = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    rated_at = Column(DateTime, default=func.current_timestamp())
    notes = Column(Text, nullable=True)

    player = relationship("Player", back_populates="skill_ratings")
    skill = relationship("PlayerSkill", back_populates="ratings")
    rater = relationship("User", foreign_keys=[rated_by])
    
    __table_args__ = (
        CheckConstraint('rating >= 1 AND rating <= 10', name='check_skill_rating_range'),
        Index('idx_skill_rating', 'player_id', 'skill_id')
    )


# -------------------------
# Event
# -------------------------
class Event(Base):
    __tablename__ = "events"

    event_id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    registration_deadline = Column(DateTime, nullable=True)
    location = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    pincode = Column(String(20), nullable=True)
    max_participants = Column(Integer, default=100, nullable=False)
    current_participants = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default='upcoming', nullable=False)
    budget = Column(DECIMAL(12, 2), default=0.00)
    base_prices = Column(JSON, nullable=True)
    bid_time_limit = Column(Integer, default=20)
    registration_fee = Column(DECIMAL(10, 2), default=0.00)
    max_players = Column(Integer, nullable=True)
    max_teams = Column(Integer, nullable=True)
    extra_info = Column(Text, nullable=True)
    is_live = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False)
    # Cricket Configuration Additions
    sport_id = Column(Integer, ForeignKey("sports.sport_id"), nullable=True)
    event_config = Column(JSON, nullable=True)
    
    # Relationships
    creator_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    creator = relationship("User", back_populates="created_events", uselist=False)
    teams = relationship("Team", back_populates="event", cascade="all, delete-orphan")
    auctions = relationship("Auction", back_populates="event", cascade="all, delete-orphan")
    
    # Legacy many-to-many sports relationship
    sports = relationship(
        "Sport", 
        secondary=event_sports, 
        back_populates="events",
        primaryjoin="Event.event_id==event_sports.c.event_id",
        secondaryjoin="Sport.sport_id==event_sports.c.sport_id",
        overlaps="events"
    )
    
    # New Cricket Configuration Authoritative Sport relationship
    sport = relationship("Sport", foreign_keys=[sport_id])
    
    players = relationship("Player", secondary=player_events, back_populates="events")
    
    __table_args__ = (
        Index('idx_event_dates', 'start_date', 'end_date'),
        Index('idx_event_status', 'status'),
        Index('idx_event_location', 'location'),
        CheckConstraint('end_date >= start_date', name='check_event_dates'),
        CheckConstraint("status IN ('upcoming', 'registration_open', 'in_progress', 'completed', 'cancelled')", 
                       name='check_event_status')
    )
    
    @validates('registration_deadline')
    def validate_registration_deadline(self, key, deadline):
        if deadline and deadline > self.start_date:
            raise ValueError("Registration deadline must be before the event start date")
        return deadline

    @property
    def is_registration_open(self):
        now = datetime.utcnow()
        return self.status == "registration_open" and (self.registration_deadline is None or now <= self.registration_deadline)

    def can_register(self):
        if not self.is_registration_open:
            return False
        if self.max_participants and self.current_participants >= self.max_participants:
            return False
        return True


# -------------------------
# TeamPlayer (Junction table between Team and Player)
# -------------------------


class TeamPlayer(Base):
    __tablename__ = "team_players"
    
    team_player_id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.player_id", ondelete="CASCADE"), nullable=False)
    jersey_number = Column(String(10), nullable=True)
    position = Column(String(50), nullable=True)
    is_captain = Column(Boolean, default=False)
    joined_date = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    
    team = relationship("Team", back_populates="players")
    player = relationship("Player", back_populates="team_players")
    
    __table_args__ = (
        UniqueConstraint('team_id', 'player_id', name='uq_team_player'),
        UniqueConstraint('team_id', 'jersey_number', name='uq_team_jersey'),
        Index('idx_team_player', 'team_id', 'player_id'),
        # Using REGEXP for MySQL compatibility
        CheckConstraint("jersey_number IS NULL OR jersey_number REGEXP '^[0-9]{1,2}$'", name='check_jersey_number')
    )


# -------------------------
# Auction / Bid
# -------------------------
class Auction(Base):
    __tablename__ = "auctions"
    
    auction_id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("events.event_id", ondelete="CASCADE"), nullable=False)
    creator_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String(20), default='scheduled', nullable=False)
    current_player_id = Column(Integer, ForeignKey("players.player_id", ondelete="SET NULL"), nullable=True)
    current_player_bid_start = Column(DateTime, nullable=True)
    current_bid_amount = Column(DECIMAL(12, 2), default=0.00, nullable=False)
    current_team_id = Column(Integer, ForeignKey("teams.team_id", ondelete="SET NULL"), nullable=True)
    min_bid_increment = Column(DECIMAL(12, 2), default=1.00, nullable=False)
    bid_deadline = Column(DateTime, nullable=True)
    paused_time_left = Column(DECIMAL(10, 2), nullable=True)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp(), nullable=False)
    
    # Relationships
    event = relationship("Event", back_populates="auctions")
    creator = relationship("User", back_populates="created_auctions")
    current_player = relationship("Player", foreign_keys=[current_player_id])
    bids = relationship("AuctionBid", back_populates="auction", cascade="all, delete-orphan")
    auction_players = relationship("AuctionPlayer", back_populates="auction", cascade="all, delete-orphan")
    team_statuses = relationship("AuctionTeamStatus", back_populates="auction", cascade="all, delete-orphan")
    current_team = relationship("Team", foreign_keys=[current_team_id])
    
    __table_args__ = (
        Index('idx_auction_event', 'event_id'),
        Index('idx_auction_creator', 'creator_id'),
        Index('idx_auction_status', 'status'),
        Index('idx_auction_times', 'start_time', 'end_time'),
        CheckConstraint("status IN ('draft', 'ready', 'lobby', 'live', 'paused', 'scheduled', 'in_progress', 'completed', 'cancelled', 'NOT_STARTED', 'READY', 'RUNNING', 'PAUSED', 'STOPPED', 'COMPLETED')", name='check_auction_status'),
        CheckConstraint('end_time > start_time', name='check_auction_times')
    )


class AuctionPlayer(Base):
    __tablename__ = "auction_players"

    id = Column(Integer, primary_key=True, autoincrement=True)
    auction_id = Column(Integer, ForeignKey("auctions.auction_id", ondelete="CASCADE"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.player_id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default='PENDING', nullable=False)
    base_price = Column(DECIMAL(12, 2), default=0.00)
    final_price = Column(DECIMAL(12, 2), default=0.00)
    sold_to_team_id = Column(Integer, ForeignKey("teams.team_id", ondelete="SET NULL"), nullable=True)
    auction_order = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)

    auction = relationship("Auction", back_populates="auction_players")
    player = relationship("Player")
    team = relationship("Team")


class AuctionBid(Base):
    __tablename__ = "auction_bids"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    auction_id = Column(Integer, ForeignKey("auctions.auction_id", ondelete="CASCADE"), nullable=False)
    auction_player_id = Column(Integer, ForeignKey("auction_players.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False)
    bid_amount = Column(DECIMAL(12, 2), nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    
    auction = relationship("Auction", back_populates="bids")
    auction_player = relationship("AuctionPlayer")
    team = relationship("Team")


class AuctionTeamStatus(Base):
    __tablename__ = "auction_team_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    auction_id = Column(Integer, ForeignKey("auctions.auction_id", ondelete="CASCADE"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), default='WAITING', nullable=False)
    current_purse = Column(DECIMAL(12, 2), nullable=False)
    squad_size = Column(Integer, default=0)

    auction = relationship("Auction", back_populates="team_statuses")
    team = relationship("Team")


class Bid(Base):
    __tablename__ = "bids"
    
    bid_id = Column(Integer, primary_key=True, autoincrement=True)
    auction_id = Column(Integer, ForeignKey("auctions.auction_id", ondelete="CASCADE"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.player_id", ondelete="CASCADE"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False)
    amount = Column(DECIMAL(12, 2), nullable=False)
    status = Column(String(20), default='pending', nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    
    # Relationships
    auction = relationship("Auction")
    player = relationship("Player", back_populates="bids")
    team = relationship("Team", back_populates="bids")
    
    __table_args__ = (
        Index('idx_bid_auction_player', 'auction_id', 'player_id'),
        Index('idx_bid_team', 'team_id'),
        Index('idx_bid_amount', 'amount'),
        Index('idx_bid_status', 'status'),
    )



# -------------------------
# Session Management
# -------------------------
class Session(Base):
    __tablename__ = "sessions"

    session_id = Column(String(64), primary_key=True, autoincrement=False)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    session_token = Column(String(128), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    is_active = Column(Boolean, default=True, server_default=text('1'), nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    last_activity = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    # Relationships
    user = relationship("User", backref="sessions")

    __table_args__ = (
        Index('idx_session_token', 'session_token'),
        Index('idx_session_expires', 'expires_at'),
    )

    def __repr__(self):
        return f"<Session(session_id='{self.session_id}', user_id={self.user_id})>"


# -------------------------
# Transaction
# -------------------------
class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    from_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    to_user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    amount = Column(DECIMAL(12, 2), nullable=False)
    transaction_type = Column(String(50), nullable=False)
    reference_id = Column(String(100), nullable=True)
    status = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)

    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])

    __table_args__ = (
        Index('idx_transaction_reference', 'reference_id'),
        Index('idx_transaction_status', 'status'),
        Index('idx_transaction_created', 'created_at'),
    )



# -------------------------
# Activity Log
# -------------------------
class ActivityLog(Base):
    __tablename__ = "activity_logs"

    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True, index=True)  # Allow NULL for public logs
    action_type = Column(String(100), nullable=False, index=True)
    action_description = Column(Text, nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(BigInteger, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False, index=True)

    # Relationship to User (without FK constraint to avoid compatibility issues)
    # user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index('idx_entity', 'entity_type', 'entity_id'),
    )

# -------------------------
# Messages / Support
# -------------------------
class Message(Base):
    __tablename__ = "messages"

    message_id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    sender_name = Column(String(100), nullable=True)
    team_name = Column(String(100), nullable=True)
    subject = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False)
    is_read = Column(Boolean, default=False)

    sender = relationship("User", foreign_keys=[sender_id])

# -------------------------
# Notifications
# -------------------------
class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False, index=True) # e.g., 'system', 'event', 'profile'
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.current_timestamp(), nullable=False, index=True)

    user = relationship("User", foreign_keys=[user_id])

# -------------------------
# Training / Calendar
# -------------------------
class TrainingSession(Base):
    __tablename__ = "training_sessions"

    training_session_id = Column(BigInteger, primary_key=True, autoincrement=True)
    team_id = Column(BigInteger, ForeignKey("teams.team_id", ondelete="CASCADE"), nullable=False, index=True)
    manager_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    title = Column(String(255), nullable=False)
    training_type = Column(String(100), nullable=False)
    date = Column("training_date", Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    location = Column(String(255), nullable=True)
    coach = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="Scheduled") # Scheduled, In Progress, Completed, Cancelled
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    team = relationship("Team")
    manager = relationship("User", foreign_keys=[manager_id])
    attendance = relationship("TrainingAttendance", back_populates="training_session", cascade="all, delete-orphan")


class TrainingAttendance(Base):
    __tablename__ = "training_attendance"

    attendance_id = Column(BigInteger, primary_key=True, autoincrement=True)
    training_session_id = Column(BigInteger, ForeignKey("training_sessions.training_session_id", ondelete="CASCADE"), nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("players.player_id", ondelete="RESTRICT"), nullable=False, index=True)
    status = Column(String(50), default="Pending") # Pending, Present, Absent, Late, Excused
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    training_session = relationship("TrainingSession", back_populates="attendance")
    player = relationship("Player")

    __table_args__ = (
        UniqueConstraint('training_session_id', 'player_id', name='uq_session_player'),
    )

from datetime import datetime, date
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field, validator
from enum import Enum
import re


# Enums
class UserType(str, Enum):
    """
    User types defining the role hierarchy for parent-child relationship.
    
    Hierarchy:
    - admin: System administrator with full access
    - team_owner: Parent role - can invite staff (manager/analyst) and manage teams
    - team_manager: Child of team_owner - can manage team data and players
    - team_analyst: Child of team_owner - read-only access to team analytics
    - player: Independent role - athletes participating in auctions
    """
    admin = "admin"
    team_owner = "team_owner"
    team_manager = "team_manager"
    team_analyst = "team_analyst"
    player = "player"

class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"

class EventStatus(str, Enum):
    upcoming = "upcoming"
    registration_open = "registration_open"
    registration_closed = "registration_closed"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"

class RegistrationStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    withdrawn = "withdrawn"

class PaymentStatus(str, Enum):
    pending = "pending"
    paid = "paid"
    refunded = "refunded"
    failed = "failed"

class TeamStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    disqualified = "disqualified"

class AuctionStatus(str, Enum):
    scheduled = "scheduled"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"

class BidStatus(str, Enum):
    active = "active"
    won = "won"
    lost = "lost"
    winning = "winning"
    outbid = "outbid"
    withdrawn = "withdrawn"
    sold = "sold"
    unsold = "unsold"

# -------------------------
# Authentication Schemas
# -------------------------
class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: Optional[bool] = False

# Base schemas
class UserBase(BaseModel):
    username: str
    email: EmailStr
    phone: Optional[str] = None
    user_type: UserType

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class TeamOwnerUserCreate(UserBase):
    """User creation schema for team owner registration"""
    phone: str = Field(..., min_length=10, max_length=15, pattern=r'^[0-9+\-\s()]+$')
    user_type: str = "team_owner"
    password: str = Field(..., min_length=6)  # Password required for team owner login

    @validator('phone')
    def validate_phone(cls, v):
        # Remove all non-digit characters
        digits = ''.join(filter(str.isdigit, v))
        if len(digits) < 10 or len(digits) > 15:
            raise ValueError('Phone number must be between 10-15 digits')
        return digits


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None

class ApproveUserRequest(BaseModel):
    """Schema for approving a user (setting password and activating)"""
    password: str = Field(..., min_length=6, description="New password for USER")


class UserInDB(UserBase):
    user_id: int
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True

    class Config:
        from_attributes = True

# Player schemas
class PlayerBase(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Gender
    profile_image_url: Optional[str] = None
    bio: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None

class PlayerCreate(PlayerBase):
    user_id: int

class PlayerUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    bio: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None

class Player(PlayerBase):
    player_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class PlayerInDB(PlayerBase):
    player_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class PlayerResponse(PlayerInDB):
    """Response schema for player registration"""
    user: UserInDB
    message: str = "Player registered successfully"
    
    class Config:
        from_attributes = True

class PlayerRegistration(BaseModel):
    """Schema for player registration"""
    first_name: str = Field(..., alias='firstName')
    last_name: str = Field(..., alias='lastName')
    email: EmailStr
    password: str
    phone: str
    date_of_birth: str = Field(..., alias='dateOfBirth')
    gender: str = 'other'
    confirm_password: Optional[str] = Field(None, alias='confirmPassword')
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None
    bio: Optional[str] = None
    height_cm: Optional[int] = None
    weight_kg: Optional[float] = None
    event_id: int = Field(..., alias='eventId')  # Required field
    sport_ratings: Optional[List[dict]] = Field(default=[], alias='sportRatings')  # [{sport_id: 1, rating: 8}, ...]


    @validator('password')
    def password_complexity(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one number')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(char in '!@#$%^&*()' for char in v):
            raise ValueError('Password must contain at least one special character (!@#$%^&*)')
        return v

    @validator('confirm_password')
    def passwords_match(cls, v, values, **kwargs):
        if 'password' in values and v != values.get('password'):
            raise ValueError('Passwords do not match')
        return v

    @validator('email')
    def validate_email(cls, v):
        # Simple email validation
        if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', v):
            raise ValueError('Invalid email format')
        return v.lower()

    @validator('phone')
    def validate_phone(cls, v):
        # Simple phone number validation (10 digits)
        if not re.match(r'^\d{10}$', v):
            raise ValueError('Phone number must be 10 digits')
        return v
    
    class Config:
        from_attributes = True
        populate_by_name = True  # Allow populating by field name (both snake_case and camelCase)
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TeamOwnerRegistration(BaseModel):
    """Schema for team owner registration"""
    name: str
    email: EmailStr
    phone: str
    team_name: str
    team_logo: str = ""
    team_bio: str = ""
    preferred_sports: List[str]
    budget: float
    contact_person: str
    contact_email: EmailStr
    contact_phone: str
    address: str
    city: str
    state: str
    country: str
    pincode: str
    event_id: Optional[int] = None
    
    # Staff invitation fields (optional) - for parent-child relationship
    # Team owner can invite staff members (manager/analyst) during registration
    # These fields create pending user entries linked to the team owner via parent_user_id
    team_manager_name: Optional[str] = Field(None, alias='teamManagerName')
    team_manager_email: Optional[EmailStr] = Field(None, alias='teamManagerEmail')
    team_analyst_name: Optional[str] = Field(None, alias='teamAnalystName')
    team_analyst_email: Optional[EmailStr] = Field(None, alias='teamAnalystEmail')

    @validator('email')
    def validate_email(cls, v):
        if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', v):
            raise ValueError('Invalid email format')
        return v.lower()

    @validator('contact_email')
    def validate_contact_email(cls, v):
        if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', v):
            raise ValueError('Invalid contact email format')
        return v.lower()

    @validator('phone')
    def validate_phone(cls, v):
        if not re.match(r'^\d{10}$', v):
            raise ValueError('Phone number must be 10 digits')
        return v

    @validator('team_manager_email')
    def validate_team_manager_email(cls, v):
        if v and not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', v):
            raise ValueError('Invalid team manager email format')
        return v.lower() if v else v

    @validator('team_analyst_email')
    def validate_team_analyst_email(cls, v):
        if v and not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', v):
            raise ValueError('Invalid team analyst email format')
        return v.lower() if v else v


class StaffRegistration(BaseModel):
    """
    Schema for staff (manager/analyst) registration completion.
    
    Flow:
    1. Staff enters email to check for pending invitation
    2. If invitation exists, staff sets username and password
    3. Backend validates invitation and activates the account
    4. Staff can then login with their credentials
    
    This schema is used in the second step of staff registration
    after invitation has been verified.
    """
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    confirm_password: str = Field(..., alias='confirmPassword')

    @validator('password')
    def password_complexity(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters long')
        return v

    @validator('confirm_password')
    def passwords_match(cls, v, values, **kwargs):
        if 'password' in values and v != values.get('password'):
            raise ValueError('Passwords do not match')
        return v


class StaffInvitationCheck(BaseModel):
    """
    Schema to check if an email has a pending staff invitation.
    
    Used in the first step of staff registration flow:
    - Staff enters their email
    - Backend checks if email exists as a pending invitation (is_invited=True, invitation_status='pending')
    - Returns invitation details (role, team owner info) if found
    """
    email: EmailStr

# Team Owner schemas
class TeamOwnerBase(BaseModel):
    team_name: str
    team_logo_url: Optional[str] = None
    company_name: Optional[str] = None
    gst_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None
    wallet_balance: float = 0.00

class TeamOwnerRegistrationRequest(BaseModel):
    team_name: str
    owner_name: str
    address: str
    team_logo_url: Optional[str] = None
    event_id: Optional[int] = None
    team_manager_name: Optional[str] = Field(None, alias='teamManagerName')
    team_manager_email: Optional[EmailStr] = Field(None, alias='teamManagerEmail')
    team_analyst_name: Optional[str] = Field(None, alias='teamAnalystName')
    team_analyst_email: Optional[EmailStr] = Field(None, alias='teamAnalystEmail')

class TeamOwnerRegistrationCombined(BaseModel):
    """Combined schema for team owner registration matching frontend structure"""
    user_data: TeamOwnerUserCreate
    team_owner_data: TeamOwnerRegistrationRequest


class TeamOwnerCreate(TeamOwnerBase):
    user_id: int

class TeamOwnerUpdate(BaseModel):
    team_name: Optional[str] = None
    team_logo_url: Optional[str] = None
    company_name: Optional[str] = None
    gst_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None

class TeamOwner(TeamOwnerBase):
    owner_id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Sport schemas
class SportBase(BaseModel):
    name: str
    description: Optional[str] = None
    icon_class: Optional[str] = None
    is_active: bool = True

class SportCreate(SportBase):
    pass

class SportUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon_class: Optional[str] = None
    is_active: Optional[bool] = None

class Sport(SportBase):
    sport_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Player Skill schemas
class PlayerSkillBase(BaseModel):
    sport_id: int
    skill_name: str
    description: Optional[str] = None
    min_rating: int = 1
    max_rating: int = 10
    is_active: bool = True

class PlayerSkillCreate(PlayerSkillBase):
    pass

class PlayerSkillUpdate(BaseModel):
    skill_name: Optional[str] = None
    description: Optional[str] = None
    min_rating: Optional[int] = None
    max_rating: Optional[int] = None
    is_active: Optional[bool] = None

class PlayerSkill(PlayerSkillBase):
    skill_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Event schemas
class EventBase(BaseModel):
    title: str
    description: Optional[str] = None
    start_date: datetime
    end_date: datetime
    registration_deadline: Optional[datetime] = None
    location: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None
    max_participants: Optional[int] = None
    current_participants: int = 0
    status: EventStatus = EventStatus.upcoming
    budget: Optional[float] = 0.00
    base_prices: Optional[Dict[str, float]] = None
    bid_time_limit: Optional[int] = 20
    registration_fee: Optional[float] = 0.00
    max_players: Optional[int] = None
    max_teams: Optional[int] = None
    extra_info: Optional[str] = None
    is_live: bool = False

class EventCreate(EventBase):
    sport_ids: List[int] = []
    sport_names: List[str] = []

class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    registration_deadline: Optional[datetime] = None
    location: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None
    max_participants: Optional[int] = None
    status: Optional[EventStatus] = None
    budget: Optional[float] = None
    base_prices: Optional[Dict[str, float]] = None
    bid_time_limit: Optional[int] = None
    registration_fee: Optional[float] = None
    max_players: Optional[int] = None
    max_teams: Optional[int] = None
    extra_info: Optional[str] = None
    sport_names: Optional[List[str]] = None
    is_live: Optional[bool] = None

class Event(EventBase):
    event_id: int
    creator_id: int
    created_at: datetime
    updated_at: datetime
    sports: List[Sport] = []

    class Config:
        from_attributes = True

# Team schemas
class TeamBase(BaseModel):
    team_name: str
    event_id: int
    sport_id: int
    logo_url: Optional[str] = None
    jersey_color: Optional[str] = None
    status: TeamStatus = TeamStatus.active

class TeamCreate(TeamBase):
    owner_id: int

class TeamUpdate(BaseModel):
    team_name: Optional[str] = None
    logo_url: Optional[str] = None
    jersey_color: Optional[str] = None
    status: Optional[TeamStatus] = None

class Team(TeamBase):
    team_id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Auction schemas
class AuctionBase(BaseModel):
    event_id: int
    sport_id: int
    start_time: datetime
    end_time: datetime
    status: AuctionStatus = AuctionStatus.scheduled
    current_player_id: Optional[int] = None
    current_player_bid_start: Optional[datetime] = None
    current_bid_amount: float = 0.00
    current_bidder_id: Optional[int] = None

class AuctionCreate(AuctionBase):
    created_by: int

class AuctionUpdate(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[AuctionStatus] = None
    current_player_id: Optional[int] = None
    current_player_bid_start: Optional[datetime] = None
    current_bid_amount: Optional[float] = None
    current_bidder_id: Optional[int] = None

class Auction(AuctionBase):
    auction_id: int
    created_by: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Bid schemas
class BidBase(BaseModel):
    auction_id: int
    player_id: int
    team_id: int
    bid_amount: float
    status: BidStatus = BidStatus.winning

class BidCreate(BidBase):
    pass

class BidUpdate(BaseModel):
    bid_amount: Optional[float] = None
    status: Optional[BidStatus] = None

class Bid(BidBase):
    bid_id: int
    bid_time: datetime

    class Config:
        from_attributes = True

class BidResponse(Bid):
    """Response schema for bid data with relationships"""
    auction: Auction
    player: Player
    team: Team
    bidder: TeamOwner
    
    class Config:
        from_attributes = True

# Transaction schemas
class TransactionBase(BaseModel):
    from_user_id: Optional[int] = None
    to_user_id: Optional[int] = None
    amount: float
    transaction_type: str
    reference_id: Optional[str] = None
    status: str
    description: Optional[str] = None

class TransactionCreate(TransactionBase):
    pass

class Transaction(TransactionBase):
    transaction_id: int
    created_at: datetime

    class Config:
        from_attributes = True

# Response schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    user_type: Optional[UserType] = None

# Nested schemas for relationships
class PlayerWithUser(Player):
    user: UserInDB

class TeamWithOwner(Team):
    owner: TeamOwner

class EventWithSports(Event):
    sports: List[Sport] = []

class EventResponse(Event):
    """Response schema for event data with relationships"""
    sports: List[Sport] = []
    registered_players_count: int = 0
    teams_count: int = 0
    status: str = "upcoming"
    created_by: Optional[UserInDB] = None
    
    class Config:
        from_attributes = True

class AuctionWithDetails(Auction):
    event: Event
    sport: Sport
    current_player: Optional[Player] = None
    current_bidder: Optional[TeamOwner] = None

class AuctionResponse(Auction):
    """Response schema for auction data with relationships"""
    event: Event
    sport: Sport
    current_player: Optional[Player] = None
    current_bidder: Optional[TeamOwner] = None
    total_bids: int = 0
    highest_bid: Optional[float] = None
    
    class Config:
        from_attributes = True

# Activity Log schemas
class ActivityLogBase(BaseModel):
    action_type: str
    action_description: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None

class ActivityLogCreate(ActivityLogBase):
    user_id: Optional[int] = None  # Optional for public logs
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class ActivityLog(ActivityLogBase):
    log_id: int
    user_id: int
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class TeamOwnerCreateAdmin(BaseModel):
    """Schema for admin to manually create a team owner"""
    username: str
    password: str
    email: EmailStr
    phone: str
    team_name: str
    owner_name: str
    address: str
    event_id: Optional[int] = None

# Message schemas
class MessageBase(BaseModel):
    subject: Optional[str] = None
    content: str
    team_name: Optional[str] = None
    sender_name: Optional[str] = None

class MessageCreate(MessageBase):
    pass

class Message(MessageBase):
    message_id: int
    sender_id: Optional[int] = None
    created_at: datetime
    is_read: bool

    class Config:
        from_attributes = True
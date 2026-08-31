-- Single table for player registration
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    
    -- Account Information
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    phone VARCHAR(20) UNIQUE,
    user_type VARCHAR(20) NOT NULL,
    
    -- Personal Information
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    date_of_birth DATE,
    gender VARCHAR(20),
    
    -- Sports Skills (stored as JSON)
    cricket_rating INTEGER CHECK (cricket_rating >= 0 AND cricket_rating <= 10),
    football_rating INTEGER CHECK (football_rating >= 0 AND football_rating <= 10),
    basketball_rating INTEGER CHECK (basketball_rating >= 0 AND basketball_rating <= 10),
    -- Add more sports as needed
    
    -- Additional Fields
    profile_image_url VARCHAR(255),
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(100),
    pincode VARCHAR(20),
    country VARCHAR(100),
    
    -- Staff Management Fields
    parent_user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
    is_invited BOOLEAN DEFAULT false,
    invitation_status VARCHAR(20) DEFAULT 'pending',

    -- Status and Timestamps
    is_active BOOLEAN DEFAULT true,
    is_verified BOOLEAN DEFAULT false,
    verification_token VARCHAR(100),
    reset_password_token VARCHAR(100),
    reset_password_expires TIMESTAMP,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sessions
CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    user_id BIGINT NOT NULL,
    session_token VARCHAR(500) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Events table
CREATE TABLE events (
    event_id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    registration_deadline TIMESTAMP,
    location VARCHAR(255) NOT NULL,
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    pincode VARCHAR(20),
    max_participants INTEGER DEFAULT 100,
    current_participants INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'upcoming',
    budget DECIMAL(12, 2) DEFAULT 0.00,
    base_prices JSON NULL,
    bid_time_limit INTEGER DEFAULT 20,
    registration_fee DECIMAL(10, 2) DEFAULT 0.00,
    max_players INTEGER NULL,
    max_teams INTEGER NULL,
    extra_info TEXT NULL,
    is_live BOOLEAN DEFAULT FALSE,
    creator_id INTEGER NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Teams table
CREATE TABLE teams (
    team_id SERIAL PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL,
    owner_name VARCHAR(100) NOT NULL,
    owner_email VARCHAR(100) NOT NULL,
    owner_phone VARCHAR(20) NOT NULL,
    event_id INTEGER REFERENCES events(event_id),
    logo_url VARCHAR(255),
    jersey_color VARCHAR(20),
    status VARCHAR(20) DEFAULT 'active',
    max_players INTEGER DEFAULT 15,
    current_players INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Team Players (mapping between players and teams)
CREATE TABLE team_players (
    team_player_id SERIAL PRIMARY KEY,
    team_id INTEGER REFERENCES teams(team_id),
    player_id INTEGER REFERENCES players(player_id),
    jersey_number VARCHAR(10),
    position VARCHAR(50),
    is_captain BOOLEAN DEFAULT false,
    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Auctions table
CREATE TABLE auctions (
    auction_id SERIAL PRIMARY KEY,
    event_id INTEGER REFERENCES events(event_id),
    title VARCHAR(200) NOT NULL,
    description TEXT,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'scheduled',
    current_player_id INTEGER REFERENCES players(player_id),
    current_bid_amount DECIMAL(12,2) DEFAULT 0.00,
    min_bid_increment DECIMAL(12,2) DEFAULT 1.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Bids table
CREATE TABLE bids (
    bid_id SERIAL PRIMARY KEY,
    auction_id INTEGER REFERENCES auctions(auction_id),
    player_id INTEGER REFERENCES players(player_id),
    team_id INTEGER REFERENCES teams(team_id),
    amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Admin User Credentials
-- NOTE: The password here is 'admin123' hashed with bcrypt
INSERT INTO users (username, email, password_hash, first_name, last_name, user_type, is_active, is_verified) 
VALUES ('admin', 'admin@bidzone.com', '$2b$12$R.325hY/QG0lJ0K6xS76tO3/tQOQWp/Lz.wXoT3p4/L/3X/5/K/oW', 'Admin', 'User', 'admin', true, true);

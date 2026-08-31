# JamRig: Sports Auction Platform Overview

JamRig is a comprehensive web-based platform designed to manage and execute sports auctions. It provides a seamless experience for administrators to manage events, for players to showcase their skills fixed across multiple sports, and for team owners to participate in real-time auctions to build their dream squads.

## 1. Homepage (The Landing Page)
The homepage serves as the entry point for all users, featuring a modern and dynamic design:
- **Hero Section**: Engaging introduction to the platform with a clear call-to-action for new registrations.
- **Upcoming Auction Events**: A real-time grid displaying active and upcoming events.
    - **Live Badges**: Events currently in progress are highlighted with "LIVE NOW" indicators.
    - **Sports Tags**: Each event shows the specific sports involved (e.g., Cricket, Football, Tennis).
    - **Event Details**: Users can view full details or jump straight to registration.
- **How It Works**: A step-by-step guide for Players and Team Owners to understand the platform's lifecycle.
- **Global Authentication**: Integrated login/register modals for all user types.

---

## 2. Administrator Dashboard
The "Master Control" for the entire platform, featuring:
- **System Monitoring**: Real-time stats for CPU, RAM, and Bandwidth usage with dynamic visual indicators.
- **Event Management**: 
    - Full CRUD capabilities for auction events.
    - Set event-specific rules: Budget limits, registration fees, player/team caps, and bidding time limits (10-60s).
    - Manage sports associated with each event.
- **User Management & Approval**:
    - **Player Registrations**: Paginated and sortable table to review and approve player applications.
    - **Team Owner Registrations**: Verification system for team owners before they can join auctions.
- **Support Messages**: Real-time communication bridge between Team Owners and Admins.
    - Features: Pagination, sorting (unread first, date, team name), and read/unread status tracking.
- **Activity Logs**: Detailed auditing of all system actions (Admin, Player, and Team Owner activities) with search and pagination.

---

## 3. Player Dashboard
A dedicated space for athletes to manage their professional profiles:
- **Profile Management**: Full control over personal details and contact information.
- **Sports Skill Ratings**: Comprehensive 1-10 rating system across 9 sports:
    - Dedicated ratings for Cricket, Football, Basketball, Tennis, Badminton, Hockey, Volleyball, Baseball, and Golf.
- **Performance Analytics**: 
    - Track "Events Participated", "Auctions Won" (Teams joined), and "Average Rating".
    - Graphical success rate tracking and "Teams Interested" metrics.
- **Activity Feed**: Real-time history of registration status and profile views.

---

## 4. Team Owner Dashboard
The strategic hub for building a championship-winning team:
- **Team Management**:
    - Manage multiple squads across different events.
    - View live squad members, their roles, and positions.
- **Strategic Auction Hub**:
    - **Wallet Management**: Real-time tracking of current budget and auction spending.
    - **Live Auction Interface**: 
        - **Player Cards**: View the current player's skills, ratings, and base price.
        - **Bidding Panel**: Instant "Quick Bids" (+10k, +50k, +1L) or custom bid sliders.
        - **Real-time Updates**: Instant feedback on current highest bidder and remaining time.
- **Support Tool**: Integrated "Contact Admin" feature for reporting issues or requesting assistance.

---

## 5. Technical Core (Backend & Real-time)
The platform is powered by a robust backend architecture:
- **API (Flask / WSGI)**: cPanel Passenger-compatible endpoints for all frontend interactions.
- **Database (SQLAlchemy/MySQL)**: Relational schema managing Users, Players, Teams, Events, Auctions, Bids, and Activity Logs.
- **Real-time Engine**: Auction logic handles bid increments, timer countdowns, and automatic winner selection.
- **Security**: 
    - Password hashing using bcrypt (handling 72-byte limits).
    - Session-based authentication with HTTP-only cookies.
    - Role-based access control (Admin, Player, Team Owner).

---

## 6. Real-time Auction Dashboard
A specialized view used during live events:
- **Live Bid Timer**: Visual countdown for each bid.
- **Dynamic Bidding**: Incremental bid logic prevents out-of-order or invalid bids.
- **Notification System**: Instant alerts for successful bids, outbids, and auction closures.

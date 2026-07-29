# JAMRIG - Sports Player Auction Platform

JAMRIG is a web application for managing and participating in live sports player auctions. It combines a responsive HTML, CSS, and JavaScript frontend with a Python Flask backend, SQLAlchemy data layer, and database-backed user and auction workflows.

## Features

- Responsive interface for desktop, tablet, and mobile browsers
- Auction pages with player details, bidding interactions, and countdowns
- Dashboards and workflows for administrators, team owners, and players
- User registration, authentication, and role-based navigation
- Sports ratings and player management
- Database-backed application using SQLAlchemy
- cPanel Passenger WSGI entry point for deployment

The frontend also includes the platform sections described in the original design: navigation and authentication buttons, hero and live-auction previews, animated statistics, a four-step "How It Works" section, registration prompts, and a footer with platform and support links. The original design notes describe simulated live updates and planned real-time integrations; availability depends on the deployed application configuration.

## Project Structure

```text
.
├── backend/              # Flask application, database, and setup utilities
│   ├── app.py            # Application entry point
│   ├── database.py       # SQLAlchemy engine and session configuration
│   ├── models.py         # Database models
│   ├── requirements.txt  # Python dependencies
│   └── passenger_wsgi.py # cPanel Passenger entry point
├── documents/            # System and deployment documentation
└── frontend/             # HTML templates, stylesheets, and JavaScript
    ├── css/
    ├── js/
    └── templates/
```

## Technology Stack

- **Frontend:** HTML5, CSS3 (Flexbox, Grid, and animations), and JavaScript (ES6+)
- **Backend:** Python and Flask
- **Data:** SQLAlchemy with SQLite or a configured MySQL database
- **Supporting libraries:** Pydantic, python-dotenv, python-jose, Passlib, and PyMySQL (see `backend/requirements.txt`)
- **UI assets:** Font Awesome and Google Fonts (Inter)

## Getting Started

### Backend

Use Python 3. Install dependencies from the backend directory:

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment (Windows: `.venv\Scripts\activate`; macOS/Linux: `source .venv/bin/activate`), then run:

```bash
python -m pip install -r requirements.txt
```

Configure database and application settings in a local `backend/.env` file as needed. Do not commit secrets or credentials. The application settings support a `DATABASE_URL`; the default in the code is a local SQLite database, while deployments can configure MySQL. Start the development server with:

```bash
python app.py
```

The Passenger entry point for cPanel is `backend/passenger_wsgi.py`.

### Frontend

Open the appropriate HTML page under `frontend/templates/` in a browser, or serve the frontend through the backend/deployment configuration. The initial prototype was vanilla HTML/CSS/JavaScript and required no frontend build step. Backend-dependent features require a running and configured API.

## Browser Support

The interface targets current versions of Chrome, Firefox, Safari, and Edge.

## Documentation

Deployment and architecture notes are available in `documents/`, including the Flask conversion guide and system overview.

## Design Principles

- **Usability:** clear navigation and calls to action
- **Performance:** responsive layouts and efficient page interactions
- **Accessibility:** semantic markup and readable contrast
- **Maintainability:** separated frontend assets and backend modules

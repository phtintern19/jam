# JAMRIG - Sports Player Auction Platform

JAMRIG is a web application for managing and participating in live sports player auctions. It combines a responsive HTML, CSS, and JavaScript frontend with a Python Flask application, SQLAlchemy data layer, and database-backed user and auction workflows. The Flask app serves the frontend.

## Project Structure

```text
.
|-- backend/                 # Flask application and database utilities
|   |-- app.py               # Flask application object
|   |-- passenger_wsgi.py    # cPanel Passenger entry point
|   |-- auction_engine.py
|   |-- database.py
|   |-- models.py
|   |-- requirements.txt
|   `-- .env.example         # Safe configuration template; copy to .env
|-- documents/               # Architecture and deployment documentation
`-- frontend/                # HTML pages, templates, styles, and scripts
    |-- css/
    |-- js/
    |-- index.html
    `-- templates/
```

## Features

- Responsive design for desktop, tablet, and mobile browsers
- Live sports auction events with timed bidding, player details, and countdowns
- Admin, player, and team-owner dashboards with role-based navigation
- User registration, session authentication, activity logs, and notifications
- Player management, sports ratings, and profile image uploads
- Navigation, hero and auction previews, statistics, a How It Works section, and footer links
- cPanel Passenger deployment support

The original frontend design also describes simulated live updates, modal interactions, animated statistics, and planned real-time integrations. Actual functionality depends on the deployed application configuration.

## Technology Stack

- **Frontend:** HTML5, CSS3 (Flexbox, Grid, and animations), JavaScript (ES6+)
- **Backend:** Python and Flask
- **Data:** SQLAlchemy with SQLite or configured MySQL
- **Libraries:** see `backend/requirements.txt` (includes Pydantic, python-dotenv, python-jose, Passlib, and PyMySQL)
- **UI assets:** Font Awesome and Google Fonts (Inter)

## Local Development

Use Python 3. From the project directory, create and activate a virtual environment:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `backend/.env` for your local database and application settings. For local MySQL-less testing, set `USE_SQLITE=true`. Never commit `.env` files, passwords, or credentials. Start the app from `backend/`:

```powershell
python app.py
```

The development server address is configured by the application. Open the running app in a browser; frontend pages are served through Flask. The original static prototype can also be opened directly from `frontend/` for UI-only review.

## cPanel Passenger Deployment

Keep `backend/` and `frontend/` as sibling directories. Set the cPanel Python application's root to `backend/` and use `passenger_wsgi.py` as its entry point.

1. Create a MySQL database and user in cPanel.
2. Upload the project with `backend/` and `frontend/` as siblings.
3. Create `backend/.env` from `.env.example`, and set the database credentials and a strong `SECRET_KEY`.
4. Install dependencies in the application's virtual environment with `pip install -r requirements.txt`.
5. Ensure the configured profile upload directory is writable by the application user.
6. Keep `ENABLE_SETUP_ROUTES=false` in production. Create the first admin with `python create_admin.py` over SSH.
7. Configure SMTP settings if password-reset OTP email is required, and restart the app after changing `.env`.

Auction progression uses request-scoped ticks for Passenger compatibility. An optional background thread is controlled by `ENABLE_AUCTION_ENGINE_THREAD`. See `documents/` for the system overview and deployment/conversion guide.

## Browser Support and Design

The interface targets current Chrome, Firefox, Safari, and Edge. The project emphasizes clear navigation, responsive performance, semantic markup, readable contrast, and separation of frontend assets from backend modules.

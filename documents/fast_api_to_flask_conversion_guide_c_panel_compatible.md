# FastAPI → Flask Conversion Guide (cPanel Compatible)

This document explains **how to convert an existing FastAPI application into Flask**, specifically to make it compatible with **cPanel (Passenger / WSGI)** hosting. The steps are written in a practical, implementation-first order so you can migrate safely without rewriting your entire backend.

---

## 1. Why Conversion Is Required

- **FastAPI is ASGI-based** (runs on Uvicorn/Hypercorn)
- **cPanel Passenger supports only WSGI**
- Passenger cannot run an event loop → FastAPI will not start correctly

**Flask is WSGI-based**, making it fully compatible with cPanel.

---

## 2. What Will Change vs What Will Stay

### Will Change
- App entry point (`FastAPI()` → `Flask()`)
- Route decorators
- Dependency Injection (`Depends`)
- Request parsing
- Middleware
- Startup/shutdown events

### Will Stay the Same
- SQLAlchemy models
- Database connection logic
- Business/service logic
- JWT logic (conceptually)
- Folder modularity

This is a **framework swap**, not a rewrite.

---

## 3. Create Flask App Entry Point

### FastAPI (`main.py`)
```python
from fastapi import FastAPI

app = FastAPI()
```

### Flask (`app.py`)
```python
from flask import Flask

app = Flask(__name__)
```

**Why:** Flask uses a WSGI-compatible app object instead of ASGI.

---

## 4. Convert Routes

### FastAPI Route
```python
@app.get("/health")
def health():
    return {"status": "ok"}
```

### Flask Route
```python
from flask import jsonify

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})
```

**Key Differences**
- Explicit HTTP methods
- `jsonify()` for responses
- No async support

---

## 5. Convert APIRouter → Blueprint

### FastAPI
```python
from fastapi import APIRouter

router = APIRouter(prefix="/auth")

@router.post("/login")
def login():
    return {"msg": "ok"}
```

### Flask
```python
from flask import Blueprint, jsonify

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

@auth_bp.route("/login", methods=["POST"])
def login():
    return jsonify({"msg": "ok"})
```

Register blueprint:
```python
app.register_blueprint(auth_bp)
```

---

## 6. Convert Request Handling

### FastAPI
```python
from fastapi import Request

@app.post("/data")
async def data(request: Request):
    body = await request.json()
    return body
```

### Flask
```python
from flask import request, jsonify

@app.route("/data", methods=["POST"])
def data():
    body = request.get_json()
    return jsonify(body)
```

**Why:** Flask is synchronous and simpler.

---

## 7. Replace Dependency Injection (Depends)

### FastAPI
```python
def get_db():
    ...

@app.get("/items")
def items(db=Depends(get_db)):
    ...
```

### Flask
```python
def get_db():
    ...

@app.route("/items")
def items():
    db = get_db()
    ...
```

**Why:** Flask does not support DI natively.

---

## 8. Pydantic Schemas (Optional but Recommended)

FastAPI auto-validates using Pydantic. Flask does not.

### Flask with Pydantic
```python
payload = request.get_json()
data = MySchema(**payload)
```

This keeps validation consistent.

---

## 9. Convert Middleware

### FastAPI
```python
@app.middleware("http")
async def middleware(request, call_next):
    response = await call_next(request)
    return response
```

### Flask
```python
@app.before_request
def before():
    pass

@app.after_request
def after(response):
    return response
```

---

## 10. Authentication (JWT)

Replace FastAPI OAuth dependencies with `flask-jwt-extended`.

```python
from flask_jwt_extended import jwt_required

@app.route("/protected")
@jwt_required()
def protected():
    return {"msg": "ok"}
```

JWT logic and token structure can remain the same.

---

## 11. Remove Startup & Shutdown Events

FastAPI lifecycle hooks are **not supported** in Passenger.

Move initialization logic to:
- App creation
- Module import time

---

## 12. Add passenger_wsgi.py (Mandatory)

Create this file in your application root:

```python
from app import app
application = app
```

Passenger looks **only** for `application`.

---

## 13. Recommended Folder Structure

```
backend/
│── app/
│   │── __init__.py
│   │── app.py
│   │── routes/
│   │── models/
│   │── schemas/
│   │── services/
│── passenger_wsgi.py
│── requirements.txt
│── .env
```

This structure works cleanly with cPanel Python App Manager.

---

## 14. Update requirements.txt

Remove:
- fastapi
- uvicorn
- starlette

Add:
```
flask
flask-jwt-extended
```

Keep:
- sqlalchemy
- pydantic
- python-dotenv

---

## 15. Migration Checklist

- [ ] Replace FastAPI app with Flask app
- [ ] Convert routes and routers
- [ ] Remove async/await
- [ ] Replace Depends
- [ ] Add passenger_wsgi.py
- [ ] Update requirements.txt
- [ ] Deploy via cPanel Python App Manager

---

## Final Note

This conversion makes your app **production-ready on shared hosting**. If you later move to VPS or Docker, the architecture allows an easy switch back to FastAPI.

---

**End of Document**

